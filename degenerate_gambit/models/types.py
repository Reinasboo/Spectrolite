"""
Core data models for Spectrolite / Degenerate Gambit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Chain(str, Enum):
    SOLANA = "solana"
    ETHEREUM = "ethereum"
    BASE = "base"
    BNB = "bnb"


class OrderType(str, Enum):
    INSTANT_MARKET = "instant_market"
    TWAP = "twap"
    MEME_BUNDLE = "meme_bundle"
    TRAILING_STOP = "trailing_stop"
    SCALED_EXIT = "scaled_exit"


class TradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    FAILED = "failed"
    SIMULATED = "simulated"


class PersonalityMode(str, Enum):
    APE = "APE MODE"
    SNIPER = "SNIPER MODE"
    ZEN = "ZEN MODE"
    CASINO = "CASINO MODE"
    SOBRIETY = "SOBRIETY MODE"
    STANDARD = "STANDARD"


class DangerLevel(str, Enum):
    APPROVED = "DEGEN APPROVED"
    CAUTION = "PROCEED WITH CAUTION"
    HIGH_RISK = "HIGH RISK — USE TEST BUY"
    LIKELY_SCAM = "LIKELY SCAM — ABORT RECOMMENDED"
    DEFINITE_RUG = "DEFINITE RUG — BLACKLISTED"


@dataclass
class MemeScore:
    base_theme_bonus: float = 0.0
    celebrity_endorsement: float = 0.0
    visual_hype_score: float = 0.0
    social_velocity_index: float = 0.0
    narrative_alignment: float = 0.0
    scam_probability_penalty: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.base_theme_bonus
            + self.celebrity_endorsement
            + self.visual_hype_score
            + self.social_velocity_index
            + self.narrative_alignment
            - self.scam_probability_penalty
        )

    def __str__(self) -> str:
        return (
            f"MemeScore(total={self.total:.1f}, "
            f"theme={self.base_theme_bonus}, celeb={self.celebrity_endorsement}, "
            f"visual={self.visual_hype_score}, velocity={self.social_velocity_index}, "
            f"narrative={self.narrative_alignment}, scam_penalty={self.scam_probability_penalty})"
        )


@dataclass
class ScamAnalysis:
    scam_probability: float = 0.0
    static_critical_findings: list[str] = field(default_factory=list)
    honeypot_detected: bool = False
    sell_tax_pct: float = 0.0
    rug_warnings_found: int = 0
    mev_bundle_detected: bool = False
    ownership_renounced: bool = True
    mint_function_present: bool = False
    blacklist_capability: bool = False
    proxy_upgradable: bool = False

    @property
    def danger_level(self) -> DangerLevel:
        p = self.scam_probability
        if p <= 0.20:
            return DangerLevel.APPROVED
        if p <= 0.40:
            return DangerLevel.CAUTION
        if p <= 0.60:
            return DangerLevel.HIGH_RISK
        if p <= 0.80:
            return DangerLevel.LIKELY_SCAM
        return DangerLevel.DEFINITE_RUG

    def danger_meter_str(self) -> str:
        d = self.danger_level
        icons = {
            DangerLevel.APPROVED: "🟢 💰",
            DangerLevel.CAUTION: "🟡 ⚠️",
            DangerLevel.HIGH_RISK: "🟠 ☠️",
            DangerLevel.LIKELY_SCAM: "🔴 💀",
            DangerLevel.DEFINITE_RUG: "⛔ 🚨",
        }
        return f"[{self.scam_probability*100:.0f}%] {icons[d]} {d.value}"


@dataclass
class PumpPrediction:
    pump_probability: float = 0.0
    confidence_interval: tuple[float, float] = (0.0, 1.0)
    suggested_entry_price: float = 0.0
    horizon_minutes: int = 15

    @property
    def is_confident(self) -> bool:
        return self.pump_probability >= 0.72


@dataclass
class ScoredToken:
    """A candidate token that has passed multi-signal scoring."""
    address: str
    symbol: str
    chain: Chain
    price_usd: float
    liquidity_usd: float
    volume_5m: float
    volume_1h: float
    holder_count: int
    meme_score: MemeScore
    scam_analysis: ScamAnalysis
    pump_prediction: PumpPrediction
    viral_thesis: str = ""
    bonding_curve_pct: float = 0.0   # Pump.fun progress
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_meme_score(self) -> float:
        return self.meme_score.total

    @property
    def scam_probability(self) -> float:
        return self.scam_analysis.scam_probability

    @property
    def is_moonshot_candidate(self) -> bool:
        return self.total_meme_score >= 85

    def summary(self) -> str:
        return (
            f"[{self.symbol}@{self.chain.value.upper()}] "
            f"Meme={self.total_meme_score:.0f} "
            f"Scam={self.scam_probability*100:.0f}% "
            f"Pump={self.pump_prediction.pump_probability*100:.0f}% "
            f"— {self.viral_thesis}"
        )


@dataclass
class TradeResult:
    token: ScoredToken
    order_type: OrderType
    entry_price: float
    size_usd: float
    leverage: float
    tx_hash: str
    chain: Chain
    mode: PersonalityMode
    status: TradeStatus = TradeStatus.OPEN
    exit_price: Optional[float] = None
    realized_pnl_usd: Optional[float] = None
    realized_pnl_pct: Optional[float] = None
    exit_tx_hash: Optional[str] = None
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    mutation_applied: bool = False
    meme_score_at_entry: float = 0.0

    @property
    def is_winner(self) -> bool:
        return (self.realized_pnl_pct or 0) > 0

    def close(self, exit_price: float, exit_tx: str) -> None:
        self.exit_price = exit_price
        self.exit_tx_hash = exit_tx
        self.closed_at = datetime.utcnow()
        self.status = TradeStatus.CLOSED
        self.realized_pnl_pct = (exit_price - self.entry_price) / self.entry_price
        self.realized_pnl_usd = self.size_usd * self.realized_pnl_pct * self.leverage

    def meme_report(self) -> str:
        pnl_str = f"{self.realized_pnl_pct*100:+.0f}%" if self.realized_pnl_pct else "OPEN"
        return (
            f"TRADE CLOSED: ${self.token.symbol} | "
            f"Entry: ${self.entry_price:.8f} | "
            f"Exit: ${self.exit_price:.8f if self.exit_price else 0:.8f} | "
            f"PnL: {pnl_str}"
        )


@dataclass
class PortfolioState:
    total_usd: float
    moonshot_usd: float
    rotation_usd: float
    arb_usd: float
    iron_coffin_usd: float
    open_positions: list[TradeResult] = field(default_factory=list)
    closed_trades: list[TradeResult] = field(default_factory=list)
    win_streak: int = 0
    loss_streak: int = 0
    mode: PersonalityMode = PersonalityMode.STANDARD

    @property
    def drawdown_pct(self) -> float:
        """Percentage lost from peak (stub — tracked externally)."""
        return 0.0

    @property
    def win_rate(self) -> float:
        closed = [t for t in self.closed_trades if t.status == TradeStatus.CLOSED]
        if not closed:
            return 0.0
        return sum(1 for t in closed if t.is_winner) / len(closed)

    @property
    def total_wins(self) -> int:
        return sum(1 for t in self.closed_trades if t.is_winner)

    @property
    def total_trades(self) -> int:
        return len(self.closed_trades)
