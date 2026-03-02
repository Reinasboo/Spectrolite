"""
Meme Report Generator — post-trade summaries in the voice of a
deranged but self-aware degen.
"""
from __future__ import annotations

import logging
import random
from typing import Optional

from ..models import PersonalityMode, ScoredToken, TradeResult
from .level_system import LevelSystem

logger = logging.getLogger(__name__)

# ── Narrative templates ──────────────────────────────────────────────────────

WIN_OPENERS = [
    "We caught ${symbol} at the bonding curve, rode the Telegram pump like a mechanical bull "
    "at a crypto conference, and exited {exit_seconds:.0f} seconds before the dev wallet moved. Textbook.",
    "Absolutely cooked ${symbol} — bought the ignorance, sold the euphoria. "
    "The chart looked like a NASA launch profile and we were Mission Control.",
    "Chart said 'up'. We said 'yes'. ${symbol} delivered. The ancestors nodded approvingly.",
    "${symbol} was a gift from the meme gods. We accepted the gift, unwrapped it, "
    "and left before the glitter got everywhere.",
    "Entered ${symbol} before the normies smelled blood. "
    "Classic. Filed under: we knew first.",
]

LOSS_OPENERS = [
    "${symbol} turned out to be a learning experience. "
    "An expensive one. A humbling one. But educational.",
    "Poured one out for ${symbol}. She tried. We tried. The rug tried harder.",
    "${symbol} looked perfect on paper, which is why the paper is now worth less than the ${symbol}.",
    "The ${symbol} trade was a ghost story — looked real for a second, then vanished.",
    "We zigged. ${symbol} zagged. Into the abyss. Noted for the training set.",
]

SOBRIETY_LINES = [
    "Win streak: {streak}. Casino Mode: {mode}.",
    "The ancestors are {'proud' if streak > 3 else 'disappointed'}. "
    "Win streak: {streak}.",
    "Street credit: {'EARNED' if streak > 5 else 'in repair'}. Streak: {streak}.",
]


class MemeReporter:
    """
    Generates post-trade meme reports in degen voice.
    Dispatches summaries to Telegram and dashboard feed.
    """

    SEPARATOR = "━" * 42

    def __init__(self, level_system: LevelSystem, telegram_bot=None) -> None:
        self._levels = level_system
        self._telegram = telegram_bot

    def generate(
        self,
        trade: TradeResult,
        telegram_dispatch: bool = True,
    ) -> str:
        """Generate the full meme report for a closed trade."""
        pnl_pct = trade.realized_pnl_pct or 0
        pnl_usd = trade.realized_pnl_usd or 0

        opener_pool = WIN_OPENERS if trade.is_winner else LOSS_OPENERS
        opener_tpl = random.choice(opener_pool)
        opener = opener_tpl.format(
            symbol=trade.token.symbol,
            exit_seconds=random.uniform(5, 30),
        )

        state = self._levels.state()
        streak_line = (
            f"Win streak: {state.win_streak}. "
            f"{trade.mode.value}: {'ACTIVE' if state.win_streak >= 1 else 'OFF'}."
        )

        report = (
            f"TRADE CLOSED: ${trade.token.symbol} | "
            f"Entry: ${trade.entry_price:.8f} | "
            f"Exit: ${trade.exit_price:.8f} | "
            f"PnL: {pnl_pct*100:+.0f}%\n"
            f"{self.SEPARATOR}\n"
            f"   🚀 MEME REPORT: \"{opener} {streak_line}\"\n"
            f"{self.SEPARATOR}\n"
            f"   Meme Score at Entry: {trade.meme_score_at_entry:.0f} | "
            f"Scam Probability: {trade.token.scam_probability*100:.0f}% | "
            f"Mode: {trade.mode.value}\n"
            f"   P&L: ${pnl_usd:+.2f} | Leverage: {trade.leverage:.0f}x | "
            f"{'🧬 MUTATION APPLIED' if trade.mutation_applied else ''}\n"
            f"   {self._levels.format_progress()}"
        )

        logger.info(f"\n{report}")

        return report

    def generate_entry_note(
        self, token: ScoredToken, mode: PersonalityMode
    ) -> str:
        """Short entry announcement."""
        note = (
            f"🎯 ENTERING ${token.symbol} | "
            f"Meme={token.total_meme_score:.0f} | "
            f"Pump={token.pump_prediction.pump_probability*100:.0f}% | "
            f"Scam={token.scam_probability*100:.0f}% | "
            f"Mode: {mode.value}\n"
            f"   Thesis: {token.viral_thesis}"
        )
        logger.info(note)
        return note

    def generate_sobriety_report(
        self,
        portfolio_summary: dict,
        total_trades: int,
        win_rate: float,
        max_drawdown_pct: float,
    ) -> str:
        """Generate autopsy report text for SOBRIETY MODE."""
        return (
            "╔══════════════════════════════════════════════╗\n"
            "║   AUTOPSY OF A BEAUTIFUL DISASTER            ║\n"
            "║   SPECTROLITE — DEGENERATE GAMBIT v2.0       ║\n"
            "╚══════════════════════════════════════════════╝\n\n"
            f"Total Trades: {total_trades}\n"
            f"Win Rate:     {win_rate*100:.1f}%\n"
            f"Max Drawdown: {max_drawdown_pct*100:.1f}%\n"
            f"Final Portfolio: ${portfolio_summary.get('total_usd', 0):,.2f}\n\n"
            "The Iron Coffin remains sealed. The degen lives to YOLO again.\n\n"
            "\"May your bags be heavy and your rugs be light.\"\n"
            "— SPECTROLITE, post-autopsy reflection mode"
        )
