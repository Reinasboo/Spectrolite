"""
Alpha Wallet Surveillance — Spectrolite's Wallet Whisperer.
Tracks 10-20 elite wallets and scores their alpha signals.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

NANSEN_BASE = "https://api.nansen.ai/v1"


@dataclass
class WalletSignal:
    wallet_address: str
    token_address: str
    token_symbol: str
    chain: str
    action: str                   # "buy" | "sell"
    amount_usd: float
    timestamp: float              # unix timestamp
    alpha_score: float = 0.0


@dataclass
class TrackedWallet:
    address: str
    label: str
    wins_30d: int = 0
    losses_30d: int = 0
    avg_roi_30d: float = 0.0
    win_streak: int = 0
    recent_signals: list[WalletSignal] = field(default_factory=list)
    alpha_score: float = 0.0
    meme_themes: list[str] = field(default_factory=list)

    def update_alpha_score(
        self,
        recency_weight: float = 3.0,
        copy_saturation: float = 0.0,
    ) -> float:
        win_rate = self.wins_30d / max(self.wins_30d + self.losses_30d, 1)
        streak_bonus = self.win_streak * 5.0
        recency_decay = recency_weight if self.win_streak > 0 else 1.0
        raw = (win_rate * 100 + streak_bonus) * recency_decay - copy_saturation
        self.alpha_score = max(raw, 0.0)
        return self.alpha_score


class WalletTracker:
    """
    Maintains a dynamic watchlist of elite wallets.
    Sources: Nansen Smart Money API + manual curation.
    """

    def __init__(
        self,
        nansen_api_key: str = "",
        initial_wallets: list[dict[str, Any]] | None = None,
    ) -> None:
        self._key = nansen_api_key
        self._watchlist: dict[str, TrackedWallet] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        if initial_wallets:
            for w in initial_wallets:
                self.add_wallet(w["address"], w.get("label", w["address"][:8]))

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"X-API-KEY": self._key} if self._key else {}
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    def add_wallet(self, address: str, label: str = "") -> TrackedWallet:
        if address not in self._watchlist:
            w = TrackedWallet(address=address, label=label or address[:8])
            self._watchlist[address] = w
        return self._watchlist[address]

    async def refresh_nansen_smart_money(self, limit: int = 20) -> None:
        """Pull top alpha wallets from Nansen Smart Money endpoint."""
        if not self._key:
            logger.warning("No Nansen API key; skipping smart money refresh")
            return
        sess = await self._sess()
        try:
            async with sess.get(
                f"{NANSEN_BASE}/smart-money/wallets",
                params={"limit": limit, "sort": "roi_30d"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for entry in data.get("data", []):
                        addr = entry.get("address", "")
                        w = self.add_wallet(addr, entry.get("label", ""))
                        w.wins_30d = entry.get("wins_30d", 0)
                        w.losses_30d = entry.get("losses_30d", 0)
                        w.avg_roi_30d = entry.get("avg_roi_30d", 0.0)
                        w.update_alpha_score()
                    logger.info(f"Nansen refresh: {len(self._watchlist)} wallets tracked")
        except Exception as exc:
            logger.error(f"Nansen refresh failed: {exc}")

    async def get_recent_buys(
        self,
        lookback_seconds: int = 300,
    ) -> list[WalletSignal]:
        """Return buy signals from all tracked wallets in the last N seconds."""
        cutoff = time.time() - lookback_seconds
        signals: list[WalletSignal] = []
        for wallet in self._watchlist.values():
            for sig in wallet.recent_signals:
                if sig.action == "buy" and sig.timestamp >= cutoff:
                    sig.alpha_score = wallet.alpha_score
                    signals.append(sig)
        return signals

    def ingest_on_chain_event(
        self,
        wallet_address: str,
        token_address: str,
        token_symbol: str,
        chain: str,
        action: str,
        amount_usd: float,
    ) -> None:
        """Called by chain listener when a tracked wallet transacts."""
        w = self._watchlist.get(wallet_address)
        if not w:
            return
        sig = WalletSignal(
            wallet_address=wallet_address,
            token_address=token_address,
            token_symbol=token_symbol,
            chain=chain,
            action=action,
            amount_usd=amount_usd,
            timestamp=time.time(),
        )
        w.recent_signals.append(sig)
        # Trim to last 200 signals
        w.recent_signals = w.recent_signals[-200:]

    @property
    def watchlist(self) -> list[TrackedWallet]:
        return list(self._watchlist.values())

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
