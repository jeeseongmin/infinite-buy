"""상태머신 (규칙서 §5)

상태 전이 규칙:
  BOOTSTRAP → READY                : 장 시작 점검 통과
  READY → BUY_PENDING              : 진입 신호 + 모든 가드 통과
  BUY_PENDING → HOLDING            : 매수 체결 완료
  HOLDING → SELL_PENDING           : 익절/리스크청산 신호
  SELL_PENDING → COOLDOWN          : 전량 청산 완료
  COOLDOWN → READY                 : 쿨다운 종료
  ANY → BUY_BLOCKED               : 매크로/변동성/갭 위험
  ANY → OBSERVE_ONLY              : 시세 지연, 부분체결 불안정
  ANY → MANUAL_REVIEW             : 포지션 불일치
  ANY → HALTED                    : 중대 오류 또는 킬스위치
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from models import Cycle, CycleState, EventLog

logger = logging.getLogger(__name__)

# 허용 전이 맵 (from → [to, ...])
ALLOWED_TRANSITIONS: dict[CycleState, set[CycleState]] = {
    CycleState.BOOTSTRAP: {
        CycleState.READY,
        CycleState.HALTED,
        CycleState.MANUAL_REVIEW,
    },
    CycleState.READY: {
        CycleState.BUY_PENDING,
        CycleState.BUY_BLOCKED,
        CycleState.OBSERVE_ONLY,
        CycleState.MANUAL_REVIEW,
        CycleState.HALTED,
    },
    CycleState.BUY_PENDING: {
        CycleState.HOLDING,
        CycleState.READY,           # 주문 취소/거부 시
        CycleState.OBSERVE_ONLY,
        CycleState.MANUAL_REVIEW,
        CycleState.HALTED,
    },
    CycleState.HOLDING: {
        CycleState.BUY_PENDING,     # 추가매수
        CycleState.SELL_PENDING,
        CycleState.BUY_BLOCKED,
        CycleState.OBSERVE_ONLY,
        CycleState.MANUAL_REVIEW,
        CycleState.HALTED,
    },
    CycleState.SELL_PENDING: {
        CycleState.COOLDOWN,
        CycleState.HOLDING,         # 매도 취소/거부 시
        CycleState.OBSERVE_ONLY,
        CycleState.MANUAL_REVIEW,
        CycleState.HALTED,
    },
    CycleState.BUY_BLOCKED: {
        CycleState.HOLDING,         # 위험 해소 후 보유 상태로
        CycleState.READY,           # 위험 해소 + 포지션 없음
        CycleState.SELL_PENDING,    # 매도는 허용
        CycleState.OBSERVE_ONLY,
        CycleState.MANUAL_REVIEW,
        CycleState.HALTED,
    },
    CycleState.OBSERVE_ONLY: {
        CycleState.READY,
        CycleState.HOLDING,
        CycleState.BUY_BLOCKED,
        CycleState.MANUAL_REVIEW,
        CycleState.HALTED,
    },
    CycleState.COOLDOWN: {
        CycleState.READY,
        CycleState.HALTED,
    },
    CycleState.MANUAL_REVIEW: {
        CycleState.READY,
        CycleState.HOLDING,
        CycleState.HALTED,
    },
    CycleState.HALTED: {
        CycleState.BOOTSTRAP,       # 수동 재시작만
    },
}


class TransitionError(Exception):
    pass


def transition(
    db: Session,
    cycle: Cycle,
    to_state: CycleState,
    reason: str = "",
) -> Cycle:
    """상태 전이 실행

    Args:
        db: DB 세션
        cycle: 대상 사이클
        to_state: 목표 상태
        reason: 전이 사유

    Returns:
        업데이트된 사이클

    Raises:
        TransitionError: 허용되지 않는 전이
    """
    from_state = cycle.state
    allowed = ALLOWED_TRANSITIONS.get(from_state, set())

    if to_state not in allowed:
        msg = f"허용되지 않는 전이: {from_state.value} → {to_state.value}"
        logger.error(f"[{cycle.symbol.ticker}] {msg}")
        raise TransitionError(msg)

    cycle.prev_state = from_state
    cycle.state = to_state
    cycle.state_reason = reason
    cycle.state_changed_at = datetime.utcnow()

    # 이벤트 로그
    db.add(EventLog(
        cycle_id=cycle.id,
        event_type="STATE_CHANGE",
        level="INFO",
        message=f"{from_state.value} → {to_state.value}: {reason}",
        data={"from": from_state.value, "to": to_state.value, "reason": reason},
    ))

    logger.info(f"[{cycle.symbol.ticker}] {from_state.value} → {to_state.value}: {reason}")
    return cycle


def can_transition(cycle: Cycle, to_state: CycleState) -> bool:
    """전이 가능 여부 확인"""
    return to_state in ALLOWED_TRANSITIONS.get(cycle.state, set())


def is_tradable(cycle: Cycle) -> bool:
    """주문 가능 상태인지"""
    return cycle.state in {
        CycleState.READY,
        CycleState.HOLDING,
        CycleState.BUY_BLOCKED,  # 매도만 가능
    }


def can_buy(cycle: Cycle) -> bool:
    """매수 가능 상태인지"""
    return cycle.state in {CycleState.READY, CycleState.HOLDING}


def can_sell(cycle: Cycle) -> bool:
    """매도 가능 상태인지"""
    return cycle.state in {
        CycleState.HOLDING,
        CycleState.BUY_BLOCKED,
    }
