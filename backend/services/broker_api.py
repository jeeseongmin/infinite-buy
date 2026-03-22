"""브로커 API 추상화 (규칙서 §15, §20)

v1: Mock 모드 + 키움증권 래퍼
limit order 전용, 시장가 금지
"""

import hashlib
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import yfinance as yf

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class Quote:
    """시세 데이터"""
    symbol: str
    bid: float
    ask: float
    mid: float
    last: float
    spread_bps: float
    volume: int
    timestamp: datetime
    prev_close: float = 0.0


@dataclass
class OrderResult:
    """주문 응답"""
    success: bool
    broker_order_id: str
    message: str
    filled_quantity: int = 0
    filled_price: float = 0.0


@dataclass
class PositionInfo:
    """브로커 포지션"""
    symbol: str
    quantity: int
    avg_cost: float
    market_value: float


class BrokerAPI(ABC):
    """브로커 인터페이스"""

    @abstractmethod
    def get_quote(self, symbol: str) -> Optional[Quote]:
        ...

    @abstractmethod
    def submit_limit_buy(
        self, symbol: str, quantity: int, limit_price: float, client_order_id: str
    ) -> OrderResult:
        ...

    @abstractmethod
    def submit_limit_sell(
        self, symbol: str, quantity: int, limit_price: float, client_order_id: str
    ) -> OrderResult:
        ...

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool:
        ...

    @abstractmethod
    def get_order_status(self, broker_order_id: str) -> Optional[dict]:
        ...

    @abstractmethod
    def get_positions(self) -> list[PositionInfo]:
        ...

    # --- LOC (Limit On Close) 주문 ---
    # 기본 구현은 NotImplementedError. 키움 등 LOC 지원 브로커에서 오버라이드.

    def submit_loc_buy(
        self, symbol: str, quantity: int, limit_price: float, client_order_id: str
    ) -> OrderResult:
        """LOC 매수: 종가가 limit_price 이하면 종가에 체결"""
        raise NotImplementedError("이 브로커는 LOC 주문을 지원하지 않습니다")

    def submit_loc_sell(
        self, symbol: str, quantity: int, limit_price: float, client_order_id: str
    ) -> OrderResult:
        """LOC 매도: 종가가 limit_price 이상이면 종가에 체결"""
        raise NotImplementedError("이 브로커는 LOC 주문을 지원하지 않습니다")

    def supports_loc(self) -> bool:
        """LOC 주문 지원 여부"""
        return False

    @abstractmethod
    def is_connected(self) -> bool:
        ...


class MockBroker(BrokerAPI):
    """Mock 브로커 (개발/테스트용)"""

    def __init__(self):
        self._connected = True
        self._order_counter = 0
        self._positions: dict[str, PositionInfo] = {}
        # 시뮬레이션 가격 (외부에서 설정 가능)
        self._prices: dict[str, float] = {
            "QLD": 85.0,
            "TQQQ": 55.0,
            "QQQ": 480.0,
        }

    def set_price(self, symbol: str, price: float):
        self._prices[symbol] = price

    def get_quote(self, symbol: str) -> Optional[Quote]:
        price = self._prices.get(symbol, 50.0)
        spread = price * 0.0004  # 4bps
        return Quote(
            symbol=symbol,
            bid=price - spread / 2,
            ask=price + spread / 2,
            mid=price,
            last=price,
            spread_bps=4.0,
            volume=1_000_000,
            timestamp=datetime.utcnow(),
            prev_close=price * 0.998,
        )

    def submit_limit_buy(
        self, symbol: str, quantity: int, limit_price: float, client_order_id: str
    ) -> OrderResult:
        self._order_counter += 1
        oid = f"MOCK-B-{self._order_counter}"
        logger.info(
            f"[MOCK] BUY {symbol} qty={quantity} limit={limit_price:.2f} "
            f"coid={client_order_id}"
        )
        # Mock: 즉시 체결
        pos = self._positions.get(symbol, PositionInfo(symbol, 0, 0.0, 0.0))
        new_qty = pos.quantity + quantity
        new_invested = pos.avg_cost * pos.quantity + limit_price * quantity
        pos.quantity = new_qty
        pos.avg_cost = new_invested / new_qty if new_qty > 0 else 0
        pos.market_value = pos.quantity * limit_price
        self._positions[symbol] = pos

        return OrderResult(
            success=True,
            broker_order_id=oid,
            message="Mock buy filled",
            filled_quantity=quantity,
            filled_price=limit_price,
        )

    def submit_limit_sell(
        self, symbol: str, quantity: int, limit_price: float, client_order_id: str
    ) -> OrderResult:
        self._order_counter += 1
        oid = f"MOCK-S-{self._order_counter}"
        logger.info(
            f"[MOCK] SELL {symbol} qty={quantity} limit={limit_price:.2f} "
            f"coid={client_order_id}"
        )
        pos = self._positions.get(symbol)
        if pos:
            pos.quantity = max(0, pos.quantity - quantity)
            if pos.quantity == 0:
                del self._positions[symbol]

        return OrderResult(
            success=True,
            broker_order_id=oid,
            message="Mock sell filled",
            filled_quantity=quantity,
            filled_price=limit_price,
        )

    def cancel_order(self, broker_order_id: str) -> bool:
        logger.info(f"[MOCK] Cancel order {broker_order_id}")
        return True

    def get_order_status(self, broker_order_id: str) -> Optional[dict]:
        return {"status": "FILLED"}

    def get_positions(self) -> list[PositionInfo]:
        return list(self._positions.values())

    def is_connected(self) -> bool:
        return self._connected


class LiveDataBroker(MockBroker):
    """실시간 시세 + Mock 주문 (시뮬레이션용)

    yfinance로 실시간 가격을 가져오고, 주문 체결은 MockBroker를 재사용.
    캐시: 10초간 동일 심볼 재요청 방지.
    """

    def __init__(self):
        super().__init__()
        self._quote_cache: dict[str, tuple[Quote, float]] = {}
        self._cache_ttl = 10  # seconds
        self._lock = threading.Lock()
        self._sma_cache: dict[str, tuple[dict, float]] = {}
        self._sma_cache_ttl = 300  # 5분

    def get_quote(self, symbol: str) -> Optional[Quote]:
        now = time.time()

        with self._lock:
            if symbol in self._quote_cache:
                cached, ts = self._quote_cache[symbol]
                if now - ts < self._cache_ttl:
                    return cached

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            last = float(info.last_price)
            prev_close = float(info.previous_close)
            volume = int(info.last_volume) if info.last_volume else 0

            # yfinance doesn't provide bid/ask in fast_info reliably,
            # estimate from last price with typical ETF spread
            spread_bps = 3.0  # typical for QLD/TQQQ
            spread = last * spread_bps / 10000
            bid = last - spread / 2
            ask = last + spread / 2

            quote = Quote(
                symbol=symbol,
                bid=round(bid, 4),
                ask=round(ask, 4),
                mid=round(last, 4),
                last=round(last, 4),
                spread_bps=spread_bps,
                volume=volume,
                timestamp=datetime.utcnow(),
                prev_close=round(prev_close, 4),
            )

            with self._lock:
                self._quote_cache[symbol] = (quote, now)
                # MockBroker의 _prices도 업데이트 (주문 체결가 반영용)
                self._prices[symbol] = last

            return quote

        except Exception as e:
            logger.warning(f"[LIVE] yfinance 시세 조회 실패 ({symbol}): {e}, Mock fallback")
            return super().get_quote(symbol)

    def get_sma(self, symbol: str, period: int) -> Optional[float]:
        """SMA 계산 (yfinance 일봉 기반)"""
        cache_key = f"{symbol}_{period}"
        now = time.time()

        with self._lock:
            if cache_key in self._sma_cache:
                cached, ts = self._sma_cache[cache_key]
                if now - ts < self._sma_cache_ttl:
                    return cached.get("sma")

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{period + 10}d")
            if len(hist) < period:
                return None
            sma = float(hist["Close"].tail(period).mean())

            with self._lock:
                self._sma_cache[cache_key] = ({"sma": sma}, now)

            return round(sma, 4)
        except Exception as e:
            logger.warning(f"[LIVE] SMA 계산 실패 ({symbol}, {period}d): {e}")
            return None

    def get_sma_slope(self, symbol: str, period: int, lookback: int = 5) -> float:
        """SMA 기울기 (최근 lookback일간 SMA 변화율)"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{period + lookback + 10}d")
            if len(hist) < period + lookback:
                return 0.0
            closes = hist["Close"]
            sma_now = float(closes.tail(period).mean())
            sma_prev = float(closes.iloc[-(period + lookback):-lookback].mean())
            if sma_prev == 0:
                return 0.0
            return round((sma_now - sma_prev) / sma_prev, 6)
        except Exception:
            return 0.0

    def is_connected(self) -> bool:
        try:
            yf.Ticker("QQQ").fast_info.last_price
            return True
        except Exception:
            return False


def generate_client_order_id(
    strategy_id: str,
    cycle_id: int,
    symbol: str,
    action: str,
    step_no: int,
    decision_ts: datetime,
) -> str:
    """주문 idempotency key 생성 (규칙서 §12-2)

    client_order_id = hash(strategy_id, cycle_id, symbol, action, step_no, decision_ts)
    """
    raw = f"{strategy_id}:{cycle_id}:{symbol}:{action}:{step_no}:{decision_ts.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def calculate_buy_limit_price(snapshot: Quote) -> float:
    """매수 지정가 계산 (규칙서 §15)

    buy_limit_price = min(best_ask, decision_mid * (1 + buy_limit_offset_bps/10000))
    """
    settings = get_settings()
    offset = settings.execution.buy_limit_offset_bps / 10000
    calc_price = snapshot.mid * (1 + offset)
    return round(min(snapshot.ask, calc_price), 2)


def calculate_sell_limit_price(snapshot: Quote) -> float:
    """매도 지정가 계산 (규칙서 §15)

    sell_limit_price = max(best_bid, decision_mid * (1 - sell_limit_offset_bps/10000))
    """
    settings = get_settings()
    offset = settings.execution.sell_limit_offset_bps / 10000
    calc_price = snapshot.mid * (1 - offset)
    return round(max(snapshot.bid, calc_price), 2)


# 브로커 싱글톤
_broker: Optional[BrokerAPI] = None


def get_broker() -> BrokerAPI:
    global _broker
    if _broker is None:
        settings = get_settings()
        if settings.broker_type == "mock":
            _broker = MockBroker()
        elif settings.broker_type == "live":
            _broker = LiveDataBroker()
            logger.info("LiveDataBroker 활성화 (yfinance 실시간 시세)")
        elif settings.broker_type == "kiwoom":
            from services.kiwoom_broker import KiwoomBroker
            _broker = KiwoomBroker(
                account=settings.kiwoom_account,
                password=settings.kiwoom_password,
            )
            if not _broker.connect():
                logger.error("키움 연결 실패 — LiveDataBroker로 fallback (시세만 실시간)")
                _broker = LiveDataBroker()
            else:
                logger.info("KiwoomBroker 활성화 (실매매 모드)")
        else:
            _broker = MockBroker()
            logger.warning(f"브로커 '{settings.broker_type}' 미구현, Mock 사용")
    return _broker
