"""
Chain Analyst — on-chain data ingestion for Spectrolite.
Pulls volume anomalies, holder activity, and smart-money flows.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class VolumeAnomaly:
    address: str
    symbol: str
    chain: str
    price_usd: float
    volume_5m: float
    volume_1h: float
    volume_z_score: float         # standard deviations above rolling mean
    price_velocity: float         # % price change per minute
    liquidity_usd: float
    holder_count: int
    holder_delta: float           # holder count change (past 5 min)
    liquidity_ratio: float        # liquidity / market_cap
    bonding_curve_pct: float      # Pump.fun progress 0-100
    is_new_launch: bool = False


DEXSCREENER_BASE = "https://api.dexscreener.com/latest"
BIRDEYE_BASE = "https://public-api.birdeye.so"
PUMPFUN_WSS = "wss://pumpportal.fun/api/data"


class ChainAnalyst:
    """
    Continuously monitors all supported chains for volume anomalies,
    new token launches, and smart-money flows.
    """

    def __init__(
        self,
        birdeye_api_key: str = "",
        nansen_api_key: str = "",
    ) -> None:
        self._birdeye_key = birdeye_api_key
        self._nansen_key = nansen_api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {}
            if self._birdeye_key:
                headers["X-API-KEY"] = self._birdeye_key
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    # ── Public surface ──────────────────────────────────────────────────────

    async def get_volume_anomalies(
        self,
        chains: list[str] | None = None,
        z_score_threshold: float = 2.5,
        max_results: int = 30,
    ) -> list[dict[str, Any]]:
        """
        Poll DexScreener and Birdeye for tokens showing abnormal volume spikes.
        Returns raw signal dicts ready for SignalFusionEngine.
        """
        tasks = [
            self._dexscreener_boosted(),
            self._pumpfun_new_graduates(),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        anomalies: list[dict[str, Any]] = []
        for r in results:
            if isinstance(r, list):
                anomalies.extend(r)

        # Filter by z-score
        filtered = [a for a in anomalies if a.get("volume_z_score", 0) >= z_score_threshold]
        return filtered[:max_results]

    async def get_holder_activity(self, token_address: str, chain: str = "solana") -> dict[str, Any]:
        """
        Fetch holder distribution & smart-money inflow/outflow from Birdeye.
        """
        sess = await self._sess()
        url = f"{BIRDEYE_BASE}/defi/token_overview"
        try:
            async with sess.get(url, params={"address": token_address}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", {})
        except Exception as exc:
            logger.warning(f"Birdeye holder fetch failed: {exc}")
        return {}

    # ── DexScreener ─────────────────────────────────────────────────────────

    async def _dexscreener_boosted(self) -> list[dict[str, Any]]:
        sess = await self._sess()
        url = f"{DEXSCREENER_BASE}/dex/search/?q=pump"
        results: list[dict[str, Any]] = []
        try:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                for pair in data.get("pairs", []):
                    results.append(self._normalise_dexscreener_pair(pair))
        except Exception as exc:
            logger.warning(f"DexScreener fetch failed: {exc}")
        return results

    def _normalise_dexscreener_pair(self, pair: dict[str, Any]) -> dict[str, Any]:
        vol5m = pair.get("volume", {}).get("m5", 0) or 0
        vol1h = pair.get("volume", {}).get("h1", 0) or 0
        # Simple z-score approximation: vol5m relative to h1 average
        avg_5m_expected = vol1h / 12.0 if vol1h else 1
        z = (vol5m - avg_5m_expected) / max(avg_5m_expected, 1)
        return {
            "address": pair.get("baseToken", {}).get("address", ""),
            "symbol": pair.get("baseToken", {}).get("symbol", "???"),
            "chain": pair.get("chainId", "solana"),
            "price_usd": float(pair.get("priceUsd", 0) or 0),
            "liquidity_usd": float((pair.get("liquidity") or {}).get("usd", 0) or 0),
            "volume_5m": vol5m,
            "volume_1h": vol1h,
            "volume_z_score": max(z, 0.0),
            "price_velocity": float(pair.get("priceChange", {}).get("m5", 0) or 0),
            "holder_count": 0,   # enriched via Birdeye
            "holder_delta": 0.0,
            "liquidity_ratio": 0.1,
            "bonding_curve_pct": 0.0,
            "scam_probability": 0.3,   # default; overwritten by ScamSlayer
            "scam_probability_penalty": 30.0,
        }

    # ── Pump.fun firehose ───────────────────────────────────────────────────

    async def _pumpfun_new_graduates(self) -> list[dict[str, Any]]:
        """
        In production: subscribe to Pump.fun WebSocket for graduation events.
        Returns recently graduated tokens that crossed the bonding curve.
        """
        return []   # WebSocket listener runs in a dedicated background task

    async def subscribe_pumpfun_firehose(self, callback) -> None:
        """
        Persistent long-running WebSocket subscription to Pump.fun graduation events.
        Automatically reconnects with exponential back-off on disconnect.
        Each event triggers: await callback(token_dict)
        """
        import json as _json
        import websockets  # type: ignore

        BACKOFF_INITIAL = 2.0
        BACKOFF_MAX = 120.0
        SUBSCRIPTION_MSG = '{"method":"subscribeNewToken"}'

        backoff = BACKOFF_INITIAL
        attempt = 0

        while True:
            attempt += 1
            logger.info(f"[PumpFun] Connecting to firehose (attempt {attempt})…")
            try:
                async with websockets.connect(
                    PUMPFUN_WSS,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    await ws.send(SUBSCRIPTION_MSG)
                    backoff = BACKOFF_INITIAL   # reset back-off on successful connect
                    logger.info("[PumpFun] Firehose connected ✓")

                    async for raw in ws:
                        try:
                            evt = _json.loads(raw)
                            normalised = self._normalise_pumpfun_event(evt)
                            if normalised:
                                await callback(normalised)
                        except Exception as parse_exc:
                            logger.debug(f"[PumpFun] Parse error: {parse_exc}")

            except Exception as exc:
                logger.warning(
                    f"[PumpFun] Firehose disconnected: {exc} — "
                    f"reconnecting in {backoff:.0f}s"
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)

    def _normalise_pumpfun_event(self, evt: dict[str, Any]) -> dict[str, Any] | None:
        """Normalise a raw Pump.fun WebSocket event into a VolumeAnomaly dict."""
        # Pump.fun graduation payload shape varies — extract best-effort fields
        mint = evt.get("mint") or evt.get("tokenAddress") or evt.get("address")
        if not mint:
            return None
        symbol = evt.get("symbol") or evt.get("name") or "???"
        market_cap = float(evt.get("marketCapSol", 0) or 0) * 150   # approx SOL→USD
        liquidity = float(evt.get("vSolInBondingCurve", 0) or 0) * 150
        bonding_pct = float(evt.get("bondingCurveProgress", 0) or 0)
        return {
            "address": mint,
            "symbol": symbol,
            "chain": "solana",
            "price_usd": float(evt.get("price", 0) or 0),
            "liquidity_usd": liquidity,
            "volume_5m": 0.0,
            "volume_1h": 0.0,
            "volume_z_score": 3.0,   # new launches always spike above baseline
            "price_velocity": 0.0,
            "holder_count": int(evt.get("holderCount", 0) or 0),
            "holder_delta": 0.0,
            "liquidity_ratio": liquidity / max(market_cap, 1),
            "bonding_curve_pct": bonding_pct,
            "is_new_launch": True,
            "scam_probability": 0.4,
            "scam_probability_penalty": 40.0,
        }

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
