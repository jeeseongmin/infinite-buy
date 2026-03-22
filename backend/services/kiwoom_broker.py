"""키움증권 해외주식 브로커 (영웅문 글로벌 OpenAPI)

Windows 전용. pykiwoom 또는 win32com 기반.
LOC(종가지정가) 주문 지원.

연동 시 필요:
  1. 키움증권 계좌 + 해외주식 거래 신청
  2. 영웅문 글로벌 OpenAPI 모듈 설치
  3. Windows 환경 (COM 기반)
  4. .env에 KIWOOM_ACCOUNT, KIWOOM_PASSWORD 설정

참고:
  - 키움 해외주식 주문 유형:
    00: 지정가
    01: 시장가
    05: LOC (Limit On Close, 종가지정가)
  - TR 코드:
    KOA_NORMAL_BUY_KW_ORD  (해외주식 매수)
    KOA_NORMAL_SELL_KW_ORD (해외주식 매도)
  - 화면번호: 자동 할당 또는 고정 (예: 9001~9010)
"""

import logging
from datetime import datetime
from typing import Optional

from services.broker_api import BrokerAPI, Quote, OrderResult, PositionInfo

logger = logging.getLogger(__name__)


# 키움 주문 유형 코드
class KiwoomOrderType:
    LIMIT = "00"       # 지정가
    MARKET = "01"      # 시장가 (사용 금지)
    LOC = "05"         # 종가지정가 (Limit On Close)


class KiwoomBroker(BrokerAPI):
    """키움증권 해외주식 브로커

    TODO: Windows 환경에서 아래 구현 완성
    - pykiwoom 또는 win32com.client로 키움 OpenAPI 연결
    - 로그인 → 계좌 조회 → 주문 → 체결 콜백
    """

    def __init__(self, account: str, password: str):
        self._account = account
        self._password = password
        self._connected = False
        self._kiwoom = None  # pykiwoom.Kiwoom() 인스턴스

        logger.info(f"[KIWOOM] 브로커 초기화 (계좌: {account[:4]}****)")

    # ===== 연결 =====

    def connect(self) -> bool:
        """키움 OpenAPI 로그인

        TODO:
            from pykiwoom.kiwoom import Kiwoom
            self._kiwoom = Kiwoom()
            self._kiwoom.CommConnect(block=True)
            self._connected = self._kiwoom.GetConnectState() == 1
        """
        logger.warning("[KIWOOM] connect() 미구현 - Windows 환경에서 구현 필요")
        return False

    def is_connected(self) -> bool:
        return self._connected

    # ===== 시세 =====

    def get_quote(self, symbol: str) -> Optional[Quote]:
        """해외주식 현재가 조회

        TODO:
            # TR: opt10001 (해외주식 현재가)
            self._kiwoom.SetInputValue("종목코드", symbol)
            self._kiwoom.CommRqData("해외주식현재가", "opt10001", 0, "8100")
            # 콜백에서 bid/ask/last/volume 파싱
        """
        logger.warning(f"[KIWOOM] get_quote({symbol}) 미구현")
        return None

    # ===== 일반 지정가 주문 =====

    def submit_limit_buy(
        self, symbol: str, quantity: int, limit_price: float, client_order_id: str
    ) -> OrderResult:
        """해외주식 지정가 매수

        TODO:
            self._kiwoom.SendOrder(
                "해외주식매수",  # 사용자 구분명
                "9001",          # 화면번호
                self._account,   # 계좌번호
                1,               # 주문유형 (1=매수)
                symbol,          # 종목코드
                quantity,         # 수량
                limit_price,     # 가격
                KiwoomOrderType.LIMIT,  # "00" 지정가
                ""               # 원주문번호 (신규는 빈 문자열)
            )
        """
        logger.warning(f"[KIWOOM] submit_limit_buy({symbol}, {quantity}, {limit_price}) 미구현")
        return OrderResult(success=False, broker_order_id="", message="키움 미구현")

    def submit_limit_sell(
        self, symbol: str, quantity: int, limit_price: float, client_order_id: str
    ) -> OrderResult:
        """해외주식 지정가 매도

        TODO:
            self._kiwoom.SendOrder(
                "해외주식매도", "9002", self._account,
                2,  # 주문유형 (2=매도)
                symbol, quantity, limit_price,
                KiwoomOrderType.LIMIT, ""
            )
        """
        logger.warning(f"[KIWOOM] submit_limit_sell({symbol}, {quantity}, {limit_price}) 미구현")
        return OrderResult(success=False, broker_order_id="", message="키움 미구현")

    # ===== LOC (종가지정가) 주문 =====

    def submit_loc_buy(
        self, symbol: str, quantity: int, limit_price: float, client_order_id: str
    ) -> OrderResult:
        """해외주식 LOC 매수: 종가가 limit_price 이하면 종가에 체결

        TODO:
            self._kiwoom.SendOrder(
                "LOC매수", "9003", self._account,
                1,  # 매수
                symbol, quantity, limit_price,
                KiwoomOrderType.LOC,  # "05" 종가지정가
                ""
            )
        """
        logger.warning(
            f"[KIWOOM] submit_loc_buy({symbol}, qty={quantity}, limit={limit_price}) 미구현"
        )
        return OrderResult(success=False, broker_order_id="", message="키움 LOC 매수 미구현")

    def submit_loc_sell(
        self, symbol: str, quantity: int, limit_price: float, client_order_id: str
    ) -> OrderResult:
        """해외주식 LOC 매도: 종가가 limit_price 이상이면 종가에 체결

        TODO:
            self._kiwoom.SendOrder(
                "LOC매도", "9004", self._account,
                2,  # 매도
                symbol, quantity, limit_price,
                KiwoomOrderType.LOC,  # "05" 종가지정가
                ""
            )
        """
        logger.warning(
            f"[KIWOOM] submit_loc_sell({symbol}, qty={quantity}, limit={limit_price}) 미구현"
        )
        return OrderResult(success=False, broker_order_id="", message="키움 LOC 매도 미구현")

    def supports_loc(self) -> bool:
        return True

    # ===== 주문 관리 =====

    def cancel_order(self, broker_order_id: str) -> bool:
        """주문 취소

        TODO:
            self._kiwoom.SendOrder(
                "주문취소", "9005", self._account,
                3,  # 주문유형 (3=취소)
                "", 0, 0, "", broker_order_id
            )
        """
        logger.warning(f"[KIWOOM] cancel_order({broker_order_id}) 미구현")
        return False

    def get_order_status(self, broker_order_id: str) -> Optional[dict]:
        """주문 상태 조회

        TODO:
            # TR: opt10076 (해외주식 미체결)
            # broker_order_id로 필터링
        """
        logger.warning(f"[KIWOOM] get_order_status({broker_order_id}) 미구현")
        return None

    # ===== 잔고 =====

    def get_positions(self) -> list[PositionInfo]:
        """해외주식 잔고 조회

        TODO:
            # TR: opw00015 (해외주식 잔고)
            self._kiwoom.SetInputValue("계좌번호", self._account)
            self._kiwoom.CommRqData("해외주식잔고", "opw00015", 0, "8700")
            # 콜백에서 종목별 수량, 평단, 평가금액 파싱
        """
        logger.warning("[KIWOOM] get_positions() 미구현")
        return []


# ===== LOC 일일 스케줄러 =====

def setup_daily_loc_orders(
    broker: KiwoomBroker,
    symbol: str,
    avg_cost: float,
    total_quantity: int,
    tranche_amount: float,
) -> list[OrderResult]:
    """매일 LOC 4건 세팅 (전략 핵심 루틴)

    매수 LOC 2건:
      1. 평단 이하에 1트랜치
      2. 평단 -5%에 트랜치 절반 (몸집 불리기)

    매도 LOC 2건:
      1. 평단 +5%에 보유 25%
      2. 평단 +10%에 보유 75%

    Args:
        broker: KiwoomBroker 인스턴스
        symbol: 종목코드 (예: "TQQQ")
        avg_cost: 현재 평균단가
        total_quantity: 현재 보유수량
        tranche_amount: 1트랜치 금액 (달러)

    Returns:
        OrderResult 리스트 (4건)
    """
    results = []
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")

    if avg_cost <= 0:
        logger.warning("[LOC] 평단이 0 이하, LOC 세팅 스킵")
        return results

    # --- 매수 LOC ---

    # 1. 평단 이하 매수
    buy_price_1 = round(avg_cost * 0.999, 2)  # 평단 바로 아래
    buy_qty_1 = max(1, int(tranche_amount / buy_price_1))
    r1 = broker.submit_loc_buy(symbol, buy_qty_1, buy_price_1, f"LOC-B1-{ts}")
    results.append(r1)
    logger.info(f"[LOC] 매수1: {symbol} {buy_qty_1}주 @ ${buy_price_1} (평단 이하)")

    # 2. 평단 -5% 매수 (몸집 불리기)
    buy_price_2 = round(avg_cost * 0.95, 2)
    buy_qty_2 = max(1, int(tranche_amount * 0.5 / buy_price_2))
    r2 = broker.submit_loc_buy(symbol, buy_qty_2, buy_price_2, f"LOC-B2-{ts}")
    results.append(r2)
    logger.info(f"[LOC] 매수2: {symbol} {buy_qty_2}주 @ ${buy_price_2} (몸집 불리기 -5%)")

    # --- 매도 LOC ---

    if total_quantity > 0:
        sell_qty_25 = max(1, int(total_quantity * 0.25))
        sell_qty_75 = total_quantity - sell_qty_25

        # 3. 평단 +5%에 25% 매도
        sell_price_1 = round(avg_cost * 1.05, 2)
        r3 = broker.submit_loc_sell(symbol, sell_qty_25, sell_price_1, f"LOC-S1-{ts}")
        results.append(r3)
        logger.info(f"[LOC] 매도1: {symbol} {sell_qty_25}주 @ ${sell_price_1} (+5%, 25%)")

        # 4. 평단 +10%에 75% 매도
        sell_price_2 = round(avg_cost * 1.10, 2)
        r4 = broker.submit_loc_sell(symbol, sell_qty_75, sell_price_2, f"LOC-S2-{ts}")
        results.append(r4)
        logger.info(f"[LOC] 매도2: {symbol} {sell_qty_75}주 @ ${sell_price_2} (+10%, 75%)")
    else:
        logger.info("[LOC] 보유수량 0 → 매도 LOC 생략")

    return results
