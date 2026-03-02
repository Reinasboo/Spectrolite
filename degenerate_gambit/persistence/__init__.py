"""
Persistence layer — SQLAlchemy models and trade logger for Spectrolite.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///degenerate_gambit.db")

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class TradeLog(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash = Column(String(128), unique=True, index=True)
    token_address = Column(String(128), index=True)
    token_symbol = Column(String(32))
    chain = Column(String(16))
    order_type = Column(String(32))
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    size_usd = Column(Float)
    leverage = Column(Float)
    realized_pnl_usd = Column(Float, nullable=True)
    realized_pnl_pct = Column(Float, nullable=True)
    meme_score_at_entry = Column(Float)
    scam_probability = Column(Float)
    pump_probability = Column(Float)
    mode = Column(String(32))
    mutation_applied = Column(Boolean, default=False)
    status = Column(String(16), default="open")
    viral_thesis = Column(Text, nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    extra_json = Column(Text, nullable=True)   # arbitrary extra metadata


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    total_usd = Column(Float)
    moonshot_usd = Column(Float)
    rotation_usd = Column(Float)
    arb_usd = Column(Float)
    iron_coffin_usd = Column(Float)
    win_streak = Column(Integer, default=0)
    level = Column(Integer, default=1)
    mode = Column(String(32))


class WalletBlacklist(Base):
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_symbol = Column(String(32), unique=True, index=True)
    reason = Column(String(256))
    blacklisted_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


class TradeLogger:
    """Records trades to PostgreSQL / SQLite for compliance and analytics."""

    def __init__(self) -> None:
        create_tables()

    def record(self, trade) -> None:
        """Persist a TradeResult to the database."""
        from ..models import TradeResult
        if not isinstance(trade, TradeResult):
            return

        row = TradeLog(
            tx_hash=trade.tx_hash,
            token_address=trade.token.address,
            token_symbol=trade.token.symbol,
            chain=trade.chain.value,
            order_type=trade.order_type.value,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            size_usd=trade.size_usd,
            leverage=trade.leverage,
            realized_pnl_usd=trade.realized_pnl_usd,
            realized_pnl_pct=trade.realized_pnl_pct,
            meme_score_at_entry=trade.meme_score_at_entry,
            scam_probability=trade.token.scam_probability,
            pump_probability=trade.token.pump_prediction.pump_probability,
            mode=trade.mode.value,
            mutation_applied=trade.mutation_applied,
            status=trade.status.value,
            viral_thesis=trade.token.viral_thesis,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
        )
        with SessionLocal() as session:
            session.merge(row)
            session.commit()

    def get_closed_trades(self, limit: int = 500) -> list[dict]:
        with SessionLocal() as session:
            rows = (
                session.query(TradeLog)
                .filter(TradeLog.status == "closed")
                .order_by(TradeLog.closed_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {c.key: getattr(row, c.key) for c in row.__table__.columns}
                for row in rows
            ]

    def snapshot_portfolio(self, portfolio) -> None:
        """Save a portfolio state snapshot."""
        snap = PortfolioSnapshot(
            total_usd=portfolio.total_usd,
            moonshot_usd=portfolio.moonshot_usd,
            rotation_usd=portfolio.rotation_usd,
            arb_usd=portfolio.arb_usd,
            iron_coffin_usd=portfolio.iron_coffin_usd,
            win_streak=portfolio.win_streak,
            mode=portfolio.mode.value,
        )
        with SessionLocal() as session:
            session.add(snap)
            session.commit()
