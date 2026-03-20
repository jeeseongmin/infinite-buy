"""의사결정 스케줄러 (규칙서 §4 decision_interval_sec 기반)

역할:
1. decision_interval_sec 마다 모든 활성 사이클에 evaluate() 호출
2. COOLDOWN 만료 체크
3. BOOTSTRAP → READY 전이 (장 시작 시)
"""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from database import SessionLocal
from config import get_settings
from models import Cycle, Symbol, CycleState
from services.strategy import evaluate
from services.state_machine import transition
from services.telegram_bot import telegram_bot

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_paused = False


def is_paused() -> bool:
    return _paused


def set_paused(value: bool):
    global _paused
    _paused = value


async def run_decision_loop():
    """메인 의사결정 루프

    모든 활성 사이클에 대해 evaluate() 실행
    """
    if _paused:
        return

    db: Session = SessionLocal()
    try:
        # 활성 사이클 조회 (HALTED 제외)
        cycles = (
            db.query(Cycle)
            .join(Symbol)
            .filter(
                Symbol.is_enabled.is_(True),
                Cycle.state.notin_([CycleState.HALTED]),
            )
            .all()
        )

        for cycle in cycles:
            try:
                # COOLDOWN 만료 체크
                if cycle.state == CycleState.COOLDOWN:
                    if cycle.cooldown_until and datetime.utcnow() >= cycle.cooldown_until:
                        transition(db, cycle, CycleState.READY, "쿨다운 종료")
                        db.commit()
                        logger.info(f"[{cycle.symbol.ticker}] 쿨다운 종료 → READY")
                    continue

                # BOOTSTRAP → READY (장 시작 점검)
                if cycle.state == CycleState.BOOTSTRAP:
                    # TODO: 실제 장 시작 점검 로직
                    transition(db, cycle, CycleState.READY, "장 시작 점검 통과")
                    db.commit()
                    continue

                # 의사결정
                result = evaluate(db, cycle)
                logger.info(f"[{cycle.symbol.ticker}] {result.action}: {result.reason}")

                # 텔레그램 알림 (체결 시)
                if result.order and result.action == "BUY":
                    await telegram_bot.notify_buy(
                        ticker=cycle.symbol.ticker,
                        quantity=result.order.filled_quantity,
                        price=result.order.filled_avg_price,
                        avg_cost=cycle.avg_cost,
                        step=cycle.steps_used,
                        tranche_count=cycle.tranche_count,
                    )
                elif result.order and result.action == "SELL":
                    await telegram_bot.notify_sell(
                        ticker=cycle.symbol.ticker,
                        quantity=result.order.filled_quantity,
                        price=result.order.filled_avg_price,
                        pnl=cycle.realized_pnl,
                        pnl_pct=cycle.realized_pnl_pct,
                    )
                elif result.action == "HALT":
                    await telegram_bot.notify_error(
                        f"[{cycle.symbol.ticker}] HALTED: {result.reason}"
                    )

            except Exception as e:
                logger.error(f"사이클 {cycle.id} 처리 실패: {e}", exc_info=True)
                await telegram_bot.notify_error(
                    f"[{cycle.symbol.ticker}] 오류: {e}"
                )
    finally:
        db.close()


def setup_scheduler():
    """스케줄러 설정"""
    settings = get_settings()

    scheduler.add_job(
        run_decision_loop,
        IntervalTrigger(seconds=settings.decision_interval_sec),
        id="decision_loop",
        name="의사결정 루프",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        f"스케줄러 시작: 의사결정 주기 {settings.decision_interval_sec}초"
    )
