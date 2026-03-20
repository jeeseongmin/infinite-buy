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
    """무한매수법 전략 시각화용 데이터 (실경험 기반)"""
    return {
        "title": "라오어 무한매수법",
        "subtitle": "매일 주문 걸고 자면 끝나는 자동 물타기 + 분할 익절 전략",
        "summary": "LOC(종가지정가) 주문으로 매일 매수/매도를 걸어놓고 자는 전략. 종가에서 조건이 맞으면 자동 체결.",
        "analogy": {
            "title": "자판기 비유로 이해하기",
            "intro": "무한매수법은 매일 밤 자판기에 동전을 넣어두는 것과 같습니다. 아침에 일어나면 결과가 나와 있어요.",
            "story": [
                {
                    "scene": "자판기 세팅",
                    "analogy": "투자 예산을 정합니다. 이 돈으로 매일 조금씩 자판기에 넣을 겁니다.",
                    "actual": "투자금 $10,000. 1회 매수 트랜치 금액 결정.",
                },
                {
                    "scene": "매일 밤 주문 걸기",
                    "analogy": "자기 전에 자판기 버튼 4개를 눌러놓습니다. '이 가격 이하면 사줘' 2개, '이 가격 이상이면 팔아줘' 2개.",
                    "actual": "LOC 매수 2건 + LOC 매도 2건을 매일 걸어놓고 취침",
                },
                {
                    "scene": "아침에 확인",
                    "analogy": "일어나서 자판기를 보면, 종가에 따라 어떤 건 체결되고 어떤 건 안 됐습니다. 내가 밤새 깨어있을 필요 없어요.",
                    "actual": "종가(Closing Price)에서 조건 충족 시 자동 체결. 미체결은 소멸.",
                },
                {
                    "scene": "떨어지면? 좋아!",
                    "analogy": "가격이 떨어지면 매수 LOC가 체결됩니다. 더 싸게 샀으니 평균 구매가가 내려갑니다.",
                    "actual": "평단 이하 LOC, 평단 -5% LOC 체결 → 몸집 불리기 + 평단 하락",
                },
                {
                    "scene": "올라가면? 팔자!",
                    "analogy": "가격이 올라가면 매도 LOC가 체결됩니다. 수수료를 충분히 커버하는 +5%, +10%에서만 팔기 때문에 확실한 수익.",
                    "actual": "보유 25%를 평단 +5%에, 75%를 +10%에 분할 매도",
                },
                {
                    "scene": "반복",
                    "analogy": "팔린 만큼 현금이 생기고, 다시 매수 주문을 걸 수 있습니다. 이걸 매일 반복하면 돈이 눈덩이처럼 불어납니다.",
                    "actual": "매도 → 현금 확보 → 새 사이클 or 추가 매수 여력 생김",
                },
            ],
            "key_insight": "핵심: '매일 매수 걸기, 매일 매도 걸기'가 전부입니다. 체결 여부는 그날 종가가 결정합니다. 내가 실시간으로 시세를 볼 필요가 없습니다.",
        },
        "why_it_works": [
            {
                "title": "왜 3배 레버리지 ETF인가?",
                "analogy": "3배 레버리지는 하루에 3~5%씩 위아래로 흔들립니다. 이 흔들림이 크기 때문에 매일 걸어둔 매수/매도 LOC가 체결될 확률이 높습니다. 잔잔한 호수에선 낚시가 안 되지만, 파도치는 바다에선 매일 잡힙니다.",
                "detail": "변동성이 클수록 LOC 체결 빈도 증가 → 사이클 회전 빠름 → 복리 효과 극대화.",
            },
            {
                "title": "왜 LOC(종가지정가)인가?",
                "analogy": "택배 보관함에 '이 가격이면 받겠다'고 써놓는 것과 같습니다. 밤새 안 깨고 자도 되고, 감정이 개입할 여지가 없습니다. 종가는 하루 중 가장 공정한 가격이기도 합니다.",
                "detail": "LOC = Limit On Close. 종가가 지정 가격 조건을 충족하면 종가에 체결, 아니면 소멸.",
            },
            {
                "title": "왜 +5%/+10%에 파나? (+1~2%는 안 되나요?)",
                "analogy": "택시를 타면 기본요금이 있습니다. 매수/매도할 때마다 수수료가 나가거든요. +1~2% 수익이면 수수료 떼고 남는 게 거의 없습니다. +5%, +10%는 수수료를 충분히 커버하고도 확실한 수익이 남는 구간입니다.",
                "detail": "해외주식 매매 수수료 + 환전 수수료 감안하면, 최소 +5% 이상에서 매도해야 실질 수익 발생.",
            },
        ],
        "phases": [
            {
                "id": 1,
                "name": "시드 투입 & 첫 매수",
                "icon": "seed",
                "description": "총 투자금(사이클 예산)을 정하고 첫 매수를 실행한다.",
                "analogy": "자판기에 처음 동전을 넣는 단계. 얼마를 넣을지, 몇 번에 나눠 넣을지 정합니다.",
                "example": "예산 $10,000. 첫 매수 QLD 7주 × $85 = $595",
            },
            {
                "id": 2,
                "name": "매일 LOC 매수 걸기",
                "icon": "buy",
                "description": "매일 2건의 매수 LOC를 걸어놓고 잔다. (1) 평단 이하에 일부, (2) 평단 -5%에 일부 (몸집 불리기).",
                "analogy": "'내일 사과가 950원 이하면 사줘' + '900원 이하면 더 사줘' 라고 자판기에 써놓는 것. 아침에 가격이 맞았으면 사져 있음.",
                "example": "평단 $85 → LOC1: $84.90 이하에 7주 / LOC2: $80.75(-5%)에 3주",
                "key_param": "LOC 매수: 평단 이하 + 평단 -5%",
            },
            {
                "id": 3,
                "name": "매일 LOC 매도 걸기",
                "icon": "profit",
                "description": "매일 2건의 매도 LOC를 걸어놓고 잔다. 보유 25%를 +5%에, 75%를 +10%에.",
                "analogy": "'사과가 1,050원 이상이면 25% 팔아줘, 1,100원 이상이면 나머지도 팔아줘' 라고 써놓는 것.",
                "example": "평단 $83 → LOC1: $87.15(+5%)에 25% / LOC2: $91.30(+10%)에 75%",
                "key_param": "LOC 매도: 25%@+5%, 75%@+10% (보수적)",
            },
            {
                "id": 4,
                "name": "자고 일어나서 확인",
                "icon": "check",
                "description": "체결 내역 확인. 체결된 건 기록하고, 새 평단 계산 후 다시 LOC 걸기.",
                "analogy": "아침에 자판기 열어보는 것. 사진 것도 있고, 팔린 것도 있고, 아무것도 안 된 날도 있음.",
                "example": "체결 확인 → 엑셀 업데이트 → 새 LOC 주문 세팅",
            },
            {
                "id": 5,
                "name": "반복 (매일)",
                "icon": "repeat",
                "description": "이걸 매일 반복합니다. 사이클이 끝나면(전량 매도) 새 사이클 시작.",
                "analogy": "매일 자판기에 주문 넣기 → 자기 → 확인. 이 루틴이 전부입니다.",
                "example": "평일 매일 5~10분 투자. 주문 걸고 자면 끝.",
            },
        ],
        "risk_controls": [
            {
                "name": "수수료 벽",
                "description": "+1~2% 매도는 수수료 빼면 남는 게 없음. 최소 +5% 이상에서 매도",
                "analogy": "택시 기본요금 안에서 내리면 손해. 충분히 가야 이득입니다.",
                "param": "최소 매도: +5% (수수료 감안)",
            },
            {
                "name": "몸집 불리기 (평단 -5% 매수)",
                "description": "평단 바로 아래만 매수하면 1~2회에서 멈춤. -5% LOC로 큰 하락에도 매수 유지",
                "analogy": "3배 레버리지는 하루 3~5% 왔다갔다함. 매수가 안 걸리면 고여있는 물이 됨.",
                "param": "LOC 매수2: 평단 -5%",
            },
            {
                "name": "레짐 필터",
                "description": "QQQ가 SMA200 아래면 하락장 → 신규매수 중단",
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
            "symbol": "TQQQ",
            "budget": 10000,
            "tranches": 16,
            "per_tranche": 625,
            "steps": [
                {"step": 1, "price": 55.00, "qty": 11, "invested": 605, "avg_cost": 55.00,
                 "comment": "첫 매수. TQQQ $55에 11주. 평단 $55."},
                {"step": 2, "price": 53.50, "qty": 12, "invested": 1247, "avg_cost": 54.22,
                 "comment": "종가 $53.50 → 평단 이하 LOC 체결. 12주 추가. 평단 $54.22로 하락."},
                {"step": 3, "price": 52.25, "qty": 6, "invested": 1561, "avg_cost": 53.83,
                 "comment": "종가 $52.25 → 평단 -5% LOC도 체결! 몸집 불리기 6주 추가."},
                {"step": 4, "price": 54.00, "qty": 0, "invested": 1561, "avg_cost": 53.83,
                 "action": "HOLD", "comment": "반등했지만 +5%($56.52)에 안 도달. 매도 LOC 미체결."},
                {"step": 5, "price": 51.80, "qty": 12, "invested": 2183, "avg_cost": 53.22,
                 "comment": "다시 하락. 평단 이하 LOC 체결. 평단이 $53.22로 더 내려감."},
                {"step": 6, "price": 55.88, "qty": 0, "invested": 2183, "avg_cost": 53.22,
                 "action": "SELL 25% (+5%)", "sell_price": 55.88, "pnl": 27.39,
                 "comment": "+5% LOC 체결! 보유 25%(10주)를 $55.88에 매도. $26.60 수익."},
                {"step": 7, "price": 58.54, "qty": 0, "invested": 1624, "avg_cost": 53.22,
                 "action": "SELL 75% (+10%)", "sell_price": 58.54, "pnl": 159.60,
                 "comment": "+10% LOC 체결! 나머지 75%(31주)를 $58.54에 매도. $164.92 수익! 사이클 완료."},
            ],
        },
        "faq": [
            {
                "q": "매일 깨어서 시세를 봐야 하나요?",
                "a": "아닙니다. LOC(종가지정가) 주문을 걸어놓고 자면 됩니다. 종가에서 조건이 맞으면 자동 체결, 안 맞으면 소멸. 하루 5~10분이면 충분합니다. 핵심은 '매일 매수 걸기, 매일 매도 걸기'이고, 체결 여부는 종가가 결정합니다.",
            },
            {
                "q": "왜 +1~2%가 아니라 +5%, +10%에 파나요?",
                "a": "매수/매도 수수료가 있습니다. 해외주식은 매매 수수료 + 환전 수수료가 나가므로, +1~2% 수익으로는 수수료 떼면 남는 게 거의 없습니다. +5%/+10%는 수수료를 충분히 커버하고도 확실한 수익이 남는 구간입니다.",
            },
            {
                "q": "평단 -5% 매수는 왜 하나요? (몸집 불리기)",
                "a": "3배 레버리지 ETF는 하루에 3~5% 움직이는 게 흔합니다. 평단 바로 아래에서만 매수하면 1~2회 매수 후 가격이 멀어져서 더 이상 매수가 안 걸립니다. 고여있는 물이 되는 거죠. -5% LOC를 같이 걸면 큰 하락에서도 매수가 체결되어 몸집(보유 수량)을 키울 수 있습니다.",
            },
            {
                "q": "왜 삼성전자가 아니라 QLD 같은 ETF인가요?",
                "a": "개별 주식은 실적 악화, 상장폐지 등 회사 고유의 위험이 있습니다. QLD 같은 지수 추종 ETF는 나스닥100 전체를 따라가므로, 한 회사가 망해도 다른 회사가 메꿔줍니다. 사과 한 종류만 사는 게 아니라 과일 바구니를 사는 것과 같습니다.",
            },
            {
                "q": "계속 떨어지기만 하면 어떡하나요?",
                "a": "트랜치를 다 쓰면 더 이상 매수하지 않고 기다립니다. 평단 대비 12% 이상 하락 시 손절이 발동됩니다. 끝없이 물타기를 하지 않습니다.",
            },
            {
                "q": "언제 시작하면 좋나요?",
                "a": "QQQ가 200일 이동평균선(SMA200) 위에 있으면 시장이 건강하다는 뜻이니 시작해도 좋습니다. 태풍 예보가 없을 때 배를 띄우는 것과 같습니다.",
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
            "title": "매일 밤 루틴 (월~금) - LOC 주문 걸고 자기",
            "timezone_note": "미국 정규장: 서머타임 23:30~06:00 / 동절기 00:30~07:00 (한국시간). LOC 주문은 장 마감 전 아무 때나 걸면 됨.",
            "core_concept": "핵심: 매일 LOC 매수 2건 + LOC 매도 2건을 걸어놓고 자면 됩니다. 종가에서 조건이 맞으면 체결, 안 맞으면 소멸. 내가 실시간으로 볼 필요 없습니다.",
            "steps": [
                {
                    "time": "자기 전 아무때나",
                    "title": "영웅문 로그인 & 잔고 확인",
                    "duration": "3분",
                    "actions": [
                        "영웅문 글로벌 (또는 영웅문S 글로벌) 로그인",
                        "[8700] 해외주식 잔고 → 보유수량, 평균단가 확인",
                        "엑셀에 오늘 날짜, 평단, 보유수량, 현재 트랜치 회차 기록",
                    ],
                    "menu_path": "영웅문 글로벌 → [8700] 해외주식 잔고현황",
                    "tip": "평단만 정확히 알면 됩니다. 현재가는 중요하지 않아요 — LOC가 알아서 판단합니다.",
                },
                {
                    "time": "자기 전",
                    "title": "LOC 매수 주문 2건 걸기",
                    "duration": "3분",
                    "actions": [
                        "[8200] 해외주식 주문 화면 열기",
                        "주문유형: 'LOC' (Limit On Close, 종가지정가) 선택",
                        "",
                        "■ 매수 LOC 1 - 평단 이하 매수:",
                        "  - 주문가격: 현재 평균단가 (또는 평단 바로 아래)",
                        "  - 주문수량: 1트랜치 분량",
                        "  - → 종가가 이 가격 이하면 체결, 아니면 소멸",
                        "",
                        "■ 매수 LOC 2 - 몸집 불리기:",
                        "  - 주문가격: 평균단가 × 0.95 (평단 -5%)",
                        "  - 주문수량: 트랜치의 절반 정도",
                        "  - → 큰 하락일에 체결되어 보유 수량을 키움",
                    ],
                    "menu_path": "영웅문 글로벌 → [8200] 해외주식 주문 → 주문유형: LOC",
                    "warning": "반드시 LOC(종가지정가)로 주문! 일반 지정가는 장중에 체결되어 의도와 다를 수 있음.",
                    "tip": "몸집 불리기가 없으면 1~2회 매수 후 가격이 멀어져서 고여버립니다. 3배 레버리지는 하루 3~5% 움직이니까요.",
                },
                {
                    "time": "자기 전",
                    "title": "LOC 매도 주문 2건 걸기",
                    "duration": "3분",
                    "actions": [
                        "같은 [8200] 화면에서 매도 주문",
                        "",
                        "■ 매도 LOC 1 - 1차 익절 (+5%):",
                        "  - 주문가격: 평균단가 × 1.05 (평단 +5%)",
                        "  - 주문수량: 보유수량의 25%",
                        "  - → 종가가 +5% 이상이면 25% 매도",
                        "",
                        "■ 매도 LOC 2 - 2차 익절 (+10%):",
                        "  - 주문가격: 평균단가 × 1.10 (평단 +10%)",
                        "  - 주문수량: 보유수량의 75% (나머지 전부)",
                        "  - → 종가가 +10% 이상이면 나머지 전량 매도",
                    ],
                    "menu_path": "영웅문 글로벌 → [8200] 해외주식 주문 → 매도 → LOC",
                    "warning": "+1~2%에 팔면 수수료 떼고 남는 게 없습니다! 최소 +5% 이상에서만 매도.",
                    "tip": "보수적 전략 기준. 공격적이면 비율/퍼센트를 조절할 수 있지만, 수수료 벽은 꼭 감안하세요.",
                },
                {
                    "time": "자기 전",
                    "title": "주문 확인 & 취침",
                    "duration": "1분",
                    "actions": [
                        "[8300] 해외주식 체결/미체결 화면에서 LOC 주문 4건 확인",
                        "매수 LOC 2건 + 매도 LOC 2건이 '접수' 상태인지 확인",
                        "확인되면 → 로그아웃 → 취침!",
                    ],
                    "menu_path": "영웅문 글로벌 → [8300] 해외주식 체결/미체결",
                    "tip": "총 소요시간 약 10분. 걸어놓고 자면 끝입니다.",
                },
                {
                    "time": "다음날 아침",
                    "title": "체결 결과 확인 & 기록",
                    "duration": "5분",
                    "actions": [
                        "영웅문 로그인 → [8300] 체결내역 확인",
                        "체결된 건: 엑셀에 기록 (매수/매도, 가격, 수량, 새 평단)",
                        "미체결 건: 자동 소멸되므로 신경 안 써도 됨",
                        "새 평균단가 계산 (매수 체결된 경우)",
                        "오늘 밤 LOC 가격 미리 계산해두기",
                    ],
                    "tip": "아침에 확인만 하면 됩니다. 매도가 체결됐으면 수익 실현, 매수가 체결됐으면 평단 하락. 둘 다 좋은 일입니다.",
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
                ["3/17", "TQQQ", "LOC매수", "$55.00", "11주", "$605", "$55.00", "1/16", "첫 매수"],
                ["3/18", "TQQQ", "LOC매수", "$53.50", "12주", "$1,247", "$54.22", "2/16", "평단이하 LOC 체결"],
                ["3/18", "TQQQ", "LOC매수", "$52.25", "6주", "$1,561", "$53.83", "3/16", "몸집불리기(-5%) LOC 체결"],
                ["3/19", "TQQQ", "-", "-", "-", "$1,561", "$53.83", "-", "LOC 미체결 (변동 적은 날)"],
                ["3/20", "TQQQ", "LOC매도", "$56.52", "7주", "$1,165", "$53.83", "-", "+5% LOC체결, 25% 매도"],
                ["3/24", "TQQQ", "LOC매도", "$59.21", "22주", "$0", "-", "완료", "+10% LOC체결, 나머지 매도"],
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
                "mistake": "LOC가 아닌 일반 지정가로 주문",
                "consequence": "장중에 체결되어 의도한 종가 매매가 아니게 됨. 변동성 높은 시간대에 불리한 가격 체결 가능.",
                "fix": "반드시 LOC(종가지정가)로 주문. 종가에서만 체결되므로 가장 공정한 가격.",
            },
            {
                "mistake": "+1~2%에서 매도 (수수료 무시)",
                "consequence": "매수/매도 수수료 + 환전 수수료 떼면 남는 게 거의 없거나 오히려 손해",
                "fix": "최소 +5% 이상에서 매도. 수수료를 충분히 커버하는 구간에서만 익절.",
            },
            {
                "mistake": "몸집 불리기(평단 -5% 매수) 안 걸기",
                "consequence": "1~2회 매수 후 가격이 멀어져서 LOC가 안 걸림. 포지션이 고여버림.",
                "fix": "매일 평단 -5% LOC를 반드시 걸어둘 것. 3x 레버리지는 하루 3~5% 흔들림.",
            },
            {
                "mistake": "감정적 판단 (더 떨어질 것 같아서 매수 안 걸음)",
                "consequence": "기계적으로 해야 할 LOC를 놓쳐서 평단이 안 내려감",
                "fix": "매일 LOC 4건 걸기가 전부. 체결 여부는 종가가 결정. 감정 개입 여지 없음.",
            },
            {
                "mistake": "변동성 잔잔한 종목 선택",
                "consequence": "LOC 매수/매도가 체결이 안 됨. 몇 주째 아무것도 안 되고 고여있음.",
                "fix": "변동성을 이용하는 전략이므로, 3배 레버리지 ETF(TQQQ, SOXL 등)처럼 하루 변동이 큰 종목 선택.",
            },
            {
                "mistake": "16회차 다 썼는데 계속 버티기",
                "consequence": "더 이상 매수가 안 되고 하락만 지켜봐야 함. 자금이 묶임.",
                "fix": "16회차 소진 + 매도 안 되면 일부 손절 → 약 12회차 수준으로 롤백 → 그 자금으로 다시 사이클. 매도되면 이익, 안 되면 손절 후 재매수. 이게 무한반복.",
            },
            {
                "mistake": "환전을 안 해두고 주문",
                "consequence": "달러 잔고 부족으로 주문 거부",
                "fix": "주말에 미리 다음 주 필요한 달러를 환전해두세요.",
            },
        ],
        "checklist": {
            "title": "매일 체크리스트 (5~10분)",
            "items": [
                "영웅문 글로벌 로그인",
                "[8300] 어제 LOC 체결 결과 확인 & 엑셀 기록",
                "[8700] 보유수량 & 평균단가 확인",
                "LOC 매수가 계산: (1) 평단 이하 (2) 평단 × 0.95",
                "LOC 매도가 계산: (1) 평단 × 1.05 (25%) (2) 평단 × 1.10 (75%)",
                "[8200] LOC 매수 2건 주문",
                "[8200] LOC 매도 2건 주문",
                "[8300] 4건 접수 확인",
                "로그아웃 & 취침",
            ],
        },
    }


@router.get("/tqqq-strategies")
def tqqq_strategies():
    """TQQQ 적립식 전략 가이드"""
    return {
        "title": "TQQQ 적립식 전략 가이드",
        "subtitle": "무한매수보다 적립식 변형이 더 많이 쓰입니다",
        "warning": {
            "title": "TQQQ는 장기 보유용이 아닙니다",
            "points": [
                "하루 기준 3배지, 장기적으로는 3배가 아님",
                "횡보하면 계속 깎임 (변동성 손실, Volatility Decay)",
                "'오래 들고 있으면 무조건 돈 번다' 구조가 아님",
            ],
            "conclusion": "그래서 '그냥 적립'이 아니라, 반드시 필터가 붙은 적립이어야 합니다.",
        },
        "strategies": [
            {
                "id": 1,
                "name": "정액 적립식 (DCA)",
                "tag": "기본",
                "risk_level": "위험",
                "description": "매주/매월 고정 금액을 투자. 가격 신경 안 씀.",
                "example": "매주 월요일 $500 TQQQ 매수",
                "pros": ["구현 매우 쉬움", "자동화 최적"],
                "cons": ["하락장에서 계좌 박살 가능", "TQQQ는 횡보 + 하락에 매우 약함"],
                "verdict": "그냥 쓰면 안 됨. 필터 없는 DCA는 레버리지 ETF에서 자살행위.",
            },
            {
                "id": 2,
                "name": "레짐 필터 적립식",
                "tag": "추천",
                "risk_level": "중간",
                "description": "조건이 좋을 때만 적립, 안 좋으면 현금 유지. 실전에서 가장 많이 쓰는 방식.",
                "example": "IF QQQ > 200일선: TQQQ 매수 (주 1회)\\nELSE: 매수 중단 (현금 보유)",
                "pros": ["하락장 회피", "심리적으로 편함", "구현 간단"],
                "cons": ["200일선 근처에서 왔다갔다하면 신호 잡음 발생"],
                "verdict": "핵심은 '언제 안 사느냐'가 전부. TQQQ는 상승장에선 미친 수익, 하락장에선 계좌 박살.",
                "key_insight": "TQQQ 적립의 핵심: '언제 사느냐'가 아니라 '언제 안 사느냐'",
            },
            {
                "id": 3,
                "name": "변동성 기반 적립식",
                "tag": "고급",
                "risk_level": "중간",
                "description": "변동성이 낮으면 매수, 높으면 중단. 횡보/불안정 구간을 회피.",
                "example": "IF VIX < 20: 매수\\nELSE: 대기",
                "pros": ["횡보/불안정 구간 회피", "자동매매에 잘 맞음"],
                "cons": ["VIX 데이터 필요", "임계값 최적화 필요"],
                "verdict": "레짐 필터와 조합하면 더 강력. VIX가 높으면 시장이 불안하다는 신호.",
            },
            {
                "id": 4,
                "name": "하락시 가중 적립식",
                "tag": "라오어 변형",
                "risk_level": "고위험",
                "description": "가격이 떨어질수록 더 많이 산다. 무한매수법과 가장 비슷한 형태.",
                "example": "기본: 1유닛\\n-5% 하락: 2유닛\\n-10% 하락: 3유닛",
                "pros": ["평균단가 빠르게 낮춤"],
                "cons": ["진짜 하락장 오면 끝없이 물림", "레버리지 ETF라 복구 어려움"],
                "verdict": "반드시 최대 단계 제한 + 손절/정지 조건 필요. 무한매수법의 16트랜치 제한이 바로 이것.",
            },
            {
                "id": 5,
                "name": "수익 재투자 적립식",
                "tag": "안전",
                "risk_level": "낮음",
                "description": "원금은 고정하고, 수익만 계속 재투자. 생각보다 많이 안 알려진 방식.",
                "example": "초기 1,000만원 투입\\n→ 수익 발생 시 그 수익으로만 TQQQ 추가 매수",
                "pros": ["원금 보호", "심리적으로 편함", "장기 복리 가능"],
                "cons": ["초기 수익 발생까지 느림", "수익금이 작으면 효과 미미"],
                "verdict": "보수적이지만 가장 심리적으로 편한 전략. 원금을 잃지 않는다는 안심감.",
            },
        ],
        "recommended_combo": {
            "title": "실전 추천 조합 (v1 전략)",
            "description": "레짐 필터 + 변동성 필터 + 리스크 관리를 조합한 실전용 전략",
            "rules": [
                {"condition": "QQQ > 200MA (레짐 ON)", "action": "주 1회 정액 적립", "icon": "buy"},
                {"condition": "QQQ < 200MA (레짐 OFF)", "action": "매수 중단, 현금 보유", "icon": "stop"},
                {"condition": "VIX > 30 (공포 구간)", "action": "매수 중단, 관망", "icon": "wait"},
                {"condition": "Max Drawdown -20%", "action": "전량 매도 (손절)", "icon": "exit"},
                {"condition": "포트폴리오 +30%", "action": "수익의 50% 현금화", "icon": "profit"},
            ],
            "note": "이 조합이면 단순 DCA 대비 drawdown 50% 이상 줄이면서 수익률은 유지 가능.",
        },
        "comparison_table": {
            "title": "전략별 비교",
            "columns": ["전략", "난이도", "위험도", "수익 잠재력", "자동화", "추천도"],
            "rows": [
                ["정액 적립 (DCA)", "쉬움", "높음", "높음", "매우 쉬움", "X (단독 사용 금지)"],
                ["레짐 필터 적립", "보통", "중간", "높음", "쉬움", "추천"],
                ["변동성 기반", "어려움", "중간", "중상", "보통", "고급자 추천"],
                ["하락시 가중", "보통", "높음", "매우 높음", "보통", "손절 필수 조건"],
                ["수익 재투자", "쉬움", "낮음", "중간", "쉬움", "보수적 추천"],
            ],
        },
        "conclusion": {
            "title": "TQQQ 적립식 3줄 요약",
            "points": [
                "그냥 적립 → 위험 (레버리지 + 횡보 = 계좌 박살)",
                "필터 붙은 적립 → 실전 (레짐 필터가 핵심)",
                "리스크 관리 포함 → 서비스 가능 (이게 Infinite Buy가 하는 일)",
            ],
        },
    }
