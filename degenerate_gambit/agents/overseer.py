"""
Overseer Agent — orchestrates all sub-agents, enforces risk limits,
and manages mode switching. Uses CrewAI for multi-agent coordination.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from ..analysis import ChainAnalyst, CrossChainArbDetector, SentimentEngine, SignalFusionEngine
from ..config import get_settings
from ..execution import PositionManager, TradeExecutor
from ..gamification import LevelSystem, MemeReporter, ModeManager
from ..models import PersonalityMode, PortfolioState, ScoredToken
from ..scam_shield import ScamSlayer
from ..wallet import SwarmIntelligence, WalletTracker

logger = logging.getLogger(__name__)
_cfg = get_settings()


@dataclass
class AgentContext:
    portfolio: PortfolioState
    mode_manager: ModeManager
    level_system: LevelSystem
    chain_analyst: ChainAnalyst
    sentiment_engine: SentimentEngine
    signal_fusion: SignalFusionEngine
    scam_slayer: ScamSlayer
    wallet_tracker: WalletTracker
    swarm: SwarmIntelligence
    trade_executor: TradeExecutor
    position_manager: PositionManager
    meme_reporter: MemeReporter
    arb_detector: CrossChainArbDetector


class OverseerAgent:
    """
    The central orchestrator of SPECTROLITE.
    Runs the main analysis loop:
      scan → score → filter → execute → monitor → report
    """

    def __init__(self, ctx: AgentContext) -> None:
        self._ctx = ctx
        self._running = False
        self._peak_portfolio_usd = ctx.portfolio.total_usd

    async def run(self) -> None:
        """Main agent loop. Runs until SOBRIETY MODE or KeyboardInterrupt."""
        self._running = True
        logger.info(
            f"\n{'═'*55}\n"
            f"  SPECTROLITE — DEGENERATE GAMBIT v2.0 ONLINE\n"
            f"  Capital: ${self._ctx.portfolio.total_usd:,.0f} | "
            f"Mode: {self._ctx.mode_manager.current_mode.value}\n"
            f"{'═'*55}"
        )

        while self._running:
            try:
                await self._analysis_cycle()
                await asyncio.sleep(_cfg.agent.analysis_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Analysis cycle error: {exc}", exc_info=True)
                await asyncio.sleep(5)

    async def _analysis_cycle(self) -> None:
        """Single scan → score → execute → report cycle."""
        ctx = self._ctx

        # Check SOBRIETY MODE before anything
        if ctx.mode_manager.current_mode == PersonalityMode.SOBRIETY:
            logger.warning("🛑 SOBRIETY MODE ACTIVE — all trading halted")
            self._running = False
            await self._trigger_sobriety_mode()
            return

        # ── 1. Ingest fresh data from all sub-agents ──────────────────────
        raw_signals, swarm_signals, _ = await asyncio.gather(
            self._run_chain_sentiment_scan(),
            ctx.swarm.get_alpha_moves(
                min_consensus_pct=_cfg.signals.min_wallet_consensus_pct
            ),
            ctx.arb_detector.scan_arb_opportunities(),
            return_exceptions=True,
        )

        if isinstance(raw_signals, Exception):
            logger.error(f"Signal ingestion failed: {raw_signals}")
            raw_signals = []

        # ── 2. Pre-screen for obvious scams ──────────────────────────────
        prescreened = await ctx.scam_slayer.prescreen_new_tokens(raw_signals)

        # ── 3. Score all candidates via signal fusion ─────────────────────
        candidates: list[ScoredToken] = ctx.signal_fusion.score_all(prescreened)

        # ── 4. Filter by current mode thresholds ─────────────────────────
        threshold = ctx.mode_manager.current_threshold()
        valid = [
            t for t in candidates
            if t.total_meme_score >= threshold
            and t.scam_probability < _cfg.scam_shield.max_scam_probability
            and t.pump_prediction.pump_probability >= _cfg.signals.pump_probability_threshold
        ]

        logger.info(
            f"[Cycle] signals={len(raw_signals)} → candidates={len(candidates)} "
            f"→ valid={len(valid)} | mode={ctx.mode_manager.current_mode.value}"
        )

        # ── 5. Execute trades ─────────────────────────────────────────────
        max_pos = _cfg.agent.max_concurrent_positions
        for token in valid[:max_pos]:
            trade = await ctx.trade_executor.enter_position(token)
            if trade:
                ctx.position_manager.add_position(trade)

        # ── 6. Monitor & manage open positions ───────────────────────────
        closed_trades = await ctx.position_manager.run_exits()
        for trade in closed_trades:
            ctx.portfolio.closed_trades.append(trade)
            ctx.meme_reporter.generate(trade)

        # ── 7. Update gamification state ─────────────────────────────────
        ctx.level_system.update(ctx.portfolio.closed_trades)
        ctx.mode_manager.evaluate_mode_switch(ctx.portfolio)

    async def _run_chain_sentiment_scan(self) -> list[dict]:
        """Concurrent scan across chain analyst and sentiment engine."""
        ctx = self._ctx
        vol_task = ctx.chain_analyst.get_volume_anomalies()
        raw_signals = await vol_task

        # Enrich each signal with sentiment data
        for sig in raw_signals:
            symbol = sig.get("symbol", "")
            try:
                sentiment = await ctx.sentiment_engine.analyse(symbol)
                sig["base_theme_bonus"] = sentiment.base_theme_bonus
                sig["social_velocity_index"] = sentiment.social_velocity_index
                sig["visual_hype_score"] = sentiment.visual_hype_score
                sig["narrative_alignment"] = sentiment.narrative_alignment
                sig["celebrity_endorsement"] = sentiment.celebrity_endorsement
                sig["viral_thesis"] = sentiment.viral_thesis
            except Exception as exc:
                logger.debug(f"Sentiment enrichment failed for {symbol}: {exc}")

        return raw_signals

    async def _trigger_sobriety_mode(self) -> None:
        """Generate autopsy report and email it."""
        ctx = self._ctx
        total_trades = len(ctx.portfolio.closed_trades)
        win_rate = ctx.portfolio.win_rate
        max_dd = max(
            0,
            (self._peak_portfolio_usd - ctx.portfolio.total_usd) / self._peak_portfolio_usd,
        )
        report_text = ctx.meme_reporter.generate_sobriety_report(
            portfolio_summary={"total_usd": ctx.portfolio.total_usd},
            total_trades=total_trades,
            win_rate=win_rate,
            max_drawdown_pct=max_dd,
        )
        logger.critical(f"\n{report_text}")

        # Attempt PDF delivery
        try:
            from ..notifications import deliver_autopsy_report
            await deliver_autopsy_report(report_text)
        except Exception as exc:
            logger.error(f"Failed to deliver autopsy report: {exc}")

    def stop(self) -> None:
        self._running = False
