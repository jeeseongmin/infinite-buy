"""v1 규칙서 기반 전체 설정"""

from pydantic_settings import BaseSettings
from pydantic import BaseModel
from functools import lru_cache


class StrategyConfig(BaseModel):
    """전략 설정 (규칙서 §4, §14)"""
    symbol: str = "QLD"
    buy_mode: str = "PRICE_LADDER"  # PRICE_LADDER | DAILY_TRANCHE
    cycle_budget_ratio: float = 0.08
    tranche_count: int = 16
    take_profit_pct: float = 0.014  # 평균단가 대비 목표 수익률
    add_trigger_pct: float = 0.015  # 추가매수 발동 하락률
    soft_drawdown_pct: float = 0.06
    hard_drawdown_pct: float = 0.12
    max_daily_buys: int = 3
    cooldown_after_exit_min: int = 30


class SessionConfig(BaseModel):
    """장 시간 설정 (규칙서 §7, §14)"""
    no_new_buy_first_min: int = 5
    no_new_buy_last_min: int = 20
    regular_session_only: bool = True
    # 미국 정규장 (ET 기준)
    market_open_hour: int = 9
    market_open_min: int = 30
    market_close_hour: int = 16
    market_close_min: int = 0


class RiskConfig(BaseModel):
    """리스크 설정 (규칙서 §10, §11, §14)"""
    spread_guard_bps: float = 12.0
    gap_guard_pct: float = 0.022
    vol_guard_15m_ann: float = 0.65
    daily_loss_limit_pct: float = 0.02
    stale_quote_sec: int = 2
    order_ack_timeout_sec: int = 5
    pos_mismatch_timeout_sec: int = 60


class ExecutionConfig(BaseModel):
    """주문 실행 설정 (규칙서 §15, §14)"""
    order_type: str = "limit"
    buy_limit_offset_bps: float = 4.0
    sell_limit_offset_bps: float = 4.0
    cancel_after_sec: int = 20
    max_replace_count: int = 2
    stabilization_after_buy_sec: int = 5
    stabilization_after_sell_sec: int = 5


class CascadeProtection(BaseModel):
    """급락 시 연속 매수 방지 (규칙서 §8)"""
    max_new_tranches_per_bar: int = 1
    min_seconds_between_buys: int = 60
    max_daily_buys: int = 3


class SymbolAdmission(BaseModel):
    """종목 허용 조건 (규칙서 §2-2)"""
    min_price: float = 20.0
    min_aum_usd: float = 500_000_000
    min_avg_dollar_volume_30d: float = 100_000_000
    max_median_spread_bps_30d: float = 12.0
    allow_sector_3x: bool = False
    allow_inverse: bool = False


class KillSwitchConfig(BaseModel):
    """킬스위치 설정 (규칙서 §11)"""
    max_consecutive_rejects: int = 3
    stale_quote_sec: int = 2
    order_ack_timeout_sec: int = 5
    pos_mismatch_timeout_sec: int = 60
    daily_loss_limit_pct: float = 0.02
    duplicate_order_detected: bool = True


class Settings(BaseSettings):
    """전체 앱 설정"""
    # 텔레그램
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # 서버
    api_secret_key: str = "change-me"
    db_path: str = "./infinite_buy.db"

    # 브로커
    broker_type: str = "mock"  # mock | kiwoom | alpaca
    broker_api_key: str = ""
    broker_api_secret: str = ""

    # 전략 (v1 QLD 기본값)
    strategy: StrategyConfig = StrategyConfig()
    session: SessionConfig = SessionConfig()
    risk: RiskConfig = RiskConfig()
    execution: ExecutionConfig = ExecutionConfig()
    cascade: CascadeProtection = CascadeProtection()
    kill_switch: KillSwitchConfig = KillSwitchConfig()
    symbol_admission: SymbolAdmission = SymbolAdmission()

    # 의사결정 주기
    decision_interval_sec: int = 60

    # 레짐 필터
    regime_symbol: str = "QQQ"
    regime_sma_long: int = 200
    regime_sma_short: int = 20

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
