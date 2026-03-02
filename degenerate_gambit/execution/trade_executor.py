"""
Trade Executor — validates, sizes, and executes entries via Padre Terminal.
Never skips the pre-flight checklist.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING

from ..config import get_settings
from ..models import OrderType, PersonalityMode, ScoredToken, TradeResult, TradeStatus
from ..scam_shield import ScamSlayer

if TYPE_CHECKING:
    from .padre_session import PadreSessionManager
    from ..gamification import ModeManager, LevelSystem, MemeReporter

logger = logging.getLogger(__name__)
_cfg = get_settings()


class MempoolMonitor:
    """
    Polls live mempool / priority fee data and returns the 75th-percentile
    fee so SPECTROLITE's transactions are reliably included without over-paying.

    Solana: getRecentPrioritizationFees RPC
    EVM chains: eth_maxPriorityFeePerGas
    """

    # Fallback fees used when RPC is unavailable
    _FALLBACK_FEES: dict[str, float] = {
        "solana":   0.001,
        "ethereum": 25.0,
        "base":      0.02,
        "bnb":       3.0,
    }
    # Fees are cached per chain to avoid RPC calls on every trade
    _cache: dict[str, tuple[float, float]] = {}   # chain → (fee, timestamp)
    _cache_ttl: float = 30.0                       # seconds

    def __init__(self) -> None:
        import aiohttp
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> "aiohttp.ClientSession":
        import aiohttp
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def optimal_fee(self, chain: str) -> float:
        """Return 75th-percentile priority fee for chain. Fetches fresh data every 30s."""
        now = time.time()
        cached = self._cache.get(chain)
        if cached and now - cached[1] < self._cache_ttl:
            return cached[0]

        fee = await self._fetch_fee(chain)
        self._cache[chain] = (fee, now)
        return fee

    async def _fetch_fee(self, chain: str) -> float:
        rpc = _cfg.chains.__dict__.get(chain, {}).get("rpc_url", "") if hasattr(_cfg, "chains") else ""
        if chain == "solana" and rpc:
            return await self._solana_fee(rpc)
        if chain in ("ethereum", "base", "bnb") and rpc:
            return await self._evm_fee(rpc)
        return self._FALLBACK_FEES.get(chain, 0.01)

    async def _solana_fee(self, rpc: str) -> float:
        try:
            import aiohttp
            body = {"jsonrpc": "2.0", "id": 1, "method": "getRecentPrioritizationFees", "params": []}
            sess = await self._get_session()
            async with sess.post(rpc, json=body, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                fees = [entry["prioritizationFee"] for entry in data.get("result", [])]
                if fees:
                    fees.sort()
                    p75_idx = int(len(fees) * 0.75)
                    return fees[p75_idx] / 1_000_000   # microlamports → SOL
        except Exception as exc:
            logger.debug(f"Solana fee fetch failed: {exc}")
        return self._FALLBACK_FEES["solana"]

    async def _evm_fee(self, rpc: str) -> float:
        try:
            import aiohttp
            body = {"jsonrpc": "2.0", "id": 1, "method": "eth_maxPriorityFeePerGas", "params": []}
            sess = await self._get_session()
            async with sess.post(rpc, json=body, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                gwei = int(data["result"], 16) / 1e9
                return gwei * 1.25   # add 25% buffer on top of current tip
        except Exception as exc:
            logger.debug(f"EVM fee fetch failed: {exc}")
        return self._FALLBACK_FEES.get("ethereum", 25.0)


# Keep the old name as an alias so references still work
BribeCalculator = MempoolMonitor


class PositionSizer:
    """
    Kelly Criterion fractional position sizing.

    Uses the formula:
        kelly_f = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
    Then applies a 25% Kelly fraction (quarter-Kelly) to avoid over-betting,
    further multiplied by the current personality mode multiplier.

    Falls back to fixed fractional when trade history is insufficient (<20 trades).
    """

    MIN_HISTORY_FOR_KELLY = 20
    KELLY_FRACTION = 0.25        # quarter-Kelly to limit variance
    MAX_POSITION_FRACTION = 0.20 # hard cap: never exceed 20% of portfolio bucket

    def calculate(
        self,
        meme_score: float,
        mode: PersonalityMode,
        win_streak: int,
        portfolio_rotation_usd: float,
        portfolio_moonshot_usd: float,
        mode_size_multiplier: float = 1.0,
        recent_pnls: list[float] | None = None,   # recent trade PnL % list
    ) -> float:
        is_moonshot = meme_score >= _cfg.risk.high_conviction_pct * 100
        bucket = portfolio_moonshot_usd if is_moonshot else portfolio_rotation_usd

        kelly_f = self._kelly_fraction(recent_pnls or [])

        # Apply quarter-Kelly and mode multiplier
        fraction = min(kelly_f * self.KELLY_FRACTION * mode_size_multiplier,
                       self.MAX_POSITION_FRACTION)
        size = bucket * max(fraction, 0.01)   # minimum 1% of bucket

        logger.debug(
            f"Kelly sizing: kelly_f={kelly_f:.3f} quarter_kelly={kelly_f*self.KELLY_FRACTION:.3f} "
            f"mode_mult={mode_size_multiplier:.2f} → {fraction*100:.1f}% of bucket → ${size:.2f}"
        )
        return size

    def _kelly_fraction(self, recent_pnls: list[float]) -> float:
        """Compute full Kelly fraction from recent trade outcomes."""
        if len(recent_pnls) < self.MIN_HISTORY_FOR_KELLY:
            # Not enough history — use configured fixed fraction
            return _cfg.risk.standard_entry_pct

        wins = [p for p in recent_pnls if p > 0]
        losses = [abs(p) for p in recent_pnls if p <= 0]

        if not wins or not losses:
            return _cfg.risk.standard_entry_pct

        win_rate = len(wins) / len(recent_pnls)
        loss_rate = 1 - win_rate
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)

        kelly = (win_rate * avg_win - loss_rate * avg_loss) / max(avg_win, 1e-6)
        return max(kelly, 0.01)   # floor at 1% — never bet negative


class RiskManager:
    """Enforces hard risk limits before any trade is opened."""

    def __init__(self, max_concurrent: int = 5) -> None:
        self._max_concurrent = max_concurrent
        self._open_count = 0

    def can_open_position(self, token: ScoredToken) -> bool:
        if self._open_count >= self._max_concurrent:
            logger.warning(f"Risk limit: max {self._max_concurrent} concurrent positions reached")
            return False
        if token.scam_probability >= _cfg.scam_shield.max_scam_probability:
            logger.warning(f"Risk limit: scam probability {token.scam_probability:.0%} too high")
            return False
        return True

    def position_opened(self) -> None:
        self._open_count += 1

    def position_closed(self) -> None:
        self._open_count = max(0, self._open_count - 1)


class TradeExecutor:
    """
    Validates, sizes, and executes trade entries.
    Integrates: ScamSlayer pre-flight, RiskManager, PositionSizer,
    ModeManager, LevelSystem, PadreTerminal, MemeChronicler.
    """

    def __init__(
        self,
        padre: "PadreSessionManager",
        scam_slayer: ScamSlayer,
        mode_manager: "ModeManager",
        level_system: "LevelSystem",
        meme_reporter: "MemeReporter",
        risk_manager: RiskManager | None = None,
    ) -> None:
        self._padre = padre
        self._scam = scam_slayer
        self._modes = mode_manager
        self._levels = level_system
        self._reporter = meme_reporter
        self._risk = risk_manager or RiskManager()
        self._sizer = PositionSizer()
        self._mempool = MempoolMonitor()
        # Simulated portfolio buckets (initialised from config)
        self._rotation_usd = _cfg.portfolio.total_capital_usd * _cfg.portfolio.rotation_allocation
        self._moonshot_usd = _cfg.portfolio.total_capital_usd * _cfg.portfolio.moonshot_allocation
        # Rolling recent trade PnLs for Kelly sizing
        self._recent_pnls: list[float] = []

    async def enter_position(self, token: ScoredToken) -> TradeResult | None:
        """
        Full pre-flight → size → execute flow.
        Returns TradeResult or None if checks fail.
        """
        mode = self._modes.current_mode
        mode_params = self._modes.params

        # ── Pre-flight: honeypot simulation ────────────────────────────────
        sim_ok = await self._scam.dynamic_simulation(token)
        if not sim_ok:
            logger.warning(f"⛔ HONEYPOT: Aborting entry for ${token.symbol}")
            return None

        # ── Pre-flight: risk limits ────────────────────────────────────────
        if not self._risk.can_open_position(token):
            return None

        # ── Position sizing (Kelly Criterion) ──────────────────────────────
        size_usd = self._sizer.calculate(
            meme_score=token.total_meme_score,
            mode=mode,
            win_streak=self._levels.current_streak,
            portfolio_rotation_usd=self._rotation_usd,
            portfolio_moonshot_usd=self._moonshot_usd,
            mode_size_multiplier=mode_params.position_size_multiplier,
            recent_pnls=self._recent_pnls[-50:],   # use last 50 trades
        )

        # ── Mutation Layer ─────────────────────────────────────────────────
        mutation_applied = False
        if random.random() < _cfg.signals.mutation_probability:
            mult = random.uniform(*_cfg.signals.mutation_size_range)
            size_usd *= mult
            mutation_applied = True
            logger.info(
                f"🧬 MUTATION APPLIED: ${token.symbol} position boosted to ${size_usd:.0f} "
                f"(×{mult:.2f})"
            )

        # ── Anti-copy jitter ───────────────────────────────────────────────
        jitter = random.uniform(8, 45)
        await asyncio.sleep(jitter)

        # ── Execute swap ───────────────────────────────────────────────────
        try:
            priority_fee = await self._mempool.optimal_fee(token.chain.value)
            result = await self._padre.execute_swap(
                token_address=token.address,
                chain=token.chain.value,
                amount_usd=size_usd,
                slippage_pct=mode_params.slippage_tolerance,
                order_type=mode_params.order_type.value,
                priority_fee=priority_fee,
            )
        except Exception as exc:
            logger.error(f"Padre swap failed for ${token.symbol}: {exc}")
            return None

        # ── Build TradeResult ──────────────────────────────────────────────
        trade = TradeResult(
            token=token,
            order_type=mode_params.order_type,
            entry_price=token.price_usd,
            size_usd=size_usd,
            leverage=mode_params.max_leverage,
            tx_hash=result.get("tx_hash", ""),
            chain=token.chain,
            mode=mode,
            status=TradeStatus.OPEN,
            mutation_applied=mutation_applied,
            meme_score_at_entry=token.total_meme_score,
        )

        self._risk.position_opened()
        self._reporter.generate_entry_note(token, mode)
        logger.info(f"✅ ENTERED: ${token.symbol} | ${size_usd:.2f} | {mode.value}")
        return trade

    def record_trade_outcome(self, pnl_pct: float) -> None:
        """Feed closed trade P&L back into the Kelly sizing history."""
        self._recent_pnls.append(pnl_pct)
        if len(self._recent_pnls) > 200:
            self._recent_pnls = self._recent_pnls[-200:]
