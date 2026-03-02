"""
Monte Carlo Stress Testing for Spectrolite.
Runs 10,000 portfolio simulations under various catastrophic scenarios.
Reports Value at Risk (VaR) and maximum ruin probability.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SCENARIOS: dict[str, dict[str, Any]] = {
    "black_swan_dump": {
        "description": "Sudden 80% market-wide crash",
        "loss_multiplier": 0.80,
        "probability_of_occurrence": 0.60,
        "duration_cycles": 5,
    },
    "coordinated_rug_wave": {
        "description": "Coordinated rug across all held positions",
        "loss_multiplier": 0.70,
        "probability_of_occurrence": 0.40,
        "duration_cycles": 3,
    },
    "liquidity_crisis": {
        "description": "Liquidity evaporates — unable to exit positions",
        "loss_multiplier": 0.50,
        "probability_of_occurrence": 0.30,
        "duration_cycles": 8,
    },
    "MEV_attack_barrage": {
        "description": "Sustained MEV front-running on all entries",
        "loss_multiplier": 0.10,   # 10% slippage loss per trade
        "probability_of_occurrence": 0.20,
        "duration_cycles": 20,
    },
}


@dataclass
class MonteCarloResult:
    initial_capital: float
    iterations: int
    scenarios: list[str]
    var_95_usd: float          # Value at Risk at 95% confidence
    var_99_usd: float          # Value at Risk at 99% confidence
    max_ruin_probability: float
    median_final_portfolio: float
    mean_final_portfolio: float
    best_outcome_usd: float
    worst_outcome_usd: float
    percentiles: dict[str, float] = field(default_factory=dict)
    scenario_survival_rates: dict[str, float] = field(default_factory=dict)


def monte_carlo_simulation(
    initial_capital: float = 10_000,
    iterations: int = 10_000,
    scenarios: list[str] | None = None,
    base_win_rate: float = 0.55,
    base_avg_win: float = 0.85,
    base_avg_loss: float = 0.20,
    trade_size_fraction: float = 0.03,
    iron_coffin_fraction: float = 0.05,
    report: str = "Value at Risk (VaR) at 95% and 99% confidence, max ruin probability",
) -> MonteCarloResult:
    """
    Run Monte Carlo simulation over N iterations.

    Parameters
    ----------
    initial_capital : float
        Starting portfolio value.
    iterations : int
        Number of Monte Carlo iterations (default 10,000).
    scenarios : list[str]
        Names of stress scenarios to inject (from SCENARIOS dict).
    base_win_rate : float
        Historical win rate of the strategy.
    base_avg_win : float
        Average win as a fraction of position size.
    base_avg_loss : float
        Average loss (stop-loss fraction).
    trade_size_fraction : float
        Position size as fraction of rotation pool.
    iron_coffin_fraction : float
        Untouchable reserve fraction.
    report : str
        Description of what to report (for logging).

    Returns
    -------
    MonteCarloResult with VaR, ruin probability, and percentile distribution.
    """
    active_scenarios = scenarios or list(SCENARIOS.keys())
    rng = np.random.default_rng(42)
    final_portfolios: list[float] = []
    scenario_outcomes: dict[str, list[float]] = {s: [] for s in active_scenarios}

    iron_coffin = initial_capital * iron_coffin_fraction
    tradeable = initial_capital * (1 - iron_coffin_fraction)

    logger.info(
        f"Monte Carlo: {iterations:,} iterations | "
        f"capital=${initial_capital:,.0f} | scenarios={active_scenarios}"
    )

    for _ in range(iterations):
        portfolio = tradeable
        trades_per_sim = 200

        # Determine if a stress scenario occurs this simulation
        active_stress: dict[str, Any] | None = None
        for sc_name in active_scenarios:
            sc = SCENARIOS.get(sc_name, {})
            if rng.random() < sc.get("probability_of_occurrence", 0):
                active_stress = {**sc, "name": sc_name}
                break

        for trade_num in range(trades_per_sim):
            # Inject stress event at random point
            stress_active = (
                active_stress is not None
                and trades_per_sim // 2 <= trade_num < trades_per_sim // 2 + active_stress.get("duration_cycles", 1)
            )

            # Position size
            rotation = portfolio * (0.30 / (1 - iron_coffin_fraction))
            size = rotation * trade_size_fraction

            if stress_active:
                loss_mult = active_stress.get("loss_multiplier", 0.5)
                portfolio -= size * loss_mult
            else:
                if rng.random() < base_win_rate:
                    portfolio += size * (base_avg_win + rng.exponential(0.3))
                else:
                    portfolio -= size * base_avg_loss

            # Portfolio floored at iron coffin (never touch it)
            portfolio = max(portfolio, 0.0)

        final = portfolio + iron_coffin   # add back iron coffin
        final_portfolios.append(final)

        if active_stress:
            sc_name = active_stress["name"]
            if sc_name in scenario_outcomes:
                scenario_outcomes[sc_name].append(final)

    arr = np.array(final_portfolios)

    # VaR calculations
    var_95 = initial_capital - float(np.percentile(arr, 5))    # 5th percentile loss
    var_99 = initial_capital - float(np.percentile(arr, 1))    # 1st percentile loss
    ruin_prob = float((arr < initial_capital * 0.20).mean())    # 80%+ loss = ruin

    # Scenario survival rates (final > 50% of initial)
    survival_rates: dict[str, float] = {}
    for sc_name, outcomes in scenario_outcomes.items():
        if outcomes:
            n_survived = sum(1 for o in outcomes if o > initial_capital * 0.50)
            survival_rates[sc_name] = n_survived / len(outcomes)

    result = MonteCarloResult(
        initial_capital=initial_capital,
        iterations=iterations,
        scenarios=active_scenarios,
        var_95_usd=var_95,
        var_99_usd=var_99,
        max_ruin_probability=ruin_prob,
        median_final_portfolio=float(np.median(arr)),
        mean_final_portfolio=float(np.mean(arr)),
        best_outcome_usd=float(arr.max()),
        worst_outcome_usd=float(arr.min()),
        percentiles={
            "p1": float(np.percentile(arr, 1)),
            "p5": float(np.percentile(arr, 5)),
            "p25": float(np.percentile(arr, 25)),
            "p50": float(np.percentile(arr, 50)),
            "p75": float(np.percentile(arr, 75)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
        },
        scenario_survival_rates=survival_rates,
    )

    _print_mc_report(result)
    return result


def _print_mc_report(r: MonteCarloResult) -> None:
    sep = "═" * 55
    scenario_lines = "\n".join(
        f"    {k}: {v*100:.1f}% survived"
        for k, v in r.scenario_survival_rates.items()
    )
    logger.info(
        f"\n{sep}\n"
        f"  MONTE CARLO STRESS TEST — {r.iterations:,} ITERATIONS\n"
        f"  Initial Capital: ${r.initial_capital:,.2f}\n"
        f"{sep}\n"
        f"  VaR (95%):          ${r.var_95_usd:,.2f}\n"
        f"  VaR (99%):          ${r.var_99_usd:,.2f}\n"
        f"  Max Ruin Prob:      {r.max_ruin_probability*100:.2f}%\n"
        f"  Median Outcome:     ${r.median_final_portfolio:,.2f}\n"
        f"  Best Outcome:       ${r.best_outcome_usd:,.2f}\n"
        f"  Worst Outcome:      ${r.worst_outcome_usd:,.2f}\n\n"
        f"  Scenario Survival Rates:\n{scenario_lines or '    (no scenarios triggered)'}\n"
        f"{sep}"
    )
