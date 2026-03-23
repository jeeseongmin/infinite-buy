"""무한매수법 전체 설정 - LOC(종가지정가) 기반"""

from pydantic_settings import BaseSettings
from pydantic import BaseModel
from functools import lru_cache


# ===== 사용자가 설정하는 핵심 항목 =====

class StrategyConfig(BaseModel):
    """전략 설정 (사이클 시작 시 사용자가 정하는 값)"""

    # 종목
    symbol: str = "TQQQ"               # 매매 종목 (TQQQ, QLD, SOXL 등)

    # 자금
    cycle_budget: float = 10000.0       # 이번 사이클 총 예산 (달러)
    tranche_count: int = 16             # 총 트랜치 횟수 (16회가 기본)

    # LOC 매수 설정
    loc_buy1_trigger: float = 0.001     # 매수 LOC 1: 평단 × (1 - 이 값) 이하. 0.001 = 평단 바로 아래
    loc_buy2_trigger: float = 0.05      # 매수 LOC 2: 평단 × (1 - 이 값) 이하. 0.05 = 평단 -5% (몸집 불리기)
    loc_buy2_ratio: float = 0.5         # 매수 LOC 2의 수량 비율 (트랜치의 50%)

    # LOC 매도 설정
    loc_sell1_target: float = 0.05      # 매도 LOC 1: 평단 × (1 + 이 값). 0.05 = +5%
    loc_sell1_ratio: float = 0.25       # 매도 LOC 1의 수량 비율 (보유의 25%)
    loc_sell2_target: float = 0.10      # 매도 LOC 2: 평단 × (1 + 이 값). 0.10 = +10%
    loc_sell2_ratio: float = 0.75       # 매도 LOC 2의 수량 비율 (보유의 75%, 나머지 전부)

    # 손절
    hard_drawdown_pct: float = 0.12     # 평단 대비 이 비율 이상 하락 시 전량 손절 (12%)
    rollback_on_exhaust: bool = True    # 16트랜치 소진 + 매도 안 됨 → 일부 손절 후 롤백
    rollback_target_tranche: int = 12   # 롤백 시 돌아갈 트랜치 수준 (약 12회차)

    # 쿨다운
    cooldown_after_exit_min: int = 30   # 사이클 종료 후 다음 사이클까지 대기 (분)


class RegimeConfig(BaseModel):
    """레짐 필터 (시장 전체 건강 체크)"""
    enabled: bool = True                # 레짐 필터 사용 여부
    symbol: str = "QQQ"                 # 레짐 판단 기준 종목
    sma_period: int = 200               # 이동평균선 기간 (200일)
    # QQQ > SMA200 → 레짐 ON (매수 허용)
    # QQQ < SMA200 → 레짐 OFF (신규매수 중단)

    # 변동성 필터 (VIX 기반, 선택)
    vix_filter_enabled: bool = False    # VIX 필터 사용 여부
    vix_max: float = 30.0              # VIX가 이 값 이상이면 매수 중단


class RiskConfig(BaseModel):
    """리스크 관리"""
    spread_guard_bps: float = 12.0      # 호가 스프레드 12bps 이상이면 매수 보류
    gap_guard_pct: float = 0.022        # 전일 종가 대비 2.2% 이상 갭이면 관망
    daily_loss_limit_pct: float = 0.02  # 일일 손실 한도 2%


class KillSwitchConfig(BaseModel):
    """킬스위치 (자동 정지 조건)"""
    max_consecutive_rejects: int = 3    # 연속 주문 거부 3회 → 자동 정지
    stale_quote_sec: int = 2            # 시세 지연 2초 이상 → 정지
    pos_mismatch_timeout_sec: int = 60  # 포지션 불일치 60초 이상 → 정지
    daily_loss_limit_pct: float = 0.02  # 일일 손실 한도 초과 → 정지


class NotificationConfig(BaseModel):
    """알림 설정"""
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # 알림 받을 이벤트
    notify_on_buy: bool = True          # 매수 체결 시
    notify_on_sell: bool = True         # 매도 체결 시
    notify_on_stop_loss: bool = True    # 손절 시
    notify_on_cycle_complete: bool = True  # 사이클 완료 시
    notify_on_error: bool = True        # 에러 발생 시


# ===== 전체 앱 설정 =====

class Settings(BaseSettings):
    """전체 앱 설정 (.env 또는 환경변수로 오버라이드 가능)"""

    # 서버
    api_secret_key: str = "change-me"
    db_path: str = "./infinite_buy.db"

    # 브로커
    broker_type: str = "mock"           # mock | live | kiwoom
    broker_api_key: str = ""
    broker_api_secret: str = ""

    # 키움증권
    kiwoom_account: str = ""            # 계좌번호
    kiwoom_password: str = ""           # 계좌 비밀번호

    # 전략
    strategy: StrategyConfig = StrategyConfig()
    regime: RegimeConfig = RegimeConfig()
    risk: RiskConfig = RiskConfig()
    kill_switch: KillSwitchConfig = KillSwitchConfig()
    notification: NotificationConfig = NotificationConfig()

    # 스케줄러
    decision_interval_sec: int = 60     # 의사결정 루프 주기 (초)

    # 하위 호환 (기존 코드 참조용)
    @property
    def regime_symbol(self) -> str:
        return self.regime.symbol

    @property
    def regime_sma_long(self) -> int:
        return self.regime.sma_period

    @property
    def regime_sma_short(self) -> int:
        return 20

    @property
    def session(self):
        """기존 코드 호환용 더미"""
        class _Session:
            no_new_buy_first_min = 5
            no_new_buy_last_min = 20
            regular_session_only = True
            market_open_hour = 9
            market_open_min = 30
            market_close_hour = 16
            market_close_min = 0
        return _Session()

    @property
    def execution(self):
        """기존 코드 호환용 더미"""
        class _Execution:
            order_type = "loc"
            buy_limit_offset_bps = 4.0
            sell_limit_offset_bps = 4.0
            cancel_after_sec = 20
            max_replace_count = 2
            stabilization_after_buy_sec = 5
            stabilization_after_sell_sec = 5
        return _Execution()

    @property
    def cascade(self):
        """기존 코드 호환용 더미"""
        class _Cascade:
            max_new_tranches_per_bar = 1
            min_seconds_between_buys = 60
            max_daily_buys = 3
        return _Cascade()

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
