"""의사결정 엔진 (규칙서 §6, §18)

의사결정 우선순위 (§6):
1. 킬스위치 여부 확인
2. 브로커/시세/포지션 정상 여부 확인
3. 기존 미체결 주문 정리
4. 매도 신호 평가
5. 보류/관망 여부 평가
6. 매수 신호 평가

한 줄 규칙: sell > hold > buy
"""

import logging
import math
from datetime import datetime, timedelta
from dataclasses import dataclass

from sqlalchemy.orm import Session

from config import get_settings
from models import (
    Cycle, Order, EventLog, CycleState, OrderSide, OrderStatus, RegimeMode,
)
from services.broker_api import (
    get_broker, generate_client_order_id,
    calculate_buy_limit_price, calculate_sell_limit_price,
    Quote, LiveDataBroker,
)
from services.risk_manager import (
    MarketSnapshot, RiskAssessment,
    assess_risk, assess_regime,
    should_take_profit, should_hard_exit, should_add_tranche,
)
from services.state_machine import transition, can_buy, can_sell

logger = logging.getLogger(__name__)


@dataclass
class DecisionResult:
    """의사결정 결과"""
    action: str  # HOLD, BUY, SELL, HALT, OBSERVE, MANUAL_REVIEW
    reason: str
    order: Order | None = None


def build_snapshot(symbol: str) -> MarketSnapshot | None:
    """브로커에서 시세 조회 → MarketSnapshot 생성"""
    broker = get_broker()
    quote = broker.get_quote(symbol)
    if not quote:
        return None

    settings = get_settings()

    # 세션 시간 계산 (ET 기준, 간략화)
    now = datetime.utcnow()
    # TODO: 실제 ET 변환 + 거래일 캘린더
    market_open = True
    minutes_since_open = 30  # mock
    minutes_until_close = 360  # mock

    # 레짐 데이터
    qqq_quote = broker.get_quote(settings.regime_symbol)
    qqq_close = qqq_quote.last if qqq_quote else 0

    # LiveDataBroker면 실제 SMA 계산, 아니면 mock
    if isinstance(broker, LiveDataBroker):
        qqq_sma200 = broker.get_sma(settings.regime_symbol, 200) or qqq_close * 0.98
        qqq_sma20 = broker.get_sma(settings.regime_symbol, 20) or qqq_close * 0.995
        qqq_sma20_slope = broker.get_sma_slope(settings.regime_symbol, 20)
    else:
        qqq_sma200 = qqq_close * 0.98
        qqq_sma20 = qqq_close * 0.995
        qqq_sma20_slope = 0.001

    return MarketSnapshot(
        symbol=symbol,
        bid=quote.bid,
        ask=quote.ask,
        mid=quote.mid,
        last=quote.last,
        spread_bps=quote.spread_bps,
        volume=quote.volume,
        timestamp=quote.timestamp,
        prev_close=quote.prev_close,
        qqq_close=qqq_close,
        qqq_sma200=qqq_sma200,
        qqq_sma20=qqq_sma20,
        qqq_sma20_slope=qqq_sma20_slope,
        vol_15m_ann=0.3,  # TODO: 실제 변동성 계산
        market_open=market_open,
        minutes_since_open=minutes_since_open,
        minutes_until_close=minutes_until_close,
    )


def has_open_orders(db: Session, cycle: Cycle) -> bool:
    """미체결 주문 존재 여부"""
    return db.query(Order).filter(
        Order.cycle_id == cycle.id,
        Order.status.in_([OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIAL]),
    ).count() > 0


def evaluate(db: Session, cycle: Cycle) -> DecisionResult:
    """핵심 의사결정 루프 (규칙서 §18 의사코드)

    def evaluate(symbol, snapshot):
        if not system_healthy(snapshot): return halt
        if position_mismatch(symbol): return manual_review
        if has_open_order(symbol): return observe_only
        mode = risk_mode(snapshot)
        # 1) sell first
        # 2) buy blocked zone
        # 3) buy logic
    """
    settings = get_settings()
    symbol = cycle.symbol.ticker

    # 1. 시스템 건전성 (브로커 연결)
    broker = get_broker()
    if not broker.is_connected():
        if cycle.state != CycleState.HALTED:
            transition(db, cycle, CycleState.HALTED, "브로커 연결 끊김")
            db.commit()
        return DecisionResult(action="HALT", reason="브로커 연결 끊김")

    # 2. 시세 조회
    snapshot = build_snapshot(symbol)
    if not snapshot:
        if cycle.state != CycleState.HALTED:
            transition(db, cycle, CycleState.HALTED, "시세 조회 실패")
            db.commit()
        return DecisionResult(action="HALT", reason="시세 조회 실패")

    # 3. 포지션 불일치 확인 (규칙서 §12-3)
    broker_positions = broker.get_positions()
    broker_qty = 0
    for pos in broker_positions:
        if pos.symbol == symbol:
            broker_qty = pos.quantity
            break

    if cycle.total_quantity != broker_qty and cycle.state not in (
        CycleState.BUY_PENDING, CycleState.SELL_PENDING, CycleState.BOOTSTRAP
    ):
        logger.warning(
            f"[{symbol}] 포지션 불일치: 내부={cycle.total_quantity} 브로커={broker_qty}"
        )
        if cycle.state != CycleState.MANUAL_REVIEW:
            transition(db, cycle, CycleState.MANUAL_REVIEW,
                       f"포지션 불일치: 내부={cycle.total_quantity} 브로커={broker_qty}")
            db.commit()
        return DecisionResult(action="MANUAL_REVIEW", reason="포지션 불일치")

    # 4. 미체결 주문 확인
    if has_open_orders(db, cycle):
        # 미체결 있으면 타임아웃 처리
        _handle_pending_orders(db, cycle)
        return DecisionResult(action="OBSERVE", reason="미체결 주문 있음")

    # 5. 리스크 모드 판단
    risk = assess_risk(cycle, snapshot)

    if risk.mode == "HALTED":
        if cycle.state != CycleState.HALTED:
            transition(db, cycle, CycleState.HALTED, "; ".join(risk.reasons))
            db.commit()
        return DecisionResult(action="HALT", reason="; ".join(risk.reasons))

    if risk.mode == "OBSERVE_ONLY":
        if cycle.state != CycleState.OBSERVE_ONLY:
            transition(db, cycle, CycleState.OBSERVE_ONLY, "; ".join(risk.reasons))
            db.commit()
        return DecisionResult(action="OBSERVE", reason="; ".join(risk.reasons))

    # === sell > hold > buy (규칙서 §6) ===

    # 6. 매도 (§9) - sell first
    if cycle.total_quantity > 0:
        # 하드 리스크 청산
        hard_exit, hard_reason = should_hard_exit(cycle, snapshot)
        if hard_exit:
            return _execute_sell(db, cycle, snapshot, f"하드 청산: {hard_reason}")

        # 익절 청산
        if should_take_profit(cycle, snapshot):
            pnl_pct = (snapshot.mid - cycle.avg_cost) / cycle.avg_cost
            return _execute_sell(
                db, cycle, snapshot,
                f"익절: {pnl_pct*100:.2f}% >= {cycle.take_profit_pct*100:.2f}%"
            )

    # 7. BUY_BLOCKED (§10-1) - hold
    if risk.mode == "BUY_BLOCKED":
        if cycle.state == CycleState.HOLDING:
            # HOLDING에서는 BUY_BLOCKED 전이
            transition(db, cycle, CycleState.BUY_BLOCKED, "; ".join(risk.reasons))
            db.commit()
        elif cycle.state == CycleState.READY:
            transition(db, cycle, CycleState.BUY_BLOCKED, "; ".join(risk.reasons))
            db.commit()
        return DecisionResult(action="HOLD", reason=f"BUY_BLOCKED: {'; '.join(risk.reasons)}")

    # BUY_BLOCKED 해소 → 원래 상태로 복귀
    if cycle.state == CycleState.BUY_BLOCKED:
        restore = CycleState.HOLDING if cycle.total_quantity > 0 else CycleState.READY
        transition(db, cycle, restore, "BUY_BLOCKED 해소")
        db.commit()

    # 8. 매수 (§7, §8) - buy
    if cycle.total_quantity == 0:
        # 첫 매수 (§7-2)
        if risk.entry_gate_ok and can_buy(cycle):
            return _execute_buy(db, cycle, snapshot, step_no=1, reason="첫 tranche 진입")
        return DecisionResult(action="HOLD", reason="진입 게이트 미통과")

    if cycle.total_quantity > 0 and can_buy(cycle):
        # 추가매수 (§8)
        should_add, add_reason = should_add_tranche(cycle, snapshot)
        if should_add:
            return _execute_buy(
                db, cycle, snapshot,
                step_no=cycle.steps_used + 1,
                reason=add_reason,
            )
        return DecisionResult(action="HOLD", reason=add_reason)

    return DecisionResult(action="HOLD", reason="대기")


def _execute_buy(
    db: Session,
    cycle: Cycle,
    snapshot: MarketSnapshot,
    step_no: int,
    reason: str,
) -> DecisionResult:
    """매수 실행"""
    settings = get_settings()
    broker = get_broker()

    # tranche 금액 계산
    regime = assess_regime(snapshot)
    budget = cycle.cycle_budget
    if regime == RegimeMode.CAUTION:
        budget *= 0.5  # CAUTION 시 예산 50% 축소

    tranche_notional = budget / cycle.tranche_count
    quote = broker.get_quote(snapshot.symbol)
    if not quote:
        return DecisionResult(action="HOLD", reason="시세 재조회 실패")

    limit_price = calculate_buy_limit_price(quote)
    quantity = max(1, math.floor(tranche_notional / limit_price))

    # client_order_id 생성 (§12-2)
    coid = generate_client_order_id(
        strategy_id="infinite_buy_v1",
        cycle_id=cycle.id,
        symbol=snapshot.symbol,
        action="BUY",
        step_no=step_no,
        decision_ts=datetime.utcnow(),
    )

    # 중복 주문 체크
    existing = db.query(Order).filter(Order.client_order_id == coid).first()
    if existing:
        return DecisionResult(action="HOLD", reason=f"중복 주문 감지 coid={coid}")

    # 상태 전이: → BUY_PENDING
    transition(db, cycle, CycleState.BUY_PENDING, reason)

    # 주문 기록
    order = Order(
        cycle_id=cycle.id,
        client_order_id=coid,
        side=OrderSide.BUY,
        status=OrderStatus.PENDING,
        symbol=snapshot.symbol,
        quantity=quantity,
        limit_price=limit_price,
        step_no=step_no,
        reason=reason,
        decision_mid=snapshot.mid,
        decision_bid=snapshot.bid,
        decision_ask=snapshot.ask,
        decision_spread_bps=snapshot.spread_bps,
        decision_position_version=cycle.position_version,
    )
    db.add(order)
    db.flush()

    # 브로커 주문
    result = broker.submit_limit_buy(snapshot.symbol, quantity, limit_price, coid)

    if result.success:
        order.broker_order_id = result.broker_order_id
        order.acked_at = datetime.utcnow()

        if result.filled_quantity > 0:
            _process_fill(db, cycle, order, result.filled_quantity, result.filled_price)
        else:
            order.status = OrderStatus.OPEN

        cycle.consecutive_rejects = 0
    else:
        order.status = OrderStatus.REJECTED
        cycle.consecutive_rejects += 1
        transition(db, cycle, CycleState.HOLDING if cycle.total_quantity > 0 else CycleState.READY,
                   f"주문 거부: {result.message}")

        db.add(EventLog(
            cycle_id=cycle.id,
            event_type="ORDER",
            level="WARN",
            message=f"매수 거부: {result.message}",
            data={"coid": coid, "reason": result.message},
        ))

    db.commit()

    return DecisionResult(
        action="BUY" if result.success else "HOLD",
        reason=f"매수 {'체결' if result.success else '거부'}: {reason}",
        order=order if result.success else None,
    )


def _execute_sell(
    db: Session,
    cycle: Cycle,
    snapshot: MarketSnapshot,
    reason: str,
) -> DecisionResult:
    """매도 실행 (전량)"""
    broker = get_broker()
    quote = broker.get_quote(snapshot.symbol)
    if not quote:
        return DecisionResult(action="HOLD", reason="시세 재조회 실패")

    limit_price = calculate_sell_limit_price(quote)

    coid = generate_client_order_id(
        strategy_id="infinite_buy_v1",
        cycle_id=cycle.id,
        symbol=snapshot.symbol,
        action="SELL",
        step_no=cycle.steps_used,
        decision_ts=datetime.utcnow(),
    )

    existing = db.query(Order).filter(Order.client_order_id == coid).first()
    if existing:
        return DecisionResult(action="HOLD", reason=f"중복 매도 주문 감지 coid={coid}")

    transition(db, cycle, CycleState.SELL_PENDING, reason)

    order = Order(
        cycle_id=cycle.id,
        client_order_id=coid,
        side=OrderSide.SELL,
        status=OrderStatus.PENDING,
        symbol=snapshot.symbol,
        quantity=cycle.total_quantity,
        limit_price=limit_price,
        step_no=cycle.steps_used,
        reason=reason,
        decision_mid=snapshot.mid,
        decision_bid=snapshot.bid,
        decision_ask=snapshot.ask,
        decision_spread_bps=snapshot.spread_bps,
        decision_position_version=cycle.position_version,
    )
    db.add(order)
    db.flush()

    result = broker.submit_limit_sell(snapshot.symbol, cycle.total_quantity, limit_price, coid)

    if result.success:
        order.broker_order_id = result.broker_order_id
        order.acked_at = datetime.utcnow()

        if result.filled_quantity > 0:
            _process_sell_fill(db, cycle, order, result.filled_quantity, result.filled_price)
        else:
            order.status = OrderStatus.OPEN
    else:
        order.status = OrderStatus.REJECTED
        transition(db, cycle, CycleState.HOLDING, f"매도 거부: {result.message}")
        db.add(EventLog(
            cycle_id=cycle.id,
            event_type="ORDER",
            level="ERROR",
            message=f"매도 거부: {result.message}",
        ))

    db.commit()

    return DecisionResult(
        action="SELL" if result.success else "HOLD",
        reason=reason,
        order=order if result.success else None,
    )


def _process_fill(
    db: Session,
    cycle: Cycle,
    order: Order,
    filled_qty: int,
    filled_price: float,
):
    """매수 체결 처리"""
    settings = get_settings()

    order.status = OrderStatus.FILLED
    order.filled_quantity = filled_qty
    order.filled_avg_price = filled_price
    order.filled_amount = filled_qty * filled_price
    order.filled_at = datetime.utcnow()

    # 포지션 업데이트
    new_invested = cycle.total_invested + order.filled_amount
    new_qty = cycle.total_quantity + filled_qty
    cycle.total_invested = new_invested
    cycle.total_quantity = new_qty
    cycle.avg_cost = new_invested / new_qty if new_qty > 0 else 0
    cycle.last_buy_fill_price = filled_price
    cycle.steps_used += 1
    cycle.position_version += 1
    cycle.last_fill_at = datetime.utcnow()

    # 일별 매수 카운터
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if cycle.daily_buy_date != today:
        cycle.daily_buy_count = 1
        cycle.daily_buy_date = today
    else:
        cycle.daily_buy_count += 1

    # 상태 전이: BUY_PENDING → HOLDING
    transition(db, cycle, CycleState.HOLDING,
               f"매수 체결: {filled_qty}주 @ ${filled_price:.2f}")

    db.add(EventLog(
        cycle_id=cycle.id,
        event_type="FILL",
        level="INFO",
        message=(
            f"매수 체결: {filled_qty}주 @ ${filled_price:.2f} | "
            f"평단 ${cycle.avg_cost:.2f} | step {cycle.steps_used}/{cycle.tranche_count}"
        ),
        data={
            "side": "BUY",
            "qty": filled_qty,
            "price": filled_price,
            "avg_cost": cycle.avg_cost,
            "step": cycle.steps_used,
        },
    ))


def _process_sell_fill(
    db: Session,
    cycle: Cycle,
    order: Order,
    filled_qty: int,
    filled_price: float,
):
    """매도 체결 처리"""
    settings = get_settings()

    order.status = OrderStatus.FILLED
    order.filled_quantity = filled_qty
    order.filled_avg_price = filled_price
    order.filled_amount = filled_qty * filled_price
    order.filled_at = datetime.utcnow()

    # 수익 계산
    sell_amount = filled_qty * filled_price
    cost_basis = cycle.avg_cost * filled_qty
    pnl = sell_amount - cost_basis
    pnl_pct = pnl / cost_basis if cost_basis > 0 else 0

    cycle.realized_pnl = pnl
    cycle.realized_pnl_pct = pnl_pct
    cycle.total_quantity = 0
    cycle.total_invested = 0
    cycle.position_version += 1
    cycle.last_fill_at = datetime.utcnow()
    cycle.ended_at = datetime.utcnow()

    # 쿨다운 설정
    cycle.cooldown_until = datetime.utcnow() + timedelta(
        minutes=settings.strategy.cooldown_after_exit_min
    )

    # SELL_PENDING → COOLDOWN
    transition(db, cycle, CycleState.COOLDOWN,
               f"전량 청산: {filled_qty}주 @ ${filled_price:.2f} | PnL ${pnl:.2f} ({pnl_pct*100:.2f}%)")

    db.add(EventLog(
        cycle_id=cycle.id,
        event_type="FILL",
        level="INFO",
        message=(
            f"전량 청산: {filled_qty}주 @ ${filled_price:.2f} | "
            f"PnL ${pnl:.2f} ({pnl_pct*100:+.2f}%)"
        ),
        data={
            "side": "SELL",
            "qty": filled_qty,
            "price": filled_price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        },
    ))


def _handle_pending_orders(db: Session, cycle: Cycle):
    """미체결 주문 타임아웃 처리 (규칙서 §15)"""
    settings = get_settings()
    now = datetime.utcnow()

    pending_orders = db.query(Order).filter(
        Order.cycle_id == cycle.id,
        Order.status.in_([OrderStatus.PENDING, OrderStatus.OPEN]),
    ).all()

    broker = get_broker()

    for order in pending_orders:
        elapsed = (now - order.created_at).total_seconds()

        if elapsed > settings.execution.cancel_after_sec:
            # 타임아웃 → 취소
            if order.broker_order_id:
                broker.cancel_order(order.broker_order_id)

            order.status = OrderStatus.CANCELLED
            order.cancelled_at = now

            db.add(EventLog(
                cycle_id=cycle.id,
                event_type="ORDER",
                level="WARN",
                message=f"주문 타임아웃 취소: {order.client_order_id} ({elapsed:.0f}s)",
            ))

            # 상태 복귀
            if cycle.state == CycleState.BUY_PENDING:
                restore = CycleState.HOLDING if cycle.total_quantity > 0 else CycleState.READY
                transition(db, cycle, restore, "매수 주문 타임아웃")
            elif cycle.state == CycleState.SELL_PENDING:
                transition(db, cycle, CycleState.HOLDING, "매도 주문 타임아웃")

    db.commit()
