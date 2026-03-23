import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from config import get_settings
from models import Symbol, Cycle, CycleState, BuyMode
from services.state_machine import transition

router = APIRouter(prefix="/api", tags=["settings"])


# --- Schemas ---

class SymbolCreate(BaseModel):
    ticker: str
    name: str
    market: str = "US"
    exchange: str = "NAS"


class CycleStart(BaseModel):
    ticker: str
    cycle_budget: float
    buy_mode: str = "PRICE_LADDER"
    tranche_count: int | None = None
    take_profit_pct: float | None = None
    add_trigger_pct: float | None = None
    soft_drawdown_pct: float | None = None
    hard_drawdown_pct: float | None = None


class StrategySettingsUpdate(BaseModel):
    symbol: str | None = None
    cycle_budget: float | None = None
    tranche_count: int | None = None
    loc_buy1_trigger: float | None = None
    loc_buy2_trigger: float | None = None
    loc_buy2_ratio: float | None = None
    loc_sell1_target: float | None = None
    loc_sell1_ratio: float | None = None
    loc_sell2_target: float | None = None
    loc_sell2_ratio: float | None = None
    hard_drawdown_pct: float | None = None
    rollback_on_exhaust: bool | None = None
    rollback_target_tranche: int | None = None
    cooldown_after_exit_min: int | None = None

class RegimeSettingsUpdate(BaseModel):
    enabled: bool | None = None
    symbol: str | None = None
    sma_period: int | None = None
    vix_filter_enabled: bool | None = None
    vix_max: float | None = None

class SettingsUpdate(BaseModel):
    strategy: StrategySettingsUpdate | None = None
    regime: RegimeSettingsUpdate | None = None


# --- 설정 ---

@router.get("/settings")
def get_current_settings():
    settings = get_settings()
    return {
        "strategy": settings.strategy.model_dump(),
        "regime": settings.regime.model_dump(),
        "risk": settings.risk.model_dump(),
        "kill_switch": settings.kill_switch.model_dump(),
        "notification": settings.notification.model_dump(),
        "broker_type": settings.broker_type,
        "decision_interval_sec": settings.decision_interval_sec,
    }


@router.put("/settings")
def update_settings(data: SettingsUpdate):
    """설정 업데이트 → .env 파일에 저장"""
    settings = get_settings()
    env_path = Path(__file__).parent.parent / ".env"
    env_lines: dict[str, str] = {}

    # 기존 .env 읽기
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_lines[k.strip()] = v.strip()

    # strategy 업데이트
    if data.strategy:
        for field, value in data.strategy.model_dump(exclude_none=True).items():
            setattr(settings.strategy, field, value)

    # regime 업데이트
    if data.regime:
        for field, value in data.regime.model_dump(exclude_none=True).items():
            setattr(settings.regime, field, value)

    # .env에 JSON으로 저장 (pydantic-settings가 읽을 수 있게)
    env_lines["BROKER_TYPE"] = settings.broker_type
    env_lines["STRATEGY"] = json.dumps(settings.strategy.model_dump(), ensure_ascii=False)
    env_lines["REGIME"] = json.dumps(settings.regime.model_dump(), ensure_ascii=False)

    env_path.write_text("\n".join(f"{k}={v}" for k, v in env_lines.items()) + "\n")

    # 캐시 클리어 (다음 호출 시 새 설정 로드)
    get_settings.cache_clear()

    return {"message": "설정 저장 완료"}


# --- 종목 관리 ---

@router.get("/symbols")
def list_symbols(db: Session = Depends(get_db)):
    symbols = db.query(Symbol).all()
    return [
        {
            "id": s.id,
            "ticker": s.ticker,
            "name": s.name,
            "market": s.market,
            "exchange": s.exchange,
            "is_enabled": s.is_enabled,
        }
        for s in symbols
    ]


@router.post("/symbols")
def add_symbol(data: SymbolCreate, db: Session = Depends(get_db)):
    ticker = data.ticker.upper()
    existing = db.query(Symbol).filter(Symbol.ticker == ticker).first()
    if existing:
        raise HTTPException(status_code=400, detail="이미 등록된 종목입니다")

    symbol = Symbol(
        ticker=ticker,
        name=data.name,
        market=data.market,
        exchange=data.exchange,
        is_enabled=True,
    )
    db.add(symbol)
    db.commit()
    db.refresh(symbol)
    return {"id": symbol.id, "message": f"{ticker} 등록 완료"}


@router.put("/symbols/{symbol_id}/toggle")
def toggle_symbol(symbol_id: int, db: Session = Depends(get_db)):
    symbol = db.query(Symbol).filter(Symbol.id == symbol_id).first()
    if not symbol:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

    # 활성 사이클 있으면 비활성화 불가
    if symbol.is_enabled:
        active = db.query(Cycle).filter(
            Cycle.symbol_id == symbol.id,
            Cycle.state.notin_([CycleState.HALTED, CycleState.COOLDOWN]),
        ).count()
        if active > 0:
            raise HTTPException(status_code=400, detail="진행 중인 사이클이 있어 비활성화할 수 없습니다")

    symbol.is_enabled = not symbol.is_enabled
    db.commit()
    return {
        "is_enabled": symbol.is_enabled,
        "message": f"{symbol.ticker} {'활성화' if symbol.is_enabled else '비활성화'} 완료",
    }


# --- 사이클 ---

@router.post("/cycle/start")
def start_cycle(data: CycleStart, db: Session = Depends(get_db)):
    settings = get_settings()
    ticker = data.ticker.upper()

    symbol = db.query(Symbol).filter(Symbol.ticker == ticker).first()
    if not symbol:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    if not symbol.is_enabled:
        raise HTTPException(status_code=400, detail="비활성화된 종목입니다")

    # 종목당 1사이클만 허용 (규칙서 v1)
    active = db.query(Cycle).filter(
        Cycle.symbol_id == symbol.id,
        Cycle.state.notin_([CycleState.HALTED, CycleState.COOLDOWN]),
    ).first()
    if active:
        raise HTTPException(status_code=400, detail="이미 진행 중인 사이클이 있습니다")

    cycle = Cycle(
        symbol_id=symbol.id,
        state=CycleState.BOOTSTRAP,
        buy_mode=BuyMode(data.buy_mode),
        cycle_budget=data.cycle_budget,
        tranche_count=data.tranche_count or settings.strategy.tranche_count,
        take_profit_pct=data.take_profit_pct or settings.strategy.loc_sell1_target,
        add_trigger_pct=data.add_trigger_pct or settings.strategy.loc_buy2_trigger,
        soft_drawdown_pct=data.soft_drawdown_pct or settings.strategy.hard_drawdown_pct * 0.5,
        hard_drawdown_pct=data.hard_drawdown_pct or settings.strategy.hard_drawdown_pct,
    )
    db.add(cycle)
    db.commit()
    db.refresh(cycle)

    return {"id": cycle.id, "message": f"{ticker} 새 사이클 시작 (BOOTSTRAP)"}


@router.post("/cycle/{cycle_id}/halt")
def halt_cycle(cycle_id: int, db: Session = Depends(get_db)):
    """수동 정지 (킬스위치, 규칙서 §11)"""
    cycle = db.query(Cycle).filter(Cycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="사이클을 찾을 수 없습니다")
    if cycle.state == CycleState.HALTED:
        raise HTTPException(status_code=400, detail="이미 정지 상태입니다")

    transition(db, cycle, CycleState.HALTED, "운영자 수동 정지")
    db.commit()
    return {"message": "사이클 수동 정지 완료"}


@router.post("/cycle/{cycle_id}/resume")
def resume_cycle(cycle_id: int, db: Session = Depends(get_db)):
    """HALTED → BOOTSTRAP 재시작"""
    cycle = db.query(Cycle).filter(Cycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="사이클을 찾을 수 없습니다")
    if cycle.state != CycleState.HALTED:
        raise HTTPException(status_code=400, detail="정지 상태에서만 재시작할 수 있습니다")

    transition(db, cycle, CycleState.BOOTSTRAP, "운영자 수동 재시작")
    cycle.consecutive_rejects = 0
    db.commit()
    return {"message": "사이클 재시작 (BOOTSTRAP)"}


@router.post("/cycle/{cycle_id}/resolve")
def resolve_manual_review(cycle_id: int, db: Session = Depends(get_db)):
    """MANUAL_REVIEW 해소"""
    cycle = db.query(Cycle).filter(Cycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="사이클을 찾을 수 없습니다")
    if cycle.state != CycleState.MANUAL_REVIEW:
        raise HTTPException(status_code=400, detail="MANUAL_REVIEW 상태에서만 가능합니다")

    target = CycleState.HOLDING if cycle.total_quantity > 0 else CycleState.READY
    transition(db, cycle, target, "운영자 수동 해소")
    db.commit()
    return {"message": f"MANUAL_REVIEW 해소 → {target.value}"}
