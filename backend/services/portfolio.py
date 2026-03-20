"""포트폴리오 조회 서비스 (대시보드/API용)"""

from sqlalchemy.orm import Session

from models import (
    Cycle, Order, Symbol, EventLog, CycleState, OrderStatus, OrderSide,
)


def get_dashboard_summary(db: Session) -> dict:
    """전체 대시보드 요약"""
    active_cycles = (
        db.query(Cycle)
        .filter(Cycle.state.notin_([CycleState.HALTED, CycleState.COOLDOWN]))
        .all()
    )
    completed_cycles = (
        db.query(Cycle)
        .filter(Cycle.state == CycleState.COOLDOWN)
        .all()
    )
    halted_cycles = (
        db.query(Cycle)
        .filter(Cycle.state == CycleState.HALTED)
        .all()
    )

    total_invested = sum(c.total_invested for c in active_cycles)
    total_pnl = sum(c.realized_pnl for c in completed_cycles)
    completed_count = len(completed_cycles)
    avg_pnl_pct = (
        sum(c.realized_pnl_pct for c in completed_cycles) / completed_count
        if completed_count > 0 else 0
    )

    return {
        "active_count": len(active_cycles),
        "completed_count": completed_count,
        "halted_count": len(halted_cycles),
        "total_invested": round(total_invested, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl_pct": round(avg_pnl_pct * 100, 2),
        "cycles": [_cycle_to_dict(c) for c in active_cycles],
    }


def get_symbol_detail(db: Session, ticker: str) -> dict:
    """종목 상세"""
    symbol = db.query(Symbol).filter(Symbol.ticker == ticker).first()
    if not symbol:
        return {"error": "종목을 찾을 수 없습니다"}

    cycles = (
        db.query(Cycle)
        .filter(Cycle.symbol_id == symbol.id)
        .order_by(Cycle.started_at.desc())
        .all()
    )

    return {
        "symbol": {
            "ticker": symbol.ticker,
            "name": symbol.name,
            "market": symbol.market,
            "exchange": symbol.exchange,
            "is_enabled": symbol.is_enabled,
        },
        "cycles": [_cycle_to_dict(c) for c in cycles],
    }


def get_order_history(
    db: Session,
    ticker: str | None = None,
    side: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """주문 내역"""
    query = db.query(Order).join(Cycle).join(Symbol)

    if ticker:
        query = query.filter(Symbol.ticker == ticker)
    if side:
        query = query.filter(Order.side == side)

    orders = (
        query.order_by(Order.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [_order_to_dict(o) for o in orders]


def get_event_logs(
    db: Session,
    cycle_id: int | None = None,
    event_type: str | None = None,
    level: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """이벤트 로그"""
    query = db.query(EventLog)
    if cycle_id:
        query = query.filter(EventLog.cycle_id == cycle_id)
    if event_type:
        query = query.filter(EventLog.event_type == event_type)
    if level:
        query = query.filter(EventLog.level == level)

    logs = query.order_by(EventLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id": e.id,
            "cycle_id": e.cycle_id,
            "event_type": e.event_type,
            "level": e.level,
            "message": e.message,
            "data": e.data,
            "created_at": e.created_at.isoformat(),
        }
        for e in logs
    ]


def get_completed_summary(db: Session) -> dict:
    """완료 사이클 요약"""
    completed = (
        db.query(Cycle)
        .filter(Cycle.realized_pnl != 0)
        .order_by(Cycle.ended_at.desc())
        .all()
    )

    return {
        "total_cycles": len(completed),
        "total_pnl": round(sum(c.realized_pnl for c in completed), 2),
        "avg_pnl_pct": round(
            sum(c.realized_pnl_pct for c in completed) / len(completed) * 100, 2
        ) if completed else 0,
        "cycles": [
            {
                "id": c.id,
                "ticker": c.symbol.ticker,
                "cycle_budget": round(c.cycle_budget, 2),
                "realized_pnl": round(c.realized_pnl, 2),
                "realized_pnl_pct": round(c.realized_pnl_pct * 100, 2),
                "steps_used": c.steps_used,
                "tranche_count": c.tranche_count,
                "started_at": c.started_at.isoformat(),
                "ended_at": c.ended_at.isoformat() if c.ended_at else None,
            }
            for c in completed
        ],
    }


def _cycle_to_dict(cycle: Cycle) -> dict:
    return {
        "id": cycle.id,
        "ticker": cycle.symbol.ticker,
        "name": cycle.symbol.name,
        "state": cycle.state.value,
        "state_reason": cycle.state_reason,
        "buy_mode": cycle.buy_mode.value,
        "cycle_budget": round(cycle.cycle_budget, 2),
        "tranche_count": cycle.tranche_count,
        "steps_used": cycle.steps_used,
        "total_invested": round(cycle.total_invested, 2),
        "total_quantity": cycle.total_quantity,
        "avg_cost": round(cycle.avg_cost, 2),
        "last_buy_fill_price": round(cycle.last_buy_fill_price, 2),
        "take_profit_pct": round(cycle.take_profit_pct * 100, 2),
        "add_trigger_pct": round(cycle.add_trigger_pct * 100, 2),
        "soft_drawdown_pct": round(cycle.soft_drawdown_pct * 100, 2),
        "hard_drawdown_pct": round(cycle.hard_drawdown_pct * 100, 2),
        "daily_buy_count": cycle.daily_buy_count,
        "realized_pnl": round(cycle.realized_pnl, 2),
        "realized_pnl_pct": round(cycle.realized_pnl_pct * 100, 2),
        "started_at": cycle.started_at.isoformat(),
        "ended_at": cycle.ended_at.isoformat() if cycle.ended_at else None,
        "position_version": cycle.position_version,
    }


def _order_to_dict(order: Order) -> dict:
    return {
        "id": order.id,
        "cycle_id": order.cycle_id,
        "ticker": order.symbol,
        "client_order_id": order.client_order_id[:12] + "...",
        "side": order.side.value,
        "status": order.status.value,
        "quantity": order.quantity,
        "limit_price": round(order.limit_price, 2) if order.limit_price else None,
        "filled_quantity": order.filled_quantity,
        "filled_avg_price": round(order.filled_avg_price, 2),
        "filled_amount": round(order.filled_amount, 2),
        "step_no": order.step_no,
        "reason": order.reason,
        "replace_count": order.replace_count,
        "created_at": order.created_at.isoformat(),
        "filled_at": order.filled_at.isoformat() if order.filled_at else None,
    }
