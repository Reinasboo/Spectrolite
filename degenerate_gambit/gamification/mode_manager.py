"""
Personality Mode Manager — dynamically switches agent behaviour
based on portfolio state and market conditions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..models import OrderType, PersonalityMode, PortfolioState

logger = logging.getLogger(__name__)


@dataclass
class ModeParameters:
    mode: PersonalityMode
    min_meme_score: float
    position_size_multiplier: float
    max_leverage: int
    slippage_tolerance: float
    order_type: OrderType
    skip_analysis_seconds: float = 0.0
    description: str = ""


MODE_PARAMS: dict[PersonalityMode, ModeParameters] = {
    PersonalityMode.APE: ModeParameters(
        mode=PersonalityMode.APE,
        min_meme_score=65,
        position_size_multiplier=1.50,   # +50%
        max_leverage=5,
        slippage_tolerance=0.05,
        order_type=OrderType.INSTANT_MARKET,
        skip_analysis_seconds=120,       # skip 2 min of analysis
        description="FOMO entry enabled. Ape hard.",
    ),
    PersonalityMode.SNIPER: ModeParameters(
        mode=PersonalityMode.SNIPER,
        min_meme_score=60,
        position_size_multiplier=1.0,
        max_leverage=10,
        slippage_tolerance=0.01,
        order_type=OrderType.TWAP,
        description="Precision entries at support. 10x available.",
    ),
    PersonalityMode.ZEN: ModeParameters(
        mode=PersonalityMode.ZEN,
        min_meme_score=80,               # raised threshold
        position_size_multiplier=0.50,   # halved
        max_leverage=3,
        slippage_tolerance=0.02,
        order_type=OrderType.TWAP,
        description="Portfolio down >30%. Calm. Surgical.",
    ),
    PersonalityMode.CASINO: ModeParameters(
        mode=PersonalityMode.CASINO,
        min_meme_score=65,
        position_size_multiplier=2.0,
        max_leverage=10,
        slippage_tolerance=0.05,
        order_type=OrderType.INSTANT_MARKET,
        description="Win streak≥5. All-in mode unlocked. Dopamine UI active.",
    ),
    PersonalityMode.SOBRIETY: ModeParameters(
        mode=PersonalityMode.SOBRIETY,
        min_meme_score=999,              # effectively halts all trading
        position_size_multiplier=0.0,
        max_leverage=1,
        slippage_tolerance=0.0,
        order_type=OrderType.TWAP,
        description="TRADING HALTED. Generating autopsy report.",
    ),
    PersonalityMode.STANDARD: ModeParameters(
        mode=PersonalityMode.STANDARD,
        min_meme_score=65,
        position_size_multiplier=1.0,
        max_leverage=3,
        slippage_tolerance=0.03,
        order_type=OrderType.INSTANT_MARKET,
        description="Standard parameters.",
    ),
}


class ModeManager:
    """
    Evaluates market and portfolio conditions to determine the active
    personality mode and exposes mode-specific trading parameters.
    """

    def __init__(self, initial_mode: PersonalityMode = PersonalityMode.STANDARD) -> None:
        self._mode = initial_mode
        self._previous_mode = initial_mode

    @property
    def current_mode(self) -> PersonalityMode:
        return self._mode

    @property
    def params(self) -> ModeParameters:
        return MODE_PARAMS[self._mode]

    def current_threshold(self) -> float:
        return self.params.min_meme_score

    def current_slippage_tolerance(self) -> float:
        return self.params.slippage_tolerance

    def current_order_type(self) -> OrderType:
        return self.params.order_type

    def evaluate_mode_switch(
        self,
        portfolio: PortfolioState,
        social_velocity_sigma: float = 0.0,
        has_accumulation_pattern: bool = False,
    ) -> PersonalityMode:
        """
        Re-evaluate and switch mode based on current conditions.
        Priority (highest first):
          SOBRIETY → ZEN → APE → CASINO → SNIPER → STANDARD
        """
        new_mode = self._determine_mode(
            portfolio, social_velocity_sigma, has_accumulation_pattern
        )

        if new_mode != self._mode:
            logger.info(
                f"🎭 MODE SWITCH: {self._mode.value} → {new_mode.value} | "
                f"{MODE_PARAMS[new_mode].description}"
            )
            self._previous_mode = self._mode
            self._mode = new_mode

        return self._mode

    def _determine_mode(
        self,
        portfolio: PortfolioState,
        social_velocity_sigma: float,
        has_accumulation_pattern: bool,
    ) -> PersonalityMode:
        # SOBRIETY takes absolute priority
        total_usd = portfolio.total_usd
        initial = (
            portfolio.iron_coffin_usd / 0.05
        ) if portfolio.iron_coffin_usd > 0 else total_usd
        drawdown = max(0, (initial - total_usd) / initial)
        if drawdown >= 0.80:
            return PersonalityMode.SOBRIETY

        # ZEN: portfolio down >30% in 24h
        if drawdown >= 0.30:
            return PersonalityMode.ZEN

        # APE: social velocity spike > 3σ
        if social_velocity_sigma >= 3.0:
            return PersonalityMode.APE

        # CASINO: win streak >= 5
        if portfolio.win_streak >= 5:
            return PersonalityMode.CASINO

        # SNIPER: low volume, accumulation detected
        if has_accumulation_pattern:
            return PersonalityMode.SNIPER

        return PersonalityMode.STANDARD

    def force_mode(self, mode: PersonalityMode) -> None:
        """Override: force a specific mode (for testing/SOBRIETY)."""
        self._previous_mode = self._mode
        self._mode = mode
        logger.info(f"🎭 MODE FORCED: {mode.value}")
