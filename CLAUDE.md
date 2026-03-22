# Infinite Buy - 라오어 무한매수법 자동매매 서비스

## 전략 문서

전략의 원본은 `docs/strategy.md`에 있다. 전략 관련 질문, 수정, 가이드 업데이트 시 반드시 이 파일을 먼저 읽을 것.

### 전략 변경 시 업데이트 순서

1. `docs/strategy.md` 수정 (전략 원본, 변경 이력 테이블 업데이트)
2. `backend/routers/market.py`의 해당 API 엔드포인트 반영 (`strategy-guide`, `manual-guide`, `tqqq-strategies`)
3. 백엔드 서버 재시작 후 API에서 JSON fetch
4. `guide.html` + `docs/index.html` 재생성 (Python 스크립트로 CSS + JSON 인라인)
5. `git commit` + `git push` (GitHub Pages 자동 배포)

## 프로젝트 구조

```
backend/          FastAPI + SQLAlchemy + APScheduler
  config.py       전체 설정 (Pydantic)
  main.py         앱 엔트리 (port 8001)
  routers/        API 라우터
    market.py     시장 데이터 + 전략 가이드 API
    dashboard.py  대시보드 + 실시간 시세 (yfinance)
    settings.py   종목/사이클 관리
    trades.py     주문/이벤트 조회
  services/
    broker_api.py   BrokerAPI 인터페이스 + MockBroker + LiveDataBroker
    kiwoom_broker.py 키움증권 브로커 (LOC 주문 포함, TODO: Windows에서 구현)
    strategy.py     의사결정 엔진
    risk_manager.py 리스크 관리
frontend/         Vite + React + TypeScript + TanStack Query
  src/pages/
    GuidePage.tsx 가이드 (3탭: 무한매수법 / TQQQ 적립식 / 수동 실전)
    MarketPage.tsx 시장 (3탭: 미장 Top10 / 국장 Top10 / 추천 종목)
docs/
  strategy.md     전략 원본 문서 (전략 변경 시 여기부터 수정)
  index.html      GitHub Pages용 standalone 가이드
guide.html        로컬 standalone 가이드 (docs/index.html과 동일)
```

## 실행

```bash
# 백엔드 (port 8001, BROKER_TYPE=live로 yfinance 실시간)
cd backend && ../.venv/bin/python -m uvicorn main:app --reload --port 8001

# 프론트엔드
cd frontend && npx vite
```

## 핵심 규칙

- 브로커 모드 (.env의 BROKER_TYPE):
  - `mock` → 하드코딩 가격, 즉시 체결
  - `live` → yfinance 실시간 시세, 주문은 Mock
  - `kiwoom` → 키움증권 실매매 (Windows 전용, KIWOOM_ACCOUNT/KIWOOM_PASSWORD 필요)
- LOC(종가지정가) 기반 전략. 실시간 매매가 아님.
- 매도 최소 +5% (수수료 벽). +1~2%는 수수료 떼면 무의미.
- GitHub Pages: https://jeeseongmin.github.io/infinite-buy/
- GitHub repo: https://github.com/jeeseongmin/infinite-buy
