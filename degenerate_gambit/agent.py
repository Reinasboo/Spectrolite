"""
SPECTROLITE — Degenerate Gambit v2.0
Main agent factory and entry point wiring.

Usage (programmatic):
    from degenerate_gambit.agent import create_agent, run_agent
    await run_agent()
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx  # type: ignore

from .agents import AgentContext, OverseerAgent
from .analysis import ChainAnalyst, CrossChainArbDetector, SentimentEngine, SignalFusionEngine
from .config import get_settings
from .execution import AESEncryptedBlob, PadreSessionManager, PositionManager, TradeExecutor, RiskManager
from .gamification import LevelSystem, MemeReporter, ModeManager
from .models import PortfolioState, PersonalityMode, Chain
from .notifications import send_telegram_message
from .persistence import TradeLogger
from .scam_shield import (
    DynamicSimulator, MEVBundleDetector, ScamSlayer, SocialScanner, StaticAnalyzer,
)
from .wallet import SwarmIntelligence, WalletTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("spectrolite")

_cfg = get_settings()


def _build_portfolio() -> PortfolioState:
    c = _cfg.portfolio
    total = c.total_capital_usd
    return PortfolioState(
        total_usd=total,
        moonshot_usd=total * c.moonshot_allocation,
        rotation_usd=total * c.rotation_allocation,
        arb_usd=total * c.arb_allocation,
        iron_coffin_usd=total * c.iron_coffin_allocation,
        mode=PersonalityMode.STANDARD,
    )


# Module-level shared HTTP client — single connection pool for the entire agent lifetime.
# Being module-level means it is shared even across multiple tests / REPL imports.
# Callers that want HTTP/2 can accept this client instead of creating their own.
_shared_http_client: httpx.AsyncClient | None = None


def get_shared_http_client() -> httpx.AsyncClient:
    """Return (lazily initialise) the global shared httpx.AsyncClient."""
    global _shared_http_client
    if _shared_http_client is None or _shared_http_client.is_closed:
        _shared_http_client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0),
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20,
                keepalive_expiry=30.0,
            ),
            headers={"User-Agent": "Spectrolite/2.0"},
            follow_redirects=True,
        )
    return _shared_http_client


async def create_agent() -> tuple[OverseerAgent, PadreSessionManager]:
    """
    Wire all components together and return a ready-to-run OverseerAgent.
    All sub-services that accept an httpx client receive the shared pool,
    eliminating redundant per-service connection pools.
    """
    cfg = _cfg
    # Ensure the shared pool is warmed up before sub-components start.
    _ = get_shared_http_client()

    # ── Encryption ──────────────────────────────────────────────────────────
    creds_enc = os.getenv("PADRE_CREDENTIALS_ENCRYPTED", "")
    wallet_key = os.getenv("WALLET_ENCRYPTION_KEY", "")
    if not creds_enc or not wallet_key:
        raise RuntimeError(
            "PADRE_CREDENTIALS_ENCRYPTED and WALLET_ENCRYPTION_KEY must be set in .env"
        )
    creds_blob = AESEncryptedBlob.from_env(creds_enc, wallet_key)

    # ── Padre Terminal ────────────────────────────────────────────────────
    padre = PadreSessionManager(encrypted_credentials=creds_blob)
    await padre.start()

    # ── Sub-components ────────────────────────────────────────────────────
    wallet_tracker = WalletTracker(
        nansen_api_key=os.getenv("NANSEN_API_KEY", ""),
    )
    await wallet_tracker.refresh_nansen_smart_money()

    chain_analyst = ChainAnalyst(
        birdeye_api_key=os.getenv("BIRDEYE_API_KEY", ""),
        nansen_api_key=os.getenv("NANSEN_API_KEY", ""),
    )
    sentiment_engine = SentimentEngine(
        apify_token=os.getenv("APIFY_API_TOKEN", ""),
        twitter_bearer=os.getenv("TWITTER_BEARER_TOKEN", ""),
        openai_key=os.getenv("OPENAI_API_KEY", ""),
        telegram_api_id=int(os.getenv("TELEGRAM_API_ID", "0")),
        telegram_api_hash=os.getenv("TELEGRAM_API_HASH", ""),
    )
    signal_fusion = SignalFusionEngine()

    scam_slayer = ScamSlayer(
        static=StaticAnalyzer(),
        simulator=DynamicSimulator(fork_url=os.getenv("ANVIL_FORK_URL", "")),
        social=SocialScanner(
            twitter_bearer_token=os.getenv("TWITTER_BEARER_TOKEN", ""),
            apify_token=os.getenv("APIFY_API_TOKEN", ""),
            scan_window_hours=cfg.scam_shield.social_scan_window_hours,
        ),
        mev=MEVBundleDetector(
            bloxroute_ws=os.getenv("BLOXROUTE_WS", ""),
        ),
        max_scam_probability=cfg.scam_shield.max_scam_probability,
        rpc_urls={
            "solana": os.getenv("SOLANA_RPC_URL", ""),
            "ethereum": os.getenv("ETHEREUM_RPC_URL", ""),
            "base": os.getenv("BASE_RPC_URL", ""),
            "bnb": os.getenv("BNB_RPC_URL", ""),
        },
    )

    mode_manager = ModeManager()
    level_system = LevelSystem()
    meme_reporter = MemeReporter(level_system=level_system)
    portfolio = _build_portfolio()
    risk_manager = RiskManager(max_concurrent=cfg.agent.max_concurrent_positions)

    trade_executor = TradeExecutor(
        padre=padre,
        scam_slayer=scam_slayer,
        mode_manager=mode_manager,
        level_system=level_system,
        meme_reporter=meme_reporter,
        risk_manager=risk_manager,
    )
    position_manager = PositionManager(risk_manager=risk_manager)
    swarm = SwarmIntelligence(wallet_tracker=wallet_tracker)
    arb_detector = CrossChainArbDetector()

    ctx = AgentContext(
        portfolio=portfolio,
        mode_manager=mode_manager,
        level_system=level_system,
        chain_analyst=chain_analyst,
        sentiment_engine=sentiment_engine,
        signal_fusion=signal_fusion,
        scam_slayer=scam_slayer,
        wallet_tracker=wallet_tracker,
        swarm=swarm,
        trade_executor=trade_executor,
        position_manager=position_manager,
        meme_reporter=meme_reporter,
        arb_detector=arb_detector,
    )

    overseer = OverseerAgent(ctx)
    logger.info("🚀 SPECTROLITE agent wired and ready")
    return overseer, padre


async def run_agent() -> None:
    """Top-level coroutine: wire → announce → run → teardown."""
    await send_telegram_message("🚀 <b>SPECTROLITE ONLINE</b> — Degenerate Gambit v2.0 starting")
    overseer, padre = await create_agent()
    try:
        await overseer.run()
    finally:
        await padre.close()
        # Gracefully close the shared HTTP connection pool
        global _shared_http_client
        if _shared_http_client and not _shared_http_client.is_closed:
            await _shared_http_client.aclose()
            _shared_http_client = None
        await send_telegram_message("🛑 <b>SPECTROLITE OFFLINE</b> — agent stopped")
