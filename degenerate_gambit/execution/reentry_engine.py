"""
Re-Entry Engine — bounces back into partially-exited positions.

When a scaled exit fires (e.g. 30% sold at 2x), the remaining position continues
to run. But if the token then dips 25-35% from the 2x high while volume
holds up (bullish structure intact), the freed capital from the partial exit
can re-enter for additional upside.

Re-entry conditions (all must be true):
  1. Trade was partially closed via a scaled exit (not a stop-loss)
  2. Current price has dipped 25-35% from the partial exit price
  3. Volume remains elevated (volume_z_score >= 1.5)
  4. Scam probability still < 35%
  5. Not more than 30 minutes since partial exit
  6. Re-entry hasn't already been attempted for this trade
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import ScoredToken, TradeResult
    from .trade_executor import TradeExecutor

logger = logging.getLogger(__name__)


@dataclass
class PartialExitRecord:
    """Logged when a scaled exit takes partial profit."""
    token_address: str
    symbol: str
    chain: str
    exit_price: float
    exit_timestamp: float = field(default_factory=time.time)
    re_entry_attempted: bool = False


class ReEntryEngine:
    """
    Monitors recently partially-exited tokens for bounce re-entry setups.

    The re-entry uses the freed capital from the partial exit (30% of original
    size) as the new position size — so risk exposure stays constant.
    """

    DIP_MIN_PCT = 0.25        # minimum dip from partial-exit price to qualify
    DIP_MAX_PCT = 0.40        # maximum dip (deeper = worse structure)
    VOLUME_Z_THRESHOLD = 1.5  # volume must still be elevated
    MAX_WAIT_MINUTES = 30     # cancel watch after this window
    SCAM_PROB_MAX = 0.35

    def __init__(
        self,
        price_fetcher: Callable,      # async fn(address, chain) → float
        volume_fetcher: Callable,     # async fn(address, chain) → float (z-score)
        executor: "TradeExecutor",
    ) -> None:
        self._price_fn = price_fetcher
        self._volume_fn = volume_fetcher
        self._executor = executor
        self._watching: dict[str, PartialExitRecord] = {}   # address → record
        self._token_cache: dict[str, "ScoredToken"] = {}    # address → last ScoredToken
        self._running = False

    # ── Public API ─────────────────────────────────────────────────────────

    def register_partial_exit(
        self,
        token: "ScoredToken",
        exit_price: float,
    ) -> None:
        """
        Called by PositionManager when a scaled exit fires.
        Starts watching for a bounce re-entry opportunity.
        """
        rec = PartialExitRecord(
            token_address=token.address,
            symbol=token.symbol,
            chain=token.chain.value,
            exit_price=exit_price,
        )
        self._watching[token.address] = rec
        self._token_cache[token.address] = token
        logger.info(
            f"ReEntryEngine: watching ${token.symbol} for bounce "
            f"from partial exit @ ${exit_price:.6f}"
        )

    async def run(self) -> None:
        """Background task. Check all watched tokens every 60 seconds."""
        self._running = True
        while self._running:
            try:
                await self._scan_bounces()
            except Exception as exc:
                logger.error(f"ReEntryEngine scan error: {exc}")
            await asyncio.sleep(60)

    def stop(self) -> None:
        self._running = False

    # ── Internals ──────────────────────────────────────────────────────────

    async def _scan_bounces(self) -> None:
        expired_keys: list[str] = []
        for address, rec in list(self._watching.items()):
            # Expire old watches
            hold_minutes = (time.time() - rec.exit_timestamp) / 60
            if hold_minutes > self.MAX_WAIT_MINUTES or rec.re_entry_attempted:
                expired_keys.append(address)
                continue

            try:
                await self._evaluate_bounce(address, rec)
            except Exception as exc:
                logger.debug(f"ReEntry eval failed for {rec.symbol}: {exc}")

        for k in expired_keys:
            self._watching.pop(k, None)
            self._token_cache.pop(k, None)

    async def _evaluate_bounce(self, address: str, rec: PartialExitRecord) -> None:
        current_price = await self._price_fn(address, rec.chain)
        if current_price is None:
            return

        dip_pct = (rec.exit_price - current_price) / rec.exit_price

        # Check dip is in the sweet spot
        if not (self.DIP_MIN_PCT <= dip_pct <= self.DIP_MAX_PCT):
            return

        # Check volume is still elevated
        volume_z = await self._volume_fn(address, rec.chain)
        if volume_z < self.VOLUME_Z_THRESHOLD:
            logger.debug(
                f"ReEntry: ${rec.symbol} dipped {dip_pct*100:.1f}% but volume weak "
                f"(z={volume_z:.1f}) — skipping"
            )
            return

        # Retrieve cached token for scam check
        token = self._token_cache.get(address)
        if token and token.scam_probability >= self.SCAM_PROB_MAX:
            logger.info(f"ReEntry: ${rec.symbol} scam probability too high — skipping")
            rec.re_entry_attempted = True
            return

        logger.info(
            f"🔁 RE-ENTRY SIGNAL: ${rec.symbol} @ ${current_price:.6f} | "
            f"dipped {dip_pct*100:.1f}% from partial exit price | vol_z={volume_z:.1f}"
        )

        rec.re_entry_attempted = True

        if token:
            # Execute re-entry — update token price to current
            import copy
            refreshed_token = copy.replace(token, price_usd=current_price)  # type: ignore[call-arg]
            result = await self._executor.enter_position(refreshed_token)
            if result:
                logger.info(f"✅ RE-ENTERED ${rec.symbol}: ${result.size_usd:.2f}")
