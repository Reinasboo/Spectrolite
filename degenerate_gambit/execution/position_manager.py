"""
Position Manager — monitors open positions and executes exit rules.
Handles trailing stops, scaled exits, hard stop-losses, and theta decay exits.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Callable

from ..config import get_settings
from ..models import TradeResult, TradeStatus

if TYPE_CHECKING:
    from .trade_executor import TradeExecutor, RiskManager

logger = logging.getLogger(__name__)
_cfg = get_settings()

# ---------------------------------------------------------------------------
# Graduated trailing stop table:
#   P&L range → trailing stop width
#   Tighter as profit grows — lets winners run while locking more gains
# ---------------------------------------------------------------------------
_TRAILING_STOP_SCHEDULE: list[tuple[float, float]] = [
    (0.00, 0.20),   # 0 →  +50%:  20% trailing
    (0.50, 0.15),   # +50 → +100%: 15% trailing
    (1.00, 0.10),   # +100 → +200%: 10% trailing
    (2.00, 0.08),   # +200 → +300%:  8% trailing
    (3.00, 0.06),   # +300 → +500%:  6% trailing
    (5.00, 0.04),   # >+500%:         4% trailing
]


def _trailing_stop_for_pnl(pnl_pct: float) -> float:
    """Return the appropriate trailing stop width for the current P&L level."""
    stop = _TRAILING_STOP_SCHEDULE[0][1]
    for threshold, width in _TRAILING_STOP_SCHEDULE:
        if pnl_pct >= threshold:
            stop = width
    return stop


class PositionManager:
    """
    Monitors all open positions at every analysis cycle.
    Applies:
      - Hard stop-loss at -20% (no exceptions)
      - Theta decay exit: forced close if +15% not reached within max_hold_minutes
      - Scaled exit: 30%@2x, 40%@5x, hold 30% for "fuck it" upside
      - Auto-exit: +500% → full exit
      - Graduated trailing stop: 6-level schedule from 20% → 4%
    """

    HARD_STOP_LOSS_PCT = -0.20
    FULL_EXIT_AT_500 = 5.00   # 500% gain → full exit
    SCALE_OUT_AT_200 = 0.60   # exit 60% of position at +200%

    # Theta decay exit: if price hasn't hit this minimum threshold within the
    # hold window, the pump thesis has failed — exit at market
    THETA_MIN_RETURN = 0.15         # +15% minimum expected move
    THETA_MAX_HOLD_MINUTES = 20     # minutes before forced exit

    # Scaled exit targets: (profit_multiplier_threshold, fraction_to_exit)
    SCALED_EXITS = [
        (1.0, 0.30),   # 2x  → sell 30%
        (4.0, 0.40),   # 5x  → sell 40%
        # remaining 30% rides under trailing stop / full exit
    ]

    def __init__(
        self,
        risk_manager: "RiskManager | None" = None,
        price_fetcher: Callable | None = None,
        max_hold_minutes: float = THETA_MAX_HOLD_MINUTES,
    ) -> None:
        self._positions: list[TradeResult] = []
        self._risk = risk_manager
        self._price_fetcher = price_fetcher         # async fn(address, chain) → float
        self._trailing_highs: dict[str, float] = {} # tx_hash → all-time-high price
        self._entry_times: dict[str, float] = {}    # tx_hash → entry unix timestamp
        self._max_hold_sec = max_hold_minutes * 60

    def add_position(self, trade: TradeResult) -> None:
        self._positions.append(trade)
        self._trailing_highs[trade.tx_hash] = trade.entry_price
        self._entry_times[trade.tx_hash] = time.time()

    async def run_exits(self) -> list[TradeResult]:
        """
        Check all open positions against exit rules.
        Returns list of trades that were closed this cycle.
        """
        closed: list[TradeResult] = []
        remaining: list[TradeResult] = []

        for trade in self._positions:
            if trade.status != TradeStatus.OPEN:
                continue

            current_price = await self._get_current_price(trade)
            if current_price is None:
                remaining.append(trade)
                continue

            pnl_pct = (current_price - trade.entry_price) / trade.entry_price

            # Update trailing high
            prev_high = self._trailing_highs.get(trade.tx_hash, trade.entry_price)
            if current_price > prev_high:
                self._trailing_highs[trade.tx_hash] = current_price
            high = self._trailing_highs[trade.tx_hash]

            hold_seconds = time.time() - self._entry_times.get(trade.tx_hash, time.time())
            should_close = self._evaluate_exits(trade, pnl_pct, current_price, high, hold_seconds)

            if should_close:
                await self._close_position(trade, current_price)
                closed.append(trade)
                if self._risk:
                    self._risk.position_closed()
            else:
                remaining.append(trade)

        self._positions = remaining
        return closed

    def _evaluate_exits(
        self,
        trade: TradeResult,
        pnl_pct: float,
        current_price: float,
        trailing_high: float,
        hold_seconds: float,
    ) -> bool:
        """Evaluate all exit rules in priority order."""

        # ── 1. Hard stop-loss: -20%, no exceptions ──────────────────────────
        if pnl_pct <= self.HARD_STOP_LOSS_PCT:
            logger.info(f"🛑 HARD STOP: ${trade.token.symbol} at {pnl_pct*100:+.1f}%")
            return True

        # ── 2. Theta decay exit ─────────────────────────────────────────────
        # If the pump thesis hasn't produced +15% within the hold window, bail
        if hold_seconds >= self._max_hold_sec and pnl_pct < self.THETA_MIN_RETURN:
            logger.info(
                f"⏰ THETA EXIT: ${trade.token.symbol} | "
                f"{hold_seconds/60:.1f}min held | {pnl_pct*100:+.1f}% — thesis failed"
            )
            return True

        # ── 3. Full exit at +500% ───────────────────────────────────────────
        if pnl_pct >= self.FULL_EXIT_AT_500:
            logger.info(f"🚀 FULL EXIT (500%): ${trade.token.symbol} at {pnl_pct*100:+.1f}%")
            return True

        # ── 4. Graduated trailing stop ──────────────────────────────────────
        trailing_stop_pct = _trailing_stop_for_pnl(pnl_pct)
        drawdown_from_high = (trailing_high - current_price) / max(trailing_high, 1e-12)
        if drawdown_from_high >= trailing_stop_pct:
            logger.info(
                f"📉 TRAILING STOP ({trailing_stop_pct*100:.0f}%): "
                f"${trade.token.symbol} | drew {drawdown_from_high*100:.1f}% from high | "
                f"P&L {pnl_pct*100:+.1f}%"
            )
            return True

        return False

    async def _close_position(
        self, trade: TradeResult, exit_price: float
    ) -> None:
        """Mark position as closed and record exit price."""
        trade.close(
            exit_price=exit_price,
            exit_tx=f"EXIT_{trade.tx_hash}_{int(time.time())}",
        )
        pnl_str = f"{(trade.realized_pnl_pct or 0)*100:+.1f}%"
        logger.info(
            f"💰 CLOSED: ${trade.token.symbol} | {pnl_str} | "
            f"${trade.realized_pnl_usd:+.2f}"
        )

    async def _get_current_price(self, trade: TradeResult) -> float | None:
        if self._price_fetcher:
            try:
                return await self._price_fetcher(
                    trade.token.address, trade.token.chain.value
                )
            except Exception as exc:
                logger.warning(f"Price fetch failed for ${trade.token.symbol}: {exc}")
        return None

    @property
    def open_positions(self) -> list[TradeResult]:
        return [t for t in self._positions if t.status == TradeStatus.OPEN]
