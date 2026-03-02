"""
Level-Up System — tracks win/loss streaks and unlocks degen tiers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..models import TradeResult

logger = logging.getLogger(__name__)

LEVEL_TABLE = [
    {"level": 1, "min_wins": 0,  "max_wins": 4,  "max_leverage": 3,  "label": "Paper Hands Peasant"},
    {"level": 2, "min_wins": 5,  "max_wins": 9,  "max_leverage": 5,  "label": "Certified Degen"},
    {"level": 3, "min_wins": 10, "max_wins": 19, "max_leverage": 7,  "label": "Moon Math Specialist"},
    {"level": 4, "min_wins": 20, "max_wins": 9999, "max_leverage": 10, "label": "Full Degen Transcendence"},
]

MILESTONE_TITLES = {5: "CASINO MODE UNLOCKED 🎰", 10: "ALL-IN MODE ACTIVE 🔮", 20: "FULL DEGEN 🌝"}


@dataclass
class LevelState:
    level: int
    label: str
    max_leverage: int
    total_wins: int
    total_losses: int
    win_streak: int
    loss_streak: int
    xp_progress_pct: float


class LevelSystem:
    """
    Manages the level progression system.
    Level resets down by 1 on 3 consecutive losing trades.
    """

    RESET_ON_LOSSES = 3

    def __init__(self) -> None:
        self._total_wins = 0
        self._total_losses = 0
        self._win_streak = 0
        self._loss_streak = 0

    @property
    def current_streak(self) -> int:
        return self._win_streak

    @property
    def current_level(self) -> int:
        for row in reversed(LEVEL_TABLE):
            if self._total_wins >= row["min_wins"]:
                return row["level"]
        return 1

    @property
    def current_label(self) -> str:
        for row in reversed(LEVEL_TABLE):
            if self._total_wins >= row["min_wins"]:
                return row["label"]
        return LEVEL_TABLE[0]["label"]

    @property
    def current_max_leverage(self) -> int:
        for row in reversed(LEVEL_TABLE):
            if self._total_wins >= row["min_wins"]:
                return row["max_leverage"]
        return 3

    def state(self) -> LevelState:
        level = self.current_level
        row = LEVEL_TABLE[level - 1]
        next_row = LEVEL_TABLE[min(level, len(LEVEL_TABLE) - 1)]
        total_in_tier = next_row["min_wins"] - row["min_wins"]
        wins_in_tier = max(0, self._total_wins - row["min_wins"])
        progress = min(wins_in_tier / max(total_in_tier, 1), 1.0) * 100

        return LevelState(
            level=level,
            label=self.current_label,
            max_leverage=self.current_max_leverage,
            total_wins=self._total_wins,
            total_losses=self._total_losses,
            win_streak=self._win_streak,
            loss_streak=self._loss_streak,
            xp_progress_pct=progress,
        )

    def update(self, trade_history: list[TradeResult]) -> LevelState:
        """Recalculate from full trade history."""
        self._total_wins = 0
        self._total_losses = 0
        self._win_streak = 0
        self._loss_streak = 0
        consecutive_losses = 0
        manual_level_penalty = 0

        for trade in trade_history:
            if trade.is_winner:
                self._total_wins += 1
                self._win_streak += 1
                self._loss_streak = 0
                consecutive_losses = 0
                if self._win_streak in MILESTONE_TITLES:
                    logger.info(f"🏆 {MILESTONE_TITLES[self._win_streak]}")
            else:
                self._total_losses += 1
                self._loss_streak += 1
                self._win_streak = 0
                consecutive_losses += 1
                if consecutive_losses >= self.RESET_ON_LOSSES:
                    manual_level_penalty += 1
                    consecutive_losses = 0
                    logger.info("📉 3 consecutive losses — level reset -1")

        # Apply level penalties (reduce win total to simulate drop)
        effective_wins = max(0, self._total_wins - manual_level_penalty * 5)
        self._total_wins = effective_wins

        return self.state()

    def _progress_bar(self, pct: float, width: int = 10) -> str:
        filled = int(pct / 100 * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}]"

    def format_progress(self) -> str:
        state = self.state()
        bar = self._progress_bar(state.xp_progress_pct)
        return (
            f"Next Level: {bar} {state.xp_progress_pct:.0f}% to Level {min(state.level + 1, 4)}"
        )
