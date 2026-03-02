"""
CLI entry point for Spectrolite — Degenerate Gambit.

Usage:
  python -m degenerate_gambit               # run live agent
  python -m degenerate_gambit backtest      # run backtests
  python -m degenerate_gambit montecarlo    # run Monte Carlo stress tests
  python -m degenerate_gambit dashboard     # launch Streamlit dashboard
"""
from __future__ import annotations

import asyncio
import logging
import sys

import click

logger = logging.getLogger("spectrolite.cli")


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """SPECTROLITE — Degenerate Gambit v2.0 — Autonomous AI Memecoin Trading Agent"""
    if ctx.invoked_subcommand is None:
        # Default: run the live agent
        ctx.invoke(run)


@cli.command()
def run() -> None:
    """Start the live trading agent."""
    from .agent import run_agent
    click.echo("🚀 Launching SPECTROLITE — Degenerate Gambit v2.0…")
    asyncio.run(run_agent())


@cli.command()
@click.option("--dataset", default="data/pump_fun_2024.parquet", help="Path to historical dataset")
@click.option("--output", default="results/", help="Output directory for results")
@click.option("--capital", default=10_000.0, help="Initial capital (USD)")
def backtest(dataset: str, output: str, capital: float) -> None:
    """Run backtesting on historical data."""
    from .backtest import Backtester, BacktestConfig
    click.echo(f"📊 Running backtest on {dataset}…")
    cfg = BacktestConfig(dataset_path=dataset, output_dir=output, initial_capital=capital)
    bt = Backtester(cfg)
    df = bt.load_dataset()
    result = bt.run(df)
    path = bt.save_results(result, output)
    click.echo(f"✅ Results saved to {path}")


@cli.command()
@click.option("--iterations", default=10_000, help="Number of Monte Carlo iterations")
@click.option("--capital", default=10_000.0, help="Initial capital (USD)")
@click.option(
    "--scenario",
    multiple=True,
    default=["black_swan_dump", "coordinated_rug_wave", "liquidity_crisis", "MEV_attack_barrage"],
    help="Stress scenarios to simulate",
)
def montecarlo(iterations: int, capital: float, scenario: tuple[str, ...]) -> None:
    """Run Monte Carlo stress tests."""
    from .backtest import monte_carlo_simulation
    click.echo(f"🎲 Running {iterations:,} Monte Carlo iterations…")
    result = monte_carlo_simulation(
        initial_capital=capital,
        iterations=iterations,
        scenarios=list(scenario),
    )
    click.echo(
        f"\n📈 Results:\n"
        f"  VaR (95%): ${result.var_95_usd:,.2f}\n"
        f"  VaR (99%): ${result.var_99_usd:,.2f}\n"
        f"  Ruin Probability: {result.max_ruin_probability*100:.2f}%\n"
        f"  Median Portfolio: ${result.median_final_portfolio:,.2f}"
    )


@cli.command()
@click.option("--port", default=8501, help="Streamlit dashboard port")
def dashboard(port: int) -> None:
    """Launch the Streamlit P&L dashboard."""
    import subprocess
    import os
    dashboard_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "app.py")
    click.echo(f"🖥️  Launching dashboard on http://localhost:{port}")
    subprocess.run(
        ["streamlit", "run", dashboard_path, "--server.port", str(port)],
        check=True,
    )


if __name__ == "__main__":
    cli()
