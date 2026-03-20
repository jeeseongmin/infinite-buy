"""시장 데이터 라우터 - 국장/미장 Top 10 + 무한매수 추천"""

import logging
import time
import threading
from typing import Optional

from fastapi import APIRouter

from yfinance.screener import screen, EquityQuery

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])

# 캐시 (API 호출 최소화)
_cache: dict[str, tuple[list, float]] = {}
_cache_lock = threading.Lock()
CACHE_TTL = 60  # 1분


def _get_cached(key: str) -> Optional[list]:
    with _cache_lock:
        if key in _cache:
            data, ts = _cache[key]
            if time.time() - ts < CACHE_TTL:
                return data
    return None


def _set_cache(key: str, data: list):
    with _cache_lock:
        _cache[key] = (data, time.time())


def _parse_quote(q: dict) -> dict:
    price = q.get("regularMarketPrice", 0)
    prev = q.get("regularMarketPreviousClose", 0)
    change_pct = round((price - prev) / prev * 100, 2) if prev else 0
    return {
        "symbol": q.get("symbol", ""),
        "name": q.get("shortName") or q.get("longName") or q.get("displayName", ""),
        "price": price,
        "prev_close": prev,
        "change_pct": change_pct,
        "volume": q.get("regularMarketVolume", 0),
        "market_cap": q.get("marketCap", 0),
        "day_high": q.get("regularMarketDayHigh", 0),
        "day_low": q.get("regularMarketDayLow", 0),
        "52w_high": q.get("fiftyTwoWeekHigh", 0),
        "52w_low": q.get("fiftyTwoWeekLow", 0),
        "avg_volume_3m": q.get("averageDailyVolume3Month", 0),
        "exchange": q.get("fullExchangeName", ""),
    }


@router.get("/us/top")
def us_top_actives(count: int = 10):
    """미장 거래량 Top N"""
    cached = _get_cached("us_top")
    if cached:
        return {"market": "US", "quotes": cached[:count]}

    try:
        result = screen("most_actives", count=count)
        quotes = [_parse_quote(q) for q in result.get("quotes", [])]
        _set_cache("us_top", quotes)
        return {"market": "US", "quotes": quotes}
    except Exception as e:
        logger.error(f"US screener 실패: {e}")
        return {"market": "US", "quotes": [], "error": str(e)}


@router.get("/kr/top")
def kr_top_actives(count: int = 10):
    """국장 거래량 Top N"""
    cached = _get_cached("kr_top")
    if cached:
        return {"market": "KR", "quotes": cached[:count]}

    try:
        q = EquityQuery("and", [
            EquityQuery("eq", ["region", "kr"]),
            EquityQuery("gt", ["dayvolume", 500000]),
        ])
        result = screen(q, count=count, sortField="dayvolume", sortAsc=False)
        quotes = [_parse_quote(q) for q in result.get("quotes", [])]
        _set_cache("kr_top", quotes)
        return {"market": "KR", "quotes": quotes}
    except Exception as e:
        logger.error(f"KR screener 실패: {e}")
        return {"market": "KR", "quotes": [], "error": str(e)}


# 무한매수법 추천 종목 기준:
# - 미국 레버리지 ETF (2x/3x)
# - 높은 유동성 (일평균 거래대금 1억달러+)
# - 좁은 스프레드
# - QQQ/SPY 추종 계열
RECOMMENDED_SYMBOLS = [
    {
        "symbol": "QLD",
        "name": "ProShares Ultra QQQ (2x)",
        "reason": "나스닥100 2배 레버리지. 무매 원형에 가장 적합. 적정 변동성, 높은 유동성.",
        "risk": "중",
        "leverage": "2x",
        "tracking": "QQQ (나스닥100)",
    },
    {
        "symbol": "TQQQ",
        "name": "ProShares UltraPro QQQ (3x)",
        "reason": "나스닥100 3배. QLD보다 공격적. 변동성 큼 → 트랜치 수 늘려야.",
        "risk": "고",
        "leverage": "3x",
        "tracking": "QQQ (나스닥100)",
    },
    {
        "symbol": "SSO",
        "name": "ProShares Ultra S&P500 (2x)",
        "reason": "S&P500 2배 레버리지. QLD보다 안정적. 보수적 무매 적합.",
        "risk": "중",
        "leverage": "2x",
        "tracking": "SPY (S&P500)",
    },
    {
        "symbol": "UPRO",
        "name": "ProShares UltraPro S&P500 (3x)",
        "reason": "S&P500 3배. SSO보다 공격적이나 나스닥 3x보다는 안정.",
        "risk": "고",
        "leverage": "3x",
        "tracking": "SPY (S&P500)",
    },
    {
        "symbol": "SOXL",
        "name": "Direxion Daily Semiconductor Bull 3x",
        "reason": "반도체 3배. 변동성 매우 높아 고위험-고수익. 숙련자용.",
        "risk": "매우 고",
        "leverage": "3x",
        "tracking": "SOXX (반도체)",
    },
]


@router.get("/recommended")
def recommended_for_infinite_buy():
    """무한매수법 추천 종목 + 실시간 시세"""
    from services.broker_api import get_broker, LiveDataBroker

    broker = get_broker()
    results = []

    for rec in RECOMMENDED_SYMBOLS:
        quote = broker.get_quote(rec["symbol"])
        entry = {**rec}
        if quote:
            entry["price"] = quote.last
            entry["prev_close"] = quote.prev_close
            entry["change_pct"] = round(
                (quote.last - quote.prev_close) / quote.prev_close * 100, 2
            ) if quote.prev_close else 0
            entry["volume"] = quote.volume
            entry["is_live"] = isinstance(broker, LiveDataBroker)

            # SMA 데이터
            if isinstance(broker, LiveDataBroker):
                sma20 = broker.get_sma(rec["symbol"], 20)
                sma200 = broker.get_sma(rec["symbol"], 200)
                if sma20:
                    entry["sma20"] = sma20
                if sma200:
                    entry["sma200"] = sma200
                    entry["above_sma200"] = quote.last > sma200
        results.append(entry)

    return {"recommendations": results}


@router.get("/strategy-guide")
def strategy_guide():
    """무한매수법 전략 시각화용 데이터 (비유 포함)"""
    return {
        "title": "라오어 무한매수법",
        "subtitle": "주가가 내려갈수록 유리해지는 마법의 쇼핑법",
        "summary": "분할매수로 평균단가를 낮추고, 목표 수익률 도달 시 전량 매도하는 전략",
        "analogy": {
            "title": "마트 세일 비유로 이해하기",
            "intro": "무한매수법은 마트에서 좋아하는 과일을 사는 것과 같습니다.",
            "story": [
                {
                    "scene": "장 보기 예산 짜기",
                    "analogy": "이번 달 사과 예산을 10만원으로 정하고, 16번에 나눠서 사기로 합니다. 한 번에 약 6,250원씩.",
                    "actual": "투자금 $10,000을 16트랜치로 나누어 1회 $625씩 투자",
                },
                {
                    "scene": "첫 번째 장보기",
                    "analogy": "사과 한 개에 1,000원. 6개를 삽니다. 내 평균 구매가: 1,000원.",
                    "actual": "QLD $85에 7주 매수. 평균단가 $85.00",
                },
                {
                    "scene": "사과가 세일!",
                    "analogy": "다음 주에 사과가 950원으로 떨어졌습니다. 좋아! 더 싸졌으니 또 삽니다. 평균 구매가가 975원으로 내려갑니다.",
                    "actual": "주가가 1.5% 하락 → 추가 매수 → 평균단가가 낮아짐",
                },
                {
                    "scene": "계속 세일이면?",
                    "analogy": "900원, 850원... 세일할 때마다 삽니다. 평균가는 계속 내려가서 900원이 됩니다.",
                    "actual": "하락할 때마다 트랜치 매수 → 평단이 계속 하락",
                },
                {
                    "scene": "가격이 반등!",
                    "analogy": "사과 가격이 다시 올라서 913원이 됐습니다. 평균 구매가 900원보다 1.4% 비싸졌으니 전부 팝니다!",
                    "actual": "현재가가 평단 + 1.4% 도달 → 전량 매도 → 수익 실현",
                },
                {
                    "scene": "정산",
                    "analogy": "싸게 많이 사서 조금만 올라도 이득. 10만원 투자해서 101,400원 회수. 치킨값 벌었습니다!",
                    "actual": "사이클 완료. 쿨다운 후 새 사이클 시작 가능.",
                },
            ],
            "key_insight": "핵심: 가격이 내려가면 '손해'가 아니라 '더 싸게 살 기회'입니다. 떨어질수록 평균단가가 낮아져서, 조금만 반등해도 수익이 됩니다.",
        },
        "why_it_works": [
            {
                "title": "왜 레버리지 ETF인가?",
                "analogy": "롤러코스터를 생각해보세요. 보통 주식이 미끄럼틀이면, 2x 레버리지는 롤러코스터입니다. 오르내림이 크니까 '싸게 사서 조금 올랐을 때 파는' 기회가 더 자주 옵니다.",
                "detail": "레버리지 ETF는 변동성이 커서 트랜치 매수/익절 사이클이 빠르게 돌아갑니다.",
            },
            {
                "title": "왜 분할매수인가?",
                "analogy": "계란을 한 바구니에 담지 않는 것과 같습니다. 10,000원을 한 번에 넣으면 떨어졌을 때 손해만 봅니다. 16번에 나눠서 사면, 떨어질 때마다 더 싸게 사서 평균가를 낮출 수 있습니다.",
                "detail": "DCA(Dollar Cost Averaging)의 변형. 시간 분산이 아닌 가격 분산.",
            },
            {
                "title": "왜 1.4%에 파나?",
                "analogy": "낚시를 생각하세요. 대어를 기다리면 하루종일 못 잡지만, 작은 물고기를 빠르게 여러 마리 잡으면 결국 더 많이 잡습니다. 작은 수익을 반복하는 게 핵심입니다.",
                "detail": "사이클 회전율이 높을수록 복리 효과. 연간 수십 회 사이클 가능.",
            },
        ],
        "phases": [
            {
                "id": 1,
                "name": "시드 투입",
                "icon": "seed",
                "description": "총 투자금(사이클 예산)을 정하고 N등분(트랜치)으로 나눈다.",
                "analogy": "이번 달 장보기 예산을 정하고, 몇 번에 나눠서 살지 정하는 단계",
                "example": "예산 $10,000 / 16트랜치 = 1회 매수 $625",
            },
            {
                "id": 2,
                "name": "첫 매수",
                "icon": "buy",
                "description": "첫 트랜치를 지정가로 매수하여 사이클 시작.",
                "analogy": "마트에서 사과를 처음 사는 것. 현재 가격 그대로 삽니다.",
                "example": "QLD $85.00 x 7주 = $595 투자",
            },
            {
                "id": 3,
                "name": "추가 매수 (물타기)",
                "icon": "add",
                "description": "평균단가 대비 일정% 하락 시 다음 트랜치 매수. 평단이 내려간다.",
                "analogy": "사과가 세일 중! 더 싸졌으니 또 삽니다. 살수록 평균 구매가가 내려갑니다.",
                "example": "1.5% 하락마다 추가매수 -> 평단 점차 하락",
                "key_param": "add_trigger_pct (기본 1.5%)",
            },
            {
                "id": 4,
                "name": "익절 (전량 매도)",
                "icon": "profit",
                "description": "현재가가 평균단가 + 목표수익률 도달 시 전량 매도.",
                "analogy": "사과 가격이 내 평균 구매가보다 조금이라도 오르면, 전부 팝니다!",
                "example": "평단 $82 -> 목표 $83.15 (+1.4%) 도달 시 매도",
                "key_param": "take_profit_pct (기본 1.4%)",
            },
            {
                "id": 5,
                "name": "사이클 완료",
                "icon": "complete",
                "description": "매도 완료 후 쿨다운. 새 사이클 시작 가능.",
                "analogy": "장보기 끝! 수익금 챙기고 다음 주에 다시 시작합니다.",
                "example": "투자금 $10,000 -> 회수 $10,140 (수익 $140)",
            },
        ],
        "risk_controls": [
            {
                "name": "스프레드 가드",
                "description": "호가 스프레드가 12bps 이상이면 매수 보류",
                "analogy": "마트에서 사과 매입가와 판매가 차이가 너무 크면 사지 않는 것",
                "param": "spread_guard_bps = 12",
            },
            {
                "name": "갭 가드",
                "description": "전일 종가 대비 2.2% 이상 갭이면 관망",
                "analogy": "어제 1,000원이던 사과가 오늘 갑자기 1,200원이면 일단 기다리는 것",
                "param": "gap_guard_pct = 2.2%",
            },
            {
                "name": "레짐 필터",
                "description": "QQQ가 SMA200 아래면 하락장 -> 신규매수 중단",
                "analogy": "태풍 예보가 뜨면 배를 항구에 묶어두는 것. 시장 전체가 위험하면 잠시 쉽니다.",
                "param": "regime_symbol = QQQ",
            },
            {
                "name": "손절 (하드 드로다운)",
                "description": "평단 대비 12% 이상 하락 시 전량 손절",
                "analogy": "사과가 썩기 시작하면 미련 없이 버리는 것. 작은 손해로 큰 손해를 막습니다.",
                "param": "hard_drawdown_pct = 12%",
            },
            {
                "name": "킬스위치",
                "description": "연속 주문 거부, 시세 지연, 포지션 불일치 시 자동 정지",
                "analogy": "차 계기판에 경고등이 켜지면 일단 멈추고 점검하는 것",
                "param": "max_consecutive_rejects = 3",
            },
        ],
        "simulation_example": {
            "symbol": "QLD",
            "budget": 10000,
            "tranches": 16,
            "per_tranche": 625,
            "steps": [
                {"step": 1, "price": 85.00, "qty": 7, "invested": 595, "avg_cost": 85.00,
                 "comment": "첫 매수. 사과 7개를 개당 $85에 삽니다."},
                {"step": 2, "price": 83.73, "qty": 7, "invested": 1181, "avg_cost": 84.36,
                 "comment": "1.5% 세일! 7개 더 삽니다. 평균가 $84.36으로 하락."},
                {"step": 3, "price": 82.47, "qty": 8, "invested": 1841, "avg_cost": 83.68,
                 "comment": "또 세일! 평균가가 $83.68로 더 내려갑니다."},
                {"step": 4, "price": 81.24, "qty": 8, "invested": 2491, "avg_cost": 83.03,
                 "comment": "계속 하락. 하지만 평단도 계속 낮아집니다."},
                {"step": 5, "price": 80.02, "qty": 8, "invested": 3131, "avg_cost": 82.39,
                 "comment": "5번째 매수 완료. 평단 $82.39."},
                {"step": 6, "price": 82.50, "qty": 0, "invested": 3131, "avg_cost": 82.39,
                 "action": "HOLD", "comment": "반등 중이지만 아직 목표(+1.4%)에 안 도달. 기다립니다."},
                {"step": 7, "price": 83.54, "qty": 0, "invested": 3131, "avg_cost": 82.39,
                 "action": "SELL (+1.4% 도달)", "sell_price": 83.54, "pnl": 43.70,
                 "comment": "목표 도달! 전량 매도. $43.70 수익 실현!"},
            ],
        },
        "faq": [
            {
                "q": "계속 떨어지기만 하면 어떡하나요?",
                "a": "16트랜치를 다 쓰면 더 이상 매수하지 않고 기다립니다. 12% 이상 떨어지면 손절(하드 드로다운)이 발동되어 손실을 제한합니다. 끝없이 물타기를 하지 않습니다.",
            },
            {
                "q": "1.4% 수익이면 너무 적지 않나요?",
                "a": "한 사이클만 보면 적지만, 이 사이클을 1년에 수십 번 반복합니다. 1.4% x 30회 = 42% 수익. 복리로 따지면 더 큽니다. 작은 물고기를 빠르게 많이 잡는 전략입니다.",
            },
            {
                "q": "왜 삼성전자가 아니라 QLD 같은 ETF인가요?",
                "a": "개별 주식은 실적 악화, 상장폐지 등 회사 고유의 위험이 있습니다. QLD 같은 지수 추종 ETF는 나스닥100 전체를 따라가므로, 한 회사가 망해도 다른 회사가 메꿔줍니다. 사과 한 종류만 사는 게 아니라 과일 바구니를 사는 것과 같습니다.",
            },
            {
                "q": "레버리지가 위험하지 않나요?",
                "a": "맞습니다. 레버리지 ETF는 변동성이 큽니다. 하지만 무한매수법은 바로 이 변동성을 이용하는 전략입니다. 롤러코스터가 무섭지만, 안전벨트(리스크 관리)를 매고 타면 스릴을 즐길 수 있는 것과 같습니다.",
            },
            {
                "q": "언제 시작하면 좋나요?",
                "a": "레짐 필터가 자동으로 판단합니다. QQQ가 200일 이동평균선 위에 있으면 시장이 건강하다는 뜻이니 시작해도 좋습니다. 태풍 예보가 없을 때 배를 띄우는 것과 같습니다.",
            },
        ],
    }


@router.get("/manual-guide")
def manual_guide():
    """키움증권 수동 무한매수법 상세 가이드"""
    return {
        "title": "키움증권으로 무한매수법 수동 실행하기",
        "subtitle": "미국 정규장 기준, 매일 밤 따라하는 루틴",
        "prerequisites": {
            "title": "시작 전 준비물",
            "items": [
                {
                    "name": "키움증권 계좌 개설",
                    "detail": "해외주식 거래가 가능한 종합매매 계좌. 비대면 개설 가능.",
                    "how": "키움증권 앱 → 계좌개설 → 비대면 계좌개설 → 신분증 촬영 → 영상통화 인증",
                },
                {
                    "name": "영웅문 글로벌 설치",
                    "detail": "해외주식 전용 HTS. PC에서만 가능 (모바일은 '영웅문S 글로벌').",
                    "how": "키움증권 홈페이지 → 트레이딩 → HTS → 영웅문 글로벌 다운로드",
                },
                {
                    "name": "해외주식 거래 신청",
                    "detail": "계좌 개설 후 별도로 해외주식 거래를 신청해야 합니다.",
                    "how": "영웅문 글로벌 → [8600] 해외주식 거래신청 또는 키움 앱에서 신청",
                },
                {
                    "name": "환전 (원화 → 달러)",
                    "detail": "해외주식은 달러로 거래. 미리 환전해두거나 자동환전 설정.",
                    "how": "영웅문 글로벌 → [8800] 해외주식 환전 → 원화 입금 후 USD 매수",
                },
                {
                    "name": "엑셀 또는 노트",
                    "detail": "매수 기록, 평균단가, 트랜치 진행 상황을 기록할 도구.",
                    "how": "구글 스프레드시트 추천. 종목, 매수가, 수량, 평단, 트랜치 번호 컬럼.",
                },
            ],
        },
        "daily_routine": {
            "title": "매일 밤 루틴 (월~금)",
            "timezone_note": "미국 정규장: 서머타임 23:30~06:00 / 동절기 00:30~07:00 (한국시간 기준)",
            "steps": [
                {
                    "time": "22:50 (서머타임) / 23:50 (동절기)",
                    "title": "기상 & 장 전 준비",
                    "duration": "10분",
                    "actions": [
                        "PC 켜고 영웅문 글로벌 로그인",
                        "보안카드 또는 OTP 준비",
                        "로그인: 영웅문 글로벌 실행 → ID/PW 입력 → 인증서 비밀번호",
                    ],
                    "tip": "잠이 안 깨면 알람을 2개 맞추세요. 하나는 22:45, 하나는 22:50.",
                },
                {
                    "time": "23:00",
                    "title": "시장 상황 체크 (레짐 필터)",
                    "duration": "5분",
                    "actions": [
                        "[8100] 해외주식 현재가 화면 열기",
                        "종목코드에 'QQQ' 입력 → 현재가 확인",
                        "차트 탭 → 일봉 → 이동평균선 200일(SMA200) 확인",
                        "QQQ 현재가가 SMA200 위인지 아래인지 확인",
                    ],
                    "decision": "QQQ가 SMA200 아래면 → 오늘은 쉽니다 (신규매수 안 함). 이미 보유 중이면 익절/손절 체크만.",
                    "menu_path": "영웅문 글로벌 → 화면번호 [8100] → 종목코드 QQQ → 차트",
                    "tip": "TradingView(tradingview.com)에서 QQQ 차트를 보는 게 더 편합니다. SMA 200을 추가하세요.",
                },
                {
                    "time": "23:20",
                    "title": "내 포지션 확인",
                    "duration": "5분",
                    "actions": [
                        "[8700] 해외주식 잔고 화면 열기",
                        "QLD (또는 내 종목) 보유수량, 평균단가 확인",
                        "현재가와 평균단가의 차이(%) 계산",
                        "엑셀/노트에 오늘 날짜, 현재가, 평단, 보유수량 기록",
                    ],
                    "menu_path": "영웅문 글로벌 → [8700] 해외주식 잔고현황",
                    "tip": "평단 대비 변동률 = (현재가 - 평단) / 평단 × 100",
                },
                {
                    "time": "23:25",
                    "title": "의사결정: 매도 / 홀드 / 매수",
                    "duration": "5분",
                    "actions": [
                        "[ 매도 체크 ] 현재가 ≥ 평균단가 × 1.014 (목표 +1.4%) → 전량 매도!",
                        "[ 손절 체크 ] 현재가 ≤ 평균단가 × 0.88 (하락 -12%) → 전량 손절!",
                        "[ 매수 체크 ] 현재가 ≤ 평균단가 × 0.985 (하락 -1.5%) → 추가 매수",
                        "[ 첫 매수 ] 보유 없고 레짐 OK → 첫 트랜치 매수",
                        "위 조건 모두 아니면 → 오늘은 홀드 (아무것도 안 함)",
                    ],
                    "decision_tree": [
                        {"condition": "현재가 ≥ 평단 × 1.014", "action": "전량 매도 (익절)", "priority": 1},
                        {"condition": "현재가 ≤ 평단 × 0.88", "action": "전량 매도 (손절)", "priority": 2},
                        {"condition": "현재가 ≤ 평단 × 0.985", "action": "추가 매수 (다음 트랜치)", "priority": 3},
                        {"condition": "보유 없음 & 레짐 OK", "action": "첫 트랜치 매수", "priority": 4},
                        {"condition": "위 모두 해당 없음", "action": "홀드 (대기)", "priority": 5},
                    ],
                    "tip": "매도 > 홀드 > 매수 순서로 판단합니다. 팔 수 있으면 무조건 파는 게 우선!",
                },
                {
                    "time": "23:30 (장 시작)",
                    "title": "주문 실행",
                    "duration": "5~10분",
                    "actions": [
                        "[8200] 해외주식 주문 화면 열기",
                        "종목코드: QLD (또는 내 종목) 입력",
                        "주문구분: '지정가' 선택 (시장가 절대 금지!)",
                        "",
                        "■ 매수인 경우:",
                        "  - 주문가격: 현재 매도호가(Ask) 입력",
                        "  - 주문수량: 1트랜치 금액 ÷ 주문가격 (소수점 버림)",
                        "  - 예) 트랜치 $625, 주가 $83 → 625÷83 = 7주",
                        "  - '매수' 버튼 클릭 → 비밀번호 입력 → 확인",
                        "",
                        "■ 매도인 경우:",
                        "  - 주문가격: 현재 매수호가(Bid) 입력",
                        "  - 주문수량: 전량 (잔고의 보유수량 전부)",
                        "  - '매도' 버튼 클릭 → 비밀번호 입력 → 확인",
                    ],
                    "menu_path": "영웅문 글로벌 → [8200] 해외주식 주문",
                    "warning": "반드시 '지정가'로 주문하세요. 시장가는 불리한 가격에 체결될 수 있습니다.",
                    "tip": "장 시작 직후 5분(23:30~23:35)은 변동성이 큽니다. 급하지 않으면 23:35 이후에 주문하세요.",
                },
                {
                    "time": "23:40",
                    "title": "체결 확인",
                    "duration": "5분",
                    "actions": [
                        "[8300] 해외주식 체결내역 화면 열기",
                        "방금 넣은 주문이 '체결' 상태인지 확인",
                        "'미체결'이면 1~2분 기다린 후 확인",
                        "5분 지나도 미체결이면 → 주문 취소 후 가격 수정해서 재주문",
                        "체결되었으면 → 엑셀에 기록 (날짜, 매수/매도, 가격, 수량, 새 평단)",
                    ],
                    "menu_path": "영웅문 글로벌 → [8300] 해외주식 체결/미체결",
                    "tip": "미체결 주문은 반드시 정리하세요. 다음 날까지 남겨두면 의도치 않게 체결될 수 있습니다.",
                },
                {
                    "time": "23:50",
                    "title": "기록 & 정리",
                    "duration": "5분",
                    "actions": [
                        "엑셀에 오늘 거래 기록 업데이트",
                        "새로운 평균단가 계산 (매수한 경우)",
                        "다음 매수 트리거 가격 계산: 새 평단 × 0.985",
                        "다음 익절 목표가 계산: 새 평단 × 1.014",
                        "미체결 주문 없는지 최종 확인",
                        "영웅문 글로벌 로그아웃 → 취침",
                    ],
                    "tip": "총 소요시간 약 30~40분. 체결이 빨리 되면 20분이면 끝납니다.",
                },
            ],
        },
        "weekly_schedule": {
            "title": "요일별 루틴",
            "note": "미국 증시는 월~금 개장. 한국시간으로는 화~토 새벽.",
            "days": [
                {
                    "day": "월요일 밤 (화요일 새벽)",
                    "focus": "주간 시작. 주말 동안 뉴스 체크. QQQ 레짐 재확인.",
                    "extra": "주말 사이 큰 이벤트(FOMC, 실적발표 등) 있었는지 확인",
                },
                {
                    "day": "화요일 밤",
                    "focus": "일반 루틴. 월요일 변동에 따른 트랜치 매수 여부 판단.",
                    "extra": "",
                },
                {
                    "day": "수요일 밤",
                    "focus": "일반 루틴. FOMC 등 연준 이벤트가 수요일에 많으므로 주의.",
                    "extra": "연준 발표일이면 변동성 클 수 있음 → 장 시작 후 30분 관망 추천",
                },
                {
                    "day": "목요일 밤",
                    "focus": "일반 루틴. 실업수당 청구건수 발표일 (매주 목).",
                    "extra": "",
                },
                {
                    "day": "금요일 밤 (토요일 새벽)",
                    "focus": "주간 마감. 미체결 주문 전부 정리. 주간 성과 정리.",
                    "extra": "주말에 거래 불가하므로, 포지션 점검 & 다음 주 계획 수립",
                },
                {
                    "day": "토/일",
                    "focus": "쉬는 날. 거래 없음.",
                    "extra": "엑셀 정리, 다음 주 경제지표 일정 확인 (investing.com 경제캘린더)",
                },
            ],
        },
        "excel_template": {
            "title": "엑셀 기록 예시",
            "columns": ["날짜", "종목", "매수/매도", "체결가", "수량", "투자금 누계", "평균단가", "트랜치 #", "메모"],
            "example_rows": [
                ["2026-03-17", "QLD", "매수", "$85.00", "7주", "$595", "$85.00", "1/16", "첫 매수"],
                ["2026-03-18", "QLD", "매수", "$83.73", "7주", "$1,181", "$84.36", "2/16", "1.5% 하락 추매"],
                ["2026-03-19", "QLD", "-", "-", "-", "$1,181", "$84.36", "-", "홀드 (조건 미충족)"],
                ["2026-03-20", "QLD", "매수", "$82.47", "8주", "$1,841", "$83.68", "3/16", "1.5% 하락 추매"],
                ["2026-03-24", "QLD", "매도", "$84.85", "22주", "$0", "-", "익절", "+1.4% 도달, +$25.74"],
            ],
        },
        "kiwoom_screens": {
            "title": "자주 쓰는 영웅문 글로벌 화면번호",
            "screens": [
                {"code": "8100", "name": "해외주식 현재가", "use": "종목 시세 확인, 차트 보기"},
                {"code": "8200", "name": "해외주식 주문", "use": "매수/매도 주문 넣기"},
                {"code": "8300", "name": "해외주식 체결/미체결", "use": "주문 체결 확인, 미체결 취소"},
                {"code": "8400", "name": "해외주식 주문가능금액", "use": "달러 잔고, 주문 가능 금액 확인"},
                {"code": "8600", "name": "해외주식 거래신청", "use": "최초 1회 해외주식 거래 신청"},
                {"code": "8700", "name": "해외주식 잔고현황", "use": "보유 종목, 평단, 평가손익 확인"},
                {"code": "8800", "name": "해외주식 환전", "use": "원화 → 달러 환전"},
            ],
        },
        "common_mistakes": [
            {
                "mistake": "시장가로 주문 넣기",
                "consequence": "특히 장 시작 직후 스프레드가 넓어서 비싼 가격에 체결됨",
                "fix": "항상 '지정가'로 주문. 매수는 Ask 가격, 매도는 Bid 가격 기준.",
            },
            {
                "mistake": "미체결 주문 방치",
                "consequence": "다음 날 의도치 않은 시점에 체결되어 계획이 틀어짐",
                "fix": "매일 [8300]에서 미체결 주문 확인. 장 마감 전 전부 정리.",
            },
            {
                "mistake": "감정적 판단 (더 떨어질 것 같아서 매수 안 함)",
                "consequence": "기계적으로 해야 할 추가매수를 놓쳐서 평단이 안 내려감",
                "fix": "조건이 맞으면 무조건 실행. 감정을 배제하는 게 이 전략의 핵심.",
            },
            {
                "mistake": "트랜치 금액을 무시하고 몰빵",
                "consequence": "초반에 예산을 다 써서 나중에 물타기 불가",
                "fix": "반드시 정해진 트랜치 금액만 투자. $625이면 $625만.",
            },
            {
                "mistake": "익절 목표를 욕심내서 올림 (1.4% → 3%)",
                "consequence": "사이클 회전이 느려지고, 하락장에서 익절 못 하고 물림",
                "fix": "1.4%를 지키세요. 작은 수익 × 높은 회전 = 큰 수익.",
            },
            {
                "mistake": "레짐 필터 무시 (하락장에서 신규 매수)",
                "consequence": "시장 전체가 하락하면 레버리지 ETF는 더 크게 하락",
                "fix": "QQQ가 SMA200 아래면 신규 사이클 시작 금지. 기존 보유분만 관리.",
            },
            {
                "mistake": "환전을 안 해두고 주문",
                "consequence": "달러 잔고 부족으로 주문 거부",
                "fix": "주말에 미리 다음 주 필요한 달러를 환전해두세요.",
            },
        ],
        "checklist": {
            "title": "매일 체크리스트",
            "items": [
                "영웅문 글로벌 로그인",
                "QQQ 현재가 & SMA200 확인 (레짐 필터)",
                "[8700] 내 잔고 & 평균단가 확인",
                "매도 조건 체크 (평단 +1.4%?)",
                "손절 조건 체크 (평단 -12%?)",
                "추가매수 조건 체크 (평단 -1.5%?)",
                "조건 맞으면 [8200]에서 지정가 주문",
                "[8300]에서 체결 확인",
                "미체결 주문 정리",
                "엑셀 기록 업데이트",
                "로그아웃 & 취침",
            ],
        },
    }
