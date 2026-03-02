"""
Backtesting Engine for Spectrolite / Degenerate Gambit.
Simulates all signal triggers, mode switches, and exit rules
across historical Pump.fun and Solana DEX data.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    dataset_path: str = "data/pump_fun_2024.parquet"
    initial_capital: float = 10_000.0
    moonshot_allocation: float = 0.50
    rotation_allocation: float = 0.30
    min_meme_score: float = 65.0
    moonshot_meme_score: float = 85.0
    stop_loss_pct: float = 0.20
    take_profit_targets: list[float] = field(default_factory=lambda: [2.0, 5.0, 10.0])
    exit_pcts_at_targets: list[float] = field(default_factory=lambda: [0.30, 0.40, 0.30])
    pump_probability_threshold: float = 0.72
    std_entry_pct: float = 0.03
    high_conviction_pct: float = 0.15
    output_dir: str = "results/"
    # ── Transaction cost model ───────────────────────────────────────────
    # Slippage is modelled as inversely proportional to sqrt(liquidity_usd)
    # DEX fee: 0.25% each way (Jupiter/Uniswap standard)
    # Priority fee: flat 0.2% per trade (conservative estimate)
    dex_fee_pct: float = 0.0025        # 0.25% base DEX fee
    priority_fee_pct: float = 0.002    # 0.2% priority fee estimate
    slippage_k: float = 500.0          # slippage = k / sqrt(liquidity_usd)
    default_liquidity_usd: float = 25_000.0  # fallback when liquidity unknown


@dataclass
class BacktestResult:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    final_portfolio_usd: float
    avg_pnl_pct: float
    best_trade_pct: float
    worst_trade_pct: float
    win_rate_by_meme_tier: dict[str, float] = field(default_factory=dict)
    level_system_impact: dict[str, Any] = field(default_factory=dict)
    equity_curve: list[float] = field(default_factory=list)


class Backtester:
    """
    Full backtesting engine that replays historical token data through
    all signal filters, mode switches, and exit rules.
    """

    def __init__(self, config: BacktestConfig) -> None:
        self._cfg = config

    def load_dataset(self) -> pd.DataFrame:
        path = Path(self._cfg.dataset_path)
        if not path.exists():
            logger.warning(f"Dataset not found: {path}. Using synthetic data.")
            return self._generate_synthetic_dataset()

        if path.suffix == ".parquet":
            return pd.read_parquet(path)
        elif path.suffix == ".csv":
            return pd.read_csv(path)
        raise ValueError(f"Unsupported dataset format: {path.suffix}")

    def _generate_synthetic_dataset(self, n: int = 10_000) -> pd.DataFrame:
        """
        Generate synthetic token data for testing when real dataset unavailable.
        """
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="15min"),
            "token_address": [f"ADDR{i:05d}" for i in range(n)],
            "symbol": [f"TOKEN{i:04d}" for i in range(n)],
            "chain": rng.choice(["solana", "base", "bnb"], n),
            "price_usd": rng.lognormal(-8, 2, n),
            "volume_5m": rng.exponential(5000, n),
            "meme_score": rng.uniform(40, 100, n),
            "scam_probability": rng.beta(2, 8, n),
            "pump_probability": rng.beta(3, 5, n),
            # Simulated outcomes
            "peak_return_15m": rng.lognormal(0.1, 1.2, n),
            "did_rug": rng.choice([0, 1], n, p=[0.85, 0.15]),
        })
        return df

    def run(self, df: pd.DataFrame | None = None) -> BacktestResult:
        """
        Main backtest execution. Returns a BacktestResult with full statistics.
        """
        if df is None:
            df = self.load_dataset()

        logger.info(f"Running backtest on {len(df):,} historical events…")

        portfolio = self._cfg.initial_capital
        equity_curve = [portfolio]
        trades: list[dict] = []

        rotation_cap = portfolio * self._cfg.rotation_allocation
        moonshot_cap = portfolio * self._cfg.moonshot_allocation

        for _, row in df.iterrows():
            # ── Signal filter ───────────────────────────────────
            meme = row.get("meme_score", 0)
            scam = row.get("scam_probability", 1.0)
            pump_prob = row.get("pump_probability", 0.0)
            did_rug = bool(row.get("did_rug", 0))

            if meme < self._cfg.min_meme_score:
                continue
            if scam >= 0.40:
                continue
            if pump_prob < self._cfg.pump_probability_threshold:
                continue
            if did_rug:
                pnl_pct = -self._cfg.stop_loss_pct
            else:
                raw_return = float(row.get("peak_return_15m", 1.0))
                pnl_pct = self._apply_exits(raw_return - 1.0)

            # ── Transaction cost model ────────────────────────────────────
            liquidity = float(row.get("liquidity_usd", self._cfg.default_liquidity_usd) or self._cfg.default_liquidity_usd)
            pnl_pct = self._apply_tx_costs(pnl_pct, liquidity)

            # ── Position sizing ──────────────────────────────────
            if meme >= self._cfg.moonshot_meme_score:
                size = moonshot_cap * self._cfg.high_conviction_pct
            else:
                size = rotation_cap * self._cfg.std_entry_pct

            pnl_usd = size * pnl_pct
            portfolio += pnl_usd
            equity_curve.append(portfolio)

            trades.append({
                "symbol": row.get("symbol"),
                "meme_score": meme,
                "pnl_pct": pnl_pct,
                "pnl_usd": pnl_usd,
                "size_usd": size,
            })

        return self._compute_stats(trades, equity_curve, portfolio)

    def _apply_tx_costs(self, gross_pnl: float, liquidity_usd: float) -> float:
        """
        Deduct realistic round-trip transaction costs:
          - Entry slippage  : k / sqrt(liquidity) (inverse square-root impact model)
          - Exit slippage   : same (exit into lower liquidity after a pump)
          - DEX fee         : 2 × dex_fee_pct (entry + exit)
          - Priority fee    : 2 × priority_fee_pct
        Total round-trip cost is subtracted from gross PnL.
        """
        slippage_one_way = self._cfg.slippage_k / max(liquidity_usd ** 0.5, 1.0) / 100.0
        # Exit slippage is 1.5× entry slippage (thinner book post-pump)
        slippage_total = slippage_one_way + slippage_one_way * 1.5
        dex_total = self._cfg.dex_fee_pct * 2
        priority_total = self._cfg.priority_fee_pct * 2
        total_cost = slippage_total + dex_total + priority_total
        return gross_pnl - total_cost

    def _apply_exits(self, raw_pnl: float) -> float:
        """
        Apply scaled exit rules to a raw return.
        Returns the realised PnL percentage after exit logic.
        """
        if raw_pnl <= -self._cfg.stop_loss_pct:
            return -self._cfg.stop_loss_pct

        # Scaled exit at targets
        realised = 0.0
        remaining = 1.0
        for target_mult, exit_pct in zip(self._cfg.take_profit_targets, self._cfg.exit_pcts_at_targets):
            target_pnl = target_mult - 1.0
            if raw_pnl >= target_pnl:
                realised += exit_pct * target_pnl
                remaining -= exit_pct

        # Remainder at actual return
        realised += remaining * raw_pnl
        return realised

    def _compute_stats(
        self,
        trades: list[dict],
        equity_curve: list[float],
        final_portfolio: float,
    ) -> BacktestResult:
        if not trades:
            return BacktestResult(
                total_trades=0, wins=0, losses=0, win_rate=0.0,
                total_return_pct=0.0, sharpe_ratio=0.0, max_drawdown_pct=0.0,
                final_portfolio_usd=final_portfolio, avg_pnl_pct=0.0,
                best_trade_pct=0.0, worst_trade_pct=0.0,
            )

        pnls = [t["pnl_pct"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        # Sharpe Ratio (annualised, 15-min cycles)
        periods_per_year = 4 * 24 * 365
        mean_ret = np.mean(pnls)
        std_ret = np.std(pnls) + 1e-10
        sharpe = (mean_ret / std_ret) * np.sqrt(periods_per_year)

        # Max Drawdown
        peak = self._cfg.initial_capital
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd

        total_return = (final_portfolio - self._cfg.initial_capital) / self._cfg.initial_capital

        # Win rate by meme tier
        tiers = {"<65": [], "65-75": [], "75-85": [], "85+": []}
        for t in trades:
            ms = t["meme_score"]
            tier = "<65" if ms < 65 else ("65-75" if ms < 75 else ("75-85" if ms < 85 else "85+"))
            tiers[tier].append(1 if t["pnl_pct"] > 0 else 0)

        wr_by_tier = {
            k: (sum(v) / len(v) if v else 0.0) for k, v in tiers.items()
        }

        result = BacktestResult(
            total_trades=len(trades),
            wins=len(wins),
            losses=len(losses),
            win_rate=len(wins) / len(trades),
            total_return_pct=total_return,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd,
            final_portfolio_usd=final_portfolio,
            avg_pnl_pct=mean_ret,
            best_trade_pct=max(pnls),
            worst_trade_pct=min(pnls),
            win_rate_by_meme_tier=wr_by_tier,
            equity_curve=equity_curve,
        )

        self._print_report(result)
        return result

    def _print_report(self, r: BacktestResult) -> None:
        sep = "─" * 50
        logger.info(
            f"\n{sep}\n"
            f"  BACKTEST RESULTS — SPECTROLITE\n{sep}\n"
            f"  Total Trades:    {r.total_trades:,}\n"
            f"  Win Rate:        {r.win_rate*100:.1f}%\n"
            f"  Total Return:    {r.total_return_pct*100:+.1f}%\n"
            f"  Sharpe Ratio:    {r.sharpe_ratio:.2f}\n"
            f"  Max Drawdown:    {r.max_drawdown_pct*100:.1f}%\n"
            f"  Final Portfolio: ${r.final_portfolio_usd:,.2f}\n"
            f"  Best Trade:      {r.best_trade_pct*100:+.1f}%\n"
            f"  Worst Trade:     {r.worst_trade_pct*100:+.1f}%\n"
            f"\n  Win Rate by Meme Score Tier:\n"
            + "".join(
                f"    {k}: {v*100:.1f}%\n" for k, v in r.win_rate_by_meme_tier.items()
            )
            + f"{sep}"
        )

    def save_results(self, result: BacktestResult, output_dir: str = "") -> Path:
        out = Path(output_dir or self._cfg.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "backtest_results.json"

        data = {
            k: v for k, v in result.__dict__.items()
            if k != "equity_curve"
        }
        data["equity_curve_length"] = len(result.equity_curve)
        path.write_text(json.dumps(data, indent=2, default=str))

        # Save equity curve separately
        eq_path = out / "equity_curve.csv"
        pd.DataFrame({"equity": result.equity_curve}).to_csv(eq_path, index=False)
        logger.info(f"Results saved to {out}/")
        return path
