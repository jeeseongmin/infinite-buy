"""규칙서 v1 기반 데이터 모델

상태머신 (규칙서 §5):
  BOOTSTRAP → READY → BUY_PENDING → HOLDING → SELL_PENDING → COOLDOWN → READY
  ANY → BUY_BLOCKED / OBSERVE_ONLY / MANUAL_REVIEW / HALTED
"""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Enum, Text, JSON,
)
from sqlalchemy.orm import relationship

from database import Base


# === 상태머신 (규칙서 §5) ===

class CycleState(str, PyEnum):
    BOOTSTRAP = "BOOTSTRAP"
    READY = "READY"
    BUY_PENDING = "BUY_PENDING"
    HOLDING = "HOLDING"
    SELL_PENDING = "SELL_PENDING"
    BUY_BLOCKED = "BUY_BLOCKED"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    COOLDOWN = "COOLDOWN"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    HALTED = "HALTED"


class OrderSide(str, PyEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, PyEnum):
    PENDING = "PENDING"       # 주문 발사됨, 응답 대기
    OPEN = "OPEN"             # 브로커 접수 확인
    PARTIAL = "PARTIAL"       # 부분 체결
    FILLED = "FILLED"         # 전량 체결
    CANCELLED = "CANCELLED"   # 취소됨
    REJECTED = "REJECTED"     # 거부됨
    EXPIRED = "EXPIRED"       # 만료


class RegimeMode(str, PyEnum):
    ON = "ON"
    CAUTION = "CAUTION"
    OFF = "OFF"


class BuyMode(str, PyEnum):
    PRICE_LADDER = "PRICE_LADDER"
    DAILY_TRANCHE = "DAILY_TRANCHE"


# === 종목 ===

class Symbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), unique=True, nullable=False)  # QLD, TQQQ
    name = Column(String(100), nullable=False)
    market = Column(String(10), default="US")
    exchange = Column(String(10), default="NAS")  # NAS, NYSE
    is_enabled = Column(Boolean, default=False)  # feature flag
    created_at = Column(DateTime, default=datetime.utcnow)

    cycles = relationship("Cycle", back_populates="symbol")


# === 사이클 (규칙서 §5 상태머신 단위) ===

class Cycle(Base):
    __tablename__ = "cycles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol_id = Column(Integer, ForeignKey("symbols.id"), nullable=False)

    # 상태머신
    state = Column(Enum(CycleState), default=CycleState.BOOTSTRAP, nullable=False)
    prev_state = Column(Enum(CycleState), nullable=True)  # 이전 상태 (복구용)
    state_reason = Column(String(200), default="")
    state_changed_at = Column(DateTime, default=datetime.utcnow)

    # 전략 설정 (사이클 시작 시 스냅샷)
    buy_mode = Column(Enum(BuyMode), default=BuyMode.PRICE_LADDER)
    cycle_budget = Column(Float, nullable=False)  # 이 사이클 총 예산
    tranche_count = Column(Integer, default=16)
    take_profit_pct = Column(Float, default=0.014)
    add_trigger_pct = Column(Float, default=0.015)
    soft_drawdown_pct = Column(Float, default=0.06)
    hard_drawdown_pct = Column(Float, default=0.12)

    # 포지션 (규칙서 §4)
    steps_used = Column(Integer, default=0)
    total_quantity = Column(Integer, default=0)
    total_invested = Column(Float, default=0.0)
    avg_cost = Column(Float, default=0.0)
    last_buy_fill_price = Column(Float, default=0.0)
    position_version = Column(Integer, default=0)  # 규칙서 §12-3

    # 일별 카운터
    daily_buy_count = Column(Integer, default=0)
    daily_buy_date = Column(String(10), default="")  # YYYY-MM-DD

    # 수익
    realized_pnl = Column(Float, default=0.0)
    realized_pnl_pct = Column(Float, default=0.0)

    # 타임스탬프
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    cooldown_until = Column(DateTime, nullable=True)
    last_fill_at = Column(DateTime, nullable=True)

    # 킬스위치 카운터
    consecutive_rejects = Column(Integer, default=0)

    symbol = relationship("Symbol", back_populates="cycles")
    orders = relationship("Order", back_populates="cycle", order_by="Order.created_at.desc()")


# === 주문 (규칙서 §12, §15) ===

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_id = Column(Integer, ForeignKey("cycles.id"), nullable=False)

    # idempotency (규칙서 §12-2)
    client_order_id = Column(String(100), unique=True, nullable=False)
    broker_order_id = Column(String(100), nullable=True)

    side = Column(Enum(OrderSide), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING)

    # 주문 내용
    symbol = Column(String(20), nullable=False)
    quantity = Column(Integer, nullable=False)
    limit_price = Column(Float, nullable=True)  # limit 주문 가격
    filled_quantity = Column(Integer, default=0)
    filled_avg_price = Column(Float, default=0.0)
    filled_amount = Column(Float, default=0.0)

    # 메타
    step_no = Column(Integer, nullable=True)  # 몇 번째 tranche
    reason = Column(String(200), default="")
    replace_count = Column(Integer, default=0)  # cancel/replace 횟수

    # 스냅샷 (의사결정 시점)
    decision_mid = Column(Float, nullable=True)
    decision_bid = Column(Float, nullable=True)
    decision_ask = Column(Float, nullable=True)
    decision_spread_bps = Column(Float, nullable=True)
    decision_position_version = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    acked_at = Column(DateTime, nullable=True)
    filled_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    cycle = relationship("Cycle", back_populates="orders")


# === 이벤트 로그 ===

class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_id = Column(Integer, ForeignKey("cycles.id"), nullable=True)
    event_type = Column(String(50), nullable=False)  # STATE_CHANGE, ORDER, FILL, RISK, KILL_SWITCH, ERROR
    level = Column(String(10), default="INFO")  # INFO, WARN, ERROR, CRITICAL
    message = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# === 설정 (DB 저장용) ===

class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False)
    value = Column(String(500), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# === 시세 스냅샷 캐시 ===

class QuoteSnapshot(Base):
    __tablename__ = "quote_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    mid = Column(Float, nullable=True)
    last = Column(Float, nullable=True)
    spread_bps = Column(Float, nullable=True)
    volume = Column(Integer, nullable=True)
    timestamp = Column(DateTime, nullable=False)
    is_stale = Column(Boolean, default=False)
