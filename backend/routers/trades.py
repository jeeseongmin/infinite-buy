from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from services.portfolio import get_order_history, get_completed_summary, get_event_logs

router = APIRouter(prefix="/api", tags=["trades"])


@router.get("/orders")
def list_orders(
    ticker: str | None = None,
    side: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return get_order_history(db, ticker, side, limit, offset)


@router.get("/orders/summary")
def completed_summary(db: Session = Depends(get_db)):
    return get_completed_summary(db)


@router.get("/events")
def event_logs(
    cycle_id: int | None = None,
    event_type: str | None = None,
    level: str | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    return get_event_logs(db, cycle_id, event_type, level, limit)
