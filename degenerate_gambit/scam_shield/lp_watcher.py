"""
LP Liquidity Watcher — real-time post-entry protection.

Polls LP position size every 90 seconds while a position is open.
Triggers immediate emergency exit if liquidity drops >15% in any 5-minute window.
This catches the most lethal rug pattern: LP removal AFTER you buy.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

import aiohttp

logger = logging.getLogger(__name__)

DEXSCREENER_BASE = "https://api.dexscreener.com/latest"


@dataclass
class LiquiditySnapshot:
    token_address: str
    chain: str
    liquidity_usd: float
    timestamp: float = field(default_factory=time.time)


class LiquidityWatcher:
    """
    Continuously monitors on-chain LP depth for all open positions.

    Algorithm:
      1. Every 90 seconds, fetch current liquidity for each watched token.
      2. Compare to the liquidity recorded in the last 5-minute window.
      3. If drop >= 15%: fire the emergency_callback immediately.
      4. Callback should trigger a market-order exit in PositionManager.
    """

    POLL_INTERVAL_SECONDS = 90
    RUG_THRESHOLD_PCT = 0.15          # 15% LP drop → emergency exit
    WINDOW_SECONDS = 300              # 5-minute comparison window

    def __init__(
        self,
        emergency_callback: Callable[[str, str, float], None],
    ) -> None:
        """
        Args:
            emergency_callback: async fn(token_address, chain, current_liquidity_usd)
                                 called when a rug threshold is breached.
        """
        self._callback = emergency_callback
        self._watched: dict[str, str] = {}           # address → chain
        self._history: dict[str, list[LiquiditySnapshot]] = {}
        self._running = False
        self._session: aiohttp.ClientSession | None = None

    # ── Public API ─────────────────────────────────────────────────────────

    def watch(self, token_address: str, chain: str) -> None:
        """Start monitoring a token. Called when a position is opened."""
        self._watched[token_address] = chain
        self._history[token_address] = []
        logger.debug(f"LiquidityWatcher: now watching {token_address} on {chain}")

    def unwatch(self, token_address: str) -> None:
        """Stop monitoring a token. Called when a position is closed."""
        self._watched.pop(token_address, None)
        self._history.pop(token_address, None)

    async def run(self) -> None:
        """Long-running background task. Launch via asyncio.create_task()."""
        self._running = True
        logger.info("LiquidityWatcher started.")
        while self._running:
            try:
                await self._poll_all()
            except Exception as exc:
                logger.error(f"LiquidityWatcher poll error: {exc}")
            await asyncio.sleep(self.POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False

    # ── Internals ──────────────────────────────────────────────────────────

    async def _poll_all(self) -> None:
        if not self._watched:
            return
        tasks = [
            self._check_token(addr, chain)
            for addr, chain in list(self._watched.items())
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_token(self, address: str, chain: str) -> None:
        liquidity = await self._fetch_liquidity(address, chain)
        if liquidity is None:
            return

        snap = LiquiditySnapshot(address, chain, liquidity)
        history = self._history.setdefault(address, [])
        history.append(snap)

        # Keep only last 10 minutes of snapshots
        cutoff = time.time() - 600
        self._history[address] = [s for s in history if s.timestamp >= cutoff]

        # Compare current value to the window-start value
        window_start_snaps = [
            s for s in self._history[address]
            if s.timestamp >= time.time() - self.WINDOW_SECONDS
        ]
        if len(window_start_snaps) < 2:
            return

        baseline = window_start_snaps[0].liquidity_usd
        if baseline <= 0:
            return

        drop_pct = (baseline - liquidity) / baseline
        if drop_pct >= self.RUG_THRESHOLD_PCT:
            logger.warning(
                f"🚨 RUG DETECTED: {address} on {chain} | "
                f"LP dropped {drop_pct*100:.1f}% in {self.WINDOW_SECONDS}s | "
                f"${baseline:,.0f} → ${liquidity:,.0f} — EMERGENCY EXIT"
            )
            # Fire callback on the event loop (don't await inside the task)
            asyncio.create_task(self._callback(address, chain, liquidity))  # type: ignore[arg-type]
            self.unwatch(address)   # stop watching — exit is incoming

    async def _fetch_liquidity(self, address: str, chain: str) -> float | None:
        sess = await self._get_session()
        url = f"{DEXSCREENER_BASE}/dex/tokens/{address}"
        try:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                pairs = data.get("pairs") or []
                if not pairs:
                    return None
                # Use the highest-liquidity pair for this token
                best = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd", 0) or 0))
                return float((best.get("liquidity") or {}).get("usd", 0) or 0)
        except Exception as exc:
            logger.debug(f"LP fetch failed for {address}: {exc}")
        return None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        self.stop()
        if self._session and not self._session.closed:
            await self._session.close()
