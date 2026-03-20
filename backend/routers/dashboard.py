from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.portfolio import get_dashboard_summary, get_symbol_detail
from services.broker_api import get_broker, LiveDataBroker

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(db: Session = Depends(get_db)):
    return get_dashboard_summary(db)


@router.get("/quote/{ticker}")
def get_live_quote(ticker: str):
    """실시간 시세 조회"""
    broker = get_broker()
    quote = broker.get_quote(ticker.upper())
    if not quote:
        raise HTTPException(status_code=404, detail="시세 조회 실패")

    result = {
        "symbol": quote.symbol,
        "bid": quote.bid,
        "ask": quote.ask,
        "mid": quote.mid,
        "last": quote.last,
        "spread_bps": quote.spread_bps,
        "volume": quote.volume,
        "prev_close": quote.prev_close,
        "change_pct": round((quote.last - quote.prev_close) / quote.prev_close * 100, 2)
        if quote.prev_close
        else 0,
        "is_live": isinstance(broker, LiveDataBroker),
        "timestamp": quote.timestamp.isoformat(),
    }

    # SMA 데이터 (LiveDataBroker만)
    if isinstance(broker, LiveDataBroker):
        sma200 = broker.get_sma(ticker.upper(), 200)
        sma20 = broker.get_sma(ticker.upper(), 20)
        result["sma200"] = sma200
        result["sma20"] = sma20

    return result


@router.get("/market-overview")
def market_overview():
    """주요 종목 시세 요약 (QLD, QQQ, TQQQ)"""
    broker = get_broker()
    symbols = ["QLD", "QQQ", "TQQQ"]
    overview = []
    for sym in symbols:
        quote = broker.get_quote(sym)
        if quote:
            overview.append({
                "symbol": sym,
                "last": quote.last,
                "prev_close": quote.prev_close,
                "change_pct": round(
                    (quote.last - quote.prev_close) / quote.prev_close * 100, 2
                ) if quote.prev_close else 0,
                "volume": quote.volume,
            })
    return {
        "is_live": isinstance(broker, LiveDataBroker),
        "quotes": overview,
    }


@router.get("/{ticker}")
def symbol_detail(ticker: str, db: Session = Depends(get_db)):
    return get_symbol_detail(db, ticker.upper())
