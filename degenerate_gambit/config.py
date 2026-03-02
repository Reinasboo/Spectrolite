"""
Configuration loader for Spectrolite / Degenerate Gambit.
Reads config.yaml and exposes a typed Settings object.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

load_dotenv()

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        raw = f.read()
    # Expand ${VAR} references from environment
    import re
    def _sub(m: re.Match) -> str:
        key: str = m.group(1) or ""
        fallback: str = m.group(0) or ""
        return os.environ.get(key, fallback)  # type: ignore[return-value]
    raw = re.sub(r"\$\{([^}]+)\}", _sub, raw)
    return yaml.safe_load(raw)


class AgentConfig(BaseModel):
    name: str = "SPECTROLITE"
    codename: str = "Degenerate Gambit"
    version: str = "2.0"
    personality: str = "degen"
    analysis_interval_seconds: int = 15
    max_concurrent_positions: int = 5
    heartbeat_interval_seconds: int = 240


class PortfolioConfig(BaseModel):
    total_capital_usd: float = 10_000
    moonshot_allocation: float = 0.50
    rotation_allocation: float = 0.30
    arb_allocation: float = 0.15
    iron_coffin_allocation: float = 0.05


class RiskConfig(BaseModel):
    tolerance: str = "insane"
    max_leverage: int = 10
    default_leverage: int = 3
    stop_loss_pct: float = 0.20
    take_profit_targets: list[float] = Field(default=[2.0, 5.0, 10.0])
    exit_pcts_at_targets: list[float] = Field(default=[0.30, 0.40, 0.30])
    max_portfolio_drawdown: float = 0.80
    standard_entry_pct: float = 0.03
    high_conviction_pct: float = 0.15


class SignalConfig(BaseModel):
    min_meme_score: int = 65
    moonshot_meme_score: int = 85
    pump_probability_threshold: float = 0.72
    min_wallet_consensus_pct: float = 0.65
    mutation_probability: float = 0.15
    mutation_size_range: list[float] = Field(default=[1.4, 2.0])
    wallet_consensus_window_seconds: int = 300


class ChainConfig(BaseModel):
    primary: str = "solana"
    secondary: list[str] = Field(default=["base", "bnb"])
    arb_only: list[str] = Field(default=["ethereum"])
    min_arb_spread_pct: float = 0.04


class ScamShieldConfig(BaseModel):
    max_scam_probability: float = 0.40
    honeypot_sell_tax_threshold: float = 0.10
    honeypot_simulation: bool = True
    static_analysis: bool = True
    social_scan_window_hours: int = 2
    test_buy_amount_usd: float = 10.0
    rug_warning_follower_threshold: int = 10_000
    blacklist_duration_hours: int = 48
    mev_delay_range_seconds: list[int] = Field(default=[30, 90])


class NotificationConfig(BaseModel):
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    voice_alerts: bool = True
    meme_reports: bool = True
    sobriety_email: str = ""


class InfrastructureConfig(BaseModel):
    vps_region: str = "us-east-1"
    docker_replicas: int = 3
    redis_url: str = "redis://localhost:6379"
    database_url: str = ""
    prometheus_port: int = 9090
    grafana_port: int = 3000


class GamificationLevelConfig(BaseModel):
    min_wins: int
    max_wins: int
    level: int
    max_leverage: int
    label: str


class GamificationConfig(BaseModel):
    levels: list[GamificationLevelConfig] = Field(default=[])
    level_reset_on_consecutive_losses: int = 3
    casino_mode_win_streak: int = 5
    win_streak_milestones: list[int] = Field(default=[5, 10, 20])


class Settings(BaseModel):
    agent: AgentConfig = AgentConfig()
    portfolio: PortfolioConfig = PortfolioConfig()
    risk: RiskConfig = RiskConfig()
    signals: SignalConfig = SignalConfig()
    chains: ChainConfig = ChainConfig()
    scam_shield: ScamShieldConfig = ScamShieldConfig()
    notifications: NotificationConfig = NotificationConfig()
    infrastructure: InfrastructureConfig = InfrastructureConfig()
    gamification: GamificationConfig = GamificationConfig()


_settings_cache: Settings | None = None


def get_settings() -> Settings:
    global _settings_cache
    if _settings_cache is None:
        raw = _load_yaml(_CONFIG_PATH)
        _settings_cache = Settings.model_validate(raw)
    return _settings_cache
