from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# ───────────────── enums ─────────────────

class Plan:
    FREE = "free"
    PRO = "pro"
    ELITE = "elite"
    ALL = (FREE, PRO, ELITE)
    LIMIT = {FREE: 3, PRO: 10, ELITE: 30}

    @classmethod
    def at_least(cls, current: str, required: str) -> bool:
        order = {cls.FREE: 0, cls.PRO: 1, cls.ELITE: 2}
        return order.get(current, -1) >= order.get(required, 99)


class SubStatus:
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    ALL = (ACTIVE, TRIALING, PAST_DUE, CANCELED, INCOMPLETE)


# ───────────────── market data ─────────────────

class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(8), default="TWSE", nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    prices: Mapped[list["DailyPrice"]] = relationship(back_populates="stock", cascade="all, delete")
    chips: Mapped[list["ChipData"]] = relationship(back_populates="stock", cascade="all, delete")
    scores: Mapped[list["Score"]] = relationship(back_populates="stock", cascade="all, delete")


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_daily_prices_stock_date"),
        Index("ix_daily_prices_stock_date", "stock_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    stock: Mapped["Stock"] = relationship(back_populates="prices")


class ChipData(Base):
    __tablename__ = "chip_data"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_chip_data_stock_date"),
        Index("ix_chip_data_stock_date", "stock_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    foreign_buy: Mapped[float] = mapped_column(Float, default=0.0)
    investment_buy: Mapped[float] = mapped_column(Float, default=0.0)
    dealer_buy: Mapped[float] = mapped_column(Float, default=0.0)

    stock: Mapped["Stock"] = relationship(back_populates="chips")


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_scores_stock_date"),
        Index("ix_scores_stock_date", "stock_id", "date"),
        Index("ix_scores_date_total", "date", "total_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    chip_score: Mapped[float] = mapped_column(Float, default=0.0)
    fundamental_score: Mapped[float] = mapped_column(Float, default=0.0)
    technical_score: Mapped[float] = mapped_column(Float, default=0.0)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[Optional[str]] = mapped_column(String(256))

    stock: Mapped["Stock"] = relationship(back_populates="scores")


# ───────────────── auth & billing ─────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))  # null for OAuth-only
    plan: Mapped[str] = mapped_column(String(16), default="free", nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    line_user_id: Mapped[Optional[str]] = mapped_column(String(64))  # for LINE push
    notify_open: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_intraday: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_close: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user", cascade="all, delete")
    favorites: Mapped[list["Favorite"]] = relationship(back_populates="user", cascade="all, delete")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)
    price_twd: Mapped[int] = mapped_column(Integer, default=0)  # 0/299/1499
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="subscriptions")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="uq_favorites_user_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="favorites")


class Referral(Base):
    """Each user has a stable referral code; each invitation creates one row."""
    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint("referrer_id", "invitee_email", name="uq_ref_inviter_invitee"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    invitee_email: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    invitee_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)  # when invitee paid
    reward_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    reward_kind: Mapped[Optional[str]] = mapped_column(String(32))  # "pro_7d" / "elite_30d"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BlogPost(Base):
    """Auto-generated SEO content."""
    __tablename__ = "blog_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(String(200), default="")  # csv
    published_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class StockPick(Base):
    """Daily AI pick snapshot — drives leaderboard performance display."""
    __tablename__ = "stock_picks"
    __table_args__ = (
        UniqueConstraint("date", "symbol", name="uq_picks_date_symbol"),
        Index("ix_picks_date", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), default="")
    rank: Mapped[int] = mapped_column(Integer, default=0)
    entry_price: Mapped[float] = mapped_column(Float, default=0.0)
    return_pct: Mapped[float] = mapped_column(Float, default=0.0)  # measured later


class EdgeSignal(Base):
    """Every LONG plan emitted by the scanner is persisted here.

    Used to compute *real* historical performance per setup, regime, sector.
    """
    __tablename__ = "edge_signals"
    __table_args__ = (
        UniqueConstraint("date", "symbol", "setup", name="uq_edge_signals_date_symbol_setup"),
        Index("ix_edge_signals_setup_date", "setup", "date"),
        Index("ix_edge_signals_evaluated", "evaluated"),
        Index("ix_edge_signals_regime", "regime"),
        Index("ix_edge_signals_sector", "sector"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    setup: Mapped[str] = mapped_column(String(48), nullable=False)
    bias: Mapped[str] = mapped_column(String(8), default="LONG")
    regime: Mapped[Optional[str]] = mapped_column(String(32))
    sector: Mapped[Optional[str]] = mapped_column(String(48))
    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    tp1: Mapped[float] = mapped_column(Float, nullable=False)
    tp2: Mapped[float] = mapped_column(Float, nullable=False)
    risk_reward: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    edge_score: Mapped[float] = mapped_column(Float, default=0.0)
    # outcome — filled by the daily evaluator
    evaluated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(16))  # stop / tp1 / tp2 / timeout
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    realized_r: Mapped[Optional[float]] = mapped_column(Float)      # in R units
    win: Mapped[Optional[bool]] = mapped_column(Boolean)
    bars_held: Mapped[Optional[int]] = mapped_column(Integer)
    # Excursion telemetry — written by the evaluator alongside the outcome.
    mfe_r: Mapped[Optional[float]] = mapped_column(Float)   # max favorable in R
    mae_r: Mapped[Optional[float]] = mapped_column(Float)   # max adverse in R
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UniverseSnapshot(Base):
    """Weekly snapshot of the active research universe.

    A row exists for each (date, symbol). `is_active` reflects whether the
    symbol cleared liquidity + data-quality filters that week.
    """
    __tablename__ = "universe_snapshots"
    __table_args__ = (
        UniqueConstraint("date", "symbol", name="uq_universe_snapshots_date_symbol"),
        Index("ix_universe_snapshots_date_active", "date", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), default="")
    market: Mapped[str] = mapped_column(String(8), default="TWSE")
    sector_zh: Mapped[str] = mapped_column(String(48), default="其他")
    sector_en: Mapped[str] = mapped_column(String(48), default="Other")
    avg_volume_20d: Mapped[int] = mapped_column(BigInteger, default=0)
    last_close: Mapped[float] = mapped_column(Float, default=0.0)
    notional_twd: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    rank_by_notional: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StrategyPerformanceDaily(Base):
    """Per-strategy daily snapshot — feeds the strategy ranker."""
    __tablename__ = "strategy_performance_daily"
    __table_args__ = (
        UniqueConstraint("date", "strategy", name="uq_strategy_perf_date_strategy"),
        Index("ix_strategy_perf_strategy_date", "strategy", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    strategy: Mapped[str] = mapped_column(String(48), nullable=False)
    signals_emitted: Mapped[int] = mapped_column(Integer, default=0)
    evaluated_count: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    expectancy_r: Mapped[float] = mapped_column(Float, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    avg_mfe_r: Mapped[float] = mapped_column(Float, default=0.0)
    avg_mae_r: Mapped[float] = mapped_column(Float, default=0.0)
    decay_score: Mapped[float] = mapped_column(Float, default=0.0)  # recent vs older R
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    production_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")  # ACTIVE / DISABLED / WATCH
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    channel: Mapped[str] = mapped_column(String(16), default="line")
    kind: Mapped[str] = mapped_column(String(24))  # open / intraday / close / test
    message: Mapped[str] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
