"""리스크 관리 (규칙서 §7, §9, §10, §11, §13)

역할:
1. 진입 게이트 점검 (§7-1)
2. 리스크 모드 판단 (NORMAL / BUY_BLOCKED / OBSERVE_ONLY / HALTED)
3. 매도 조건 (익절/소프트/하드) (§9)
4. 킬스위치 (§11)
5. 레짐 필터 (§13)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from config import get_settings
from models import Cycle, CycleState, RegimeMode

logger = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    """시세 스냅샷"""
    symbol: str
    bid: float
    ask: float
    mid: float
    last: float
    spread_bps: float
    volume: int
    timestamp: datetime
    prev_close: float = 0.0
    # 레짐 데이터
    qqq_close: float = 0.0
    qqq_sma200: float = 0.0
    qqq_sma20: float = 0.0
    qqq_sma20_slope: float = 0.0  # >= 0이면 상승
    # 변동성
    vol_15m_ann: float = 0.0
    # 세션
    market_open: bool = True
    minutes_since_open: int = 0
    minutes_until_close: int = 0


@dataclass
class RiskAssessment:
    """리스크 판단 결과"""
    mode: str  # NORMAL, BUY_BLOCKED, OBSERVE_ONLY, HALTED
    reasons: list[str]
    regime: RegimeMode
    entry_gate_ok: bool
    can_buy: bool
    can_sell: bool


def assess_regime(snapshot: MarketSnapshot) -> RegimeMode:
    """레짐 필터 (규칙서 §13)

    REGIME_ON:  QQQ > SMA200 AND SMA20 slope >= 0
    REGIME_CAUTION: 하나만 만족
    REGIME_OFF: 둘 다 불만족
    """
    if snapshot.qqq_sma200 <= 0 or snapshot.qqq_sma20 <= 0:
        return RegimeMode.ON  # 데이터 없으면 ON (mock)

    above_sma200 = snapshot.qqq_close > snapshot.qqq_sma200
    sma20_rising = snapshot.qqq_sma20_slope >= 0

    if above_sma200 and sma20_rising:
        return RegimeMode.ON
    elif above_sma200 or sma20_rising:
        return RegimeMode.CAUTION
    else:
        return RegimeMode.OFF


def check_entry_gate(
    cycle: Cycle,
    snapshot: MarketSnapshot,
) -> tuple[bool, list[str]]:
    """진입 게이트 (규칙서 §7-1)

    Returns:
        (통과 여부, 실패 사유 목록)
    """
    settings = get_settings()
    reasons: list[str] = []

    # 장 열림 확인
    if not snapshot.market_open:
        reasons.append("장이 열리지 않음")

    # 장 초반 제한
    if snapshot.minutes_since_open < settings.session.no_new_buy_first_min:
        reasons.append(f"장 시작 후 {settings.session.no_new_buy_first_min}분 미경과")

    # 장 마감 제한
    if snapshot.minutes_until_close < settings.session.no_new_buy_last_min:
        reasons.append(f"장 마감 {settings.session.no_new_buy_last_min}분 전")

    # 스프레드 가드
    if snapshot.spread_bps > settings.risk.spread_guard_bps:
        reasons.append(f"스프레드 {snapshot.spread_bps:.1f}bps > 한도 {settings.risk.spread_guard_bps}bps")

    # 갭 가드 (전일 종가 대비)
    if snapshot.prev_close > 0:
        gap_pct = abs(snapshot.mid - snapshot.prev_close) / snapshot.prev_close
        if gap_pct > settings.risk.gap_guard_pct:
            reasons.append(f"갭 {gap_pct*100:.1f}% > 한도 {settings.risk.gap_guard_pct*100:.1f}%")

    # 변동성 가드
    if snapshot.vol_15m_ann > settings.risk.vol_guard_15m_ann:
        reasons.append(f"변동성 {snapshot.vol_15m_ann:.2f} > 한도 {settings.risk.vol_guard_15m_ann:.2f}")

    # 시세 유효성
    staleness = (datetime.utcnow() - snapshot.timestamp).total_seconds()
    if staleness > settings.risk.stale_quote_sec:
        reasons.append(f"시세 {staleness:.0f}초 지연 (한도 {settings.risk.stale_quote_sec}초)")

    # 레짐 필터
    regime = assess_regime(snapshot)
    if regime == RegimeMode.OFF:
        reasons.append("레짐 OFF: 신규 매수 금지")

    # 쿨다운
    if cycle.cooldown_until and datetime.utcnow() < cycle.cooldown_until:
        remaining = (cycle.cooldown_until - datetime.utcnow()).total_seconds()
        reasons.append(f"쿨다운 중 (잔여 {remaining:.0f}초)")

    return len(reasons) == 0, reasons


def assess_risk(
    cycle: Cycle,
    snapshot: MarketSnapshot,
) -> RiskAssessment:
    """종합 리스크 판단 (규칙서 §6, §10)

    Returns:
        RiskAssessment
    """
    settings = get_settings()
    reasons: list[str] = []
    regime = assess_regime(snapshot)

    # --- HALTED 조건 (킬스위치, §11) ---
    if cycle.consecutive_rejects >= settings.kill_switch.max_consecutive_rejects:
        return RiskAssessment(
            mode="HALTED",
            reasons=[f"연속 주문 거부 {cycle.consecutive_rejects}회"],
            regime=regime,
            entry_gate_ok=False, can_buy=False, can_sell=False,
        )

    # 시세 유효성
    staleness = (datetime.utcnow() - snapshot.timestamp).total_seconds()

    # --- OBSERVE_ONLY 조건 (§10-2) ---
    if staleness > settings.risk.stale_quote_sec:
        return RiskAssessment(
            mode="OBSERVE_ONLY",
            reasons=[f"시세 {staleness:.0f}초 지연"],
            regime=regime,
            entry_gate_ok=False, can_buy=False, can_sell=False,
        )

    # --- BUY_BLOCKED 조건 (§10-1) ---
    buy_blocked_reasons: list[str] = []

    if regime == RegimeMode.OFF:
        buy_blocked_reasons.append("레짐 OFF")

    if not snapshot.market_open:
        buy_blocked_reasons.append("장 비개장")

    if snapshot.minutes_since_open < settings.session.no_new_buy_first_min:
        buy_blocked_reasons.append("장 초반 제한")

    if snapshot.minutes_until_close < settings.session.no_new_buy_last_min:
        buy_blocked_reasons.append("장 마감 제한")

    if snapshot.spread_bps > settings.risk.spread_guard_bps:
        buy_blocked_reasons.append(f"스프레드 과다 ({snapshot.spread_bps:.1f}bps)")

    if snapshot.vol_15m_ann > settings.risk.vol_guard_15m_ann:
        buy_blocked_reasons.append(f"변동성 과다 ({snapshot.vol_15m_ann:.2f})")

    # soft drawdown 체크
    if cycle.total_quantity > 0 and cycle.avg_cost > 0:
        current_dd = (cycle.avg_cost - snapshot.mid) / cycle.avg_cost
        if current_dd > cycle.soft_drawdown_pct:
            buy_blocked_reasons.append(f"소프트 드로다운 {current_dd*100:.1f}% > {cycle.soft_drawdown_pct*100:.1f}%")

    entry_ok, entry_reasons = check_entry_gate(cycle, snapshot)

    if buy_blocked_reasons:
        return RiskAssessment(
            mode="BUY_BLOCKED",
            reasons=buy_blocked_reasons,
            regime=regime,
            entry_gate_ok=False,
            can_buy=False,
            can_sell=True,  # 매도는 허용
        )

    # --- NORMAL ---
    return RiskAssessment(
        mode="NORMAL",
        reasons=[],
        regime=regime,
        entry_gate_ok=entry_ok,
        can_buy=entry_ok,
        can_sell=True,
    )


def should_take_profit(cycle: Cycle, snapshot: MarketSnapshot) -> bool:
    """익절 조건 (규칙서 §9-1)

    cycle_pnl_pct >= take_profit_pct
    """
    if cycle.total_quantity <= 0 or cycle.avg_cost <= 0:
        return False

    pnl_pct = (snapshot.mid - cycle.avg_cost) / cycle.avg_cost
    return pnl_pct >= cycle.take_profit_pct


def should_hard_exit(cycle: Cycle, snapshot: MarketSnapshot) -> tuple[bool, str]:
    """하드 리스크 청산 (규칙서 §9-3)

    Returns:
        (청산 여부, 사유)
    """
    settings = get_settings()

    if cycle.total_quantity <= 0 or cycle.avg_cost <= 0:
        return False, ""

    dd = (cycle.avg_cost - snapshot.mid) / cycle.avg_cost

    # hard drawdown
    if dd > cycle.hard_drawdown_pct:
        return True, f"하드 드로다운 {dd*100:.1f}% > {cycle.hard_drawdown_pct*100:.1f}%"

    # 일일 손실 한도 (미실현 기준)
    unrealized_loss_pct = dd
    if unrealized_loss_pct > settings.risk.daily_loss_limit_pct:
        return True, f"일일 손실 한도 초과 {unrealized_loss_pct*100:.1f}%"

    return False, ""


def should_add_tranche(
    cycle: Cycle,
    snapshot: MarketSnapshot,
) -> tuple[bool, str]:
    """추가매수 조건 (규칙서 §8, PRICE_LADDER)

    current_mid <= last_buy_fill_price * (1 - add_trigger_pct)
    """
    settings = get_settings()

    # 남은 tranche
    if cycle.steps_used >= cycle.tranche_count:
        return False, f"tranche 소진 ({cycle.steps_used}/{cycle.tranche_count})"

    # 일일 매수 횟수
    today = datetime.utcnow().strftime("%Y-%m-%d")
    daily_count = cycle.daily_buy_count if cycle.daily_buy_date == today else 0
    max_daily = settings.strategy.max_daily_buys
    # CAUTION 레짐이면 1로 축소
    regime = assess_regime(snapshot)
    if regime == RegimeMode.CAUTION:
        max_daily = 1
    if daily_count >= max_daily:
        return False, f"일일 매수 상한 ({daily_count}/{max_daily})"

    # 마지막 체결 후 안정화 시간
    if cycle.last_fill_at:
        elapsed = (datetime.utcnow() - cycle.last_fill_at).total_seconds()
        if elapsed < settings.cascade.min_seconds_between_buys:
            return False, f"매수 간격 미충족 ({elapsed:.0f}s < {settings.cascade.min_seconds_between_buys}s)"

    if cycle.buy_mode == BuyMode.PRICE_LADDER:
        if cycle.last_buy_fill_price <= 0:
            return False, "마지막 매수가 없음"

        trigger_price = cycle.last_buy_fill_price * (1 - cycle.add_trigger_pct)
        if snapshot.mid <= trigger_price:
            return True, (
                f"PRICE_LADDER 발동: mid {snapshot.mid:.2f} <= "
                f"trigger {trigger_price:.2f} "
                f"(last_fill {cycle.last_buy_fill_price:.2f} × "
                f"{1 - cycle.add_trigger_pct:.3f})"
            )
        return False, f"하락 미달: mid {snapshot.mid:.2f} > trigger {trigger_price:.2f}"
    else:
        # DAILY_TRANCHE: 스케줄러가 호출
        return True, "DAILY_TRANCHE 스케줄 매수"


# BuyMode import
from models import BuyMode
