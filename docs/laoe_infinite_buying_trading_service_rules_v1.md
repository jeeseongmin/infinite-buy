# 라오어 무한매수 자동매매 서비스 규칙서 v1.0

작성일: 2026-03-18  
문서 목적: 라오어식 무한매수 전략을 자동매매 서비스로 구현할 때 필요한 운영 규칙, 예외 처리, 리스크 통제 방식을 정리한 운영형 설계 문서

---

## 0. 문서의 기본 철학

라오어식 무한매수는 커뮤니티 변형이 많기 때문에, 이 문서는 “원문 재현”보다 **자동화 안정성**, **예외 처리**, **리스크 통제**를 우선으로 둔다.

핵심 원칙은 아래 다섯 가지다.

1. **무한은 금지**  
   모든 사이클은 최대 투입금과 최대 횟수가 있어야 한다.

2. **매수보다 매도 우선**  
   같은 시점에 매수·매도 조건이 동시에 성립하면 무조건 매도부터 처리한다.

3. **신호보다 체결 상태가 우선**  
   포지션·체결·미체결 상태가 불명확하면 신규 주문을 막는다.

4. **새 진입보다 생존 우선**  
   시장이 지저분할 때는 “안 사는 기능”이 전략 성능을 지킨다.

5. **원전 재현보다 서비스 안정성 우선**  
   라오어 원형을 그대로 고집하지 말고, 자동화에 맞게 상태와 예외를 쪼개서 관리한다.

---

## 1. v1 운영 전제

v1은 아래처럼 단순하게 시작하는 것을 권장한다.

- 대상 시장: 미국 주식 정규장만
- 방향: 롱 온리
- 대상 종목: 1종목만 운영
- 기본 종목: QLD
- 확장 종목: TQQQ는 feature flag
- 평가 주기: 1분봉 종가 기준 + 실시간 bid/ask snapshot
- 주문 방식: 지정가(limit) 우선
- 포지션 모델: 종목당 1사이클만 허용
- 오더 동시성: 같은 종목에 반대 방향 주문 동시 발사 금지
- 야간/프리마켓/애프터마켓: 금지

---

## 2. 종목 선정 규칙

### 2-1. 출시 순서

운영 순서는 아래처럼 권장한다.

- 백테스트/페이퍼: QQQ
- 실전 v1: QLD
- 실전 v2 이상: TQQQ
- 섹터형 3배 ETF: v3 이후

이유는 단순하다. TQQQ는 QLD보다 목표 레버리지가 높아 변동성과 괴리 리스크가 더 크므로, 예외 처리 실패 비용이 훨씬 높다.

### 2-2. 서비스 허용 조건

새 종목을 서비스에 추가하려면 아래 조건을 모두 만족하도록 설계한다.

- broad index 기반 ETF일 것
- 최근 30거래일 평균 거래대금이 충분할 것
- 최근 30거래일 중앙값 스프레드가 좁을 것
- 장중 체결 품질이 안정적일 것
- 섹터 집중형 3배 ETF는 v1에서 제외할 것

예시:

```yaml
symbol_admission:
  min_price: 20
  min_aum_usd: 500_000_000
  min_avg_dollar_volume_30d: 100_000_000
  max_median_spread_bps_30d: 12
  allow_sector_3x: false
  allow_inverse: false
```

---

## 3. 전략 모드 정의

### 3-1. DAILY_TRANCHE 모드

정해진 시간에 하루 1회 또는 하루 최대 N회, 고정된 tranche를 매수한다.

- 장점: 원형에 가깝고 이해가 쉽다.
- 단점: 급락일에 가격 정보 없이 기계적으로 사게 된다.

### 3-2. PRICE_LADDER 모드

현재 가격이 마지막 매수 체결가 대비 일정 비율 하락했을 때 다음 tranche를 매수한다.

- 장점: 자동매매에 더 적합하고 변동성 대응이 된다.
- 단점: 원형 그대로는 아니다.

**권장 기본값은 PRICE_LADDER**이다.

---

## 4. 핵심 변수 정의

```yaml
account_equity           # 계좌 총자산
cycle_budget_ratio       # 한 사이클에 쓸 자산 비율
cycle_budget             # account_equity * cycle_budget_ratio
tranche_count            # 분할 횟수
tranche_notional         # cycle_budget / tranche_count
steps_used               # 현재 사이클에서 사용한 tranche 수
avg_cost                 # 현재 평균단가
last_buy_fill_price      # 마지막 매수 체결가
take_profit_pct          # 평균단가 대비 목표 수익률
add_trigger_pct          # 추가매수 발동 하락률
soft_drawdown_pct        # 신규 매수 중단 기준
hard_drawdown_pct        # 강제 청산 기준
max_daily_buys           # 하루 최대 매수 횟수
cooldown_after_exit_min  # 청산 후 재진입 금지 시간
decision_interval_sec    # 신호 평가 주기
spread_guard_bps         # 스프레드 경계값
gap_guard_pct            # 갭 위험 경계값
vol_guard_15m_ann        # 단기 실현변동성 경계값
stale_quote_sec          # 시세 데이터 유효시간
order_ack_timeout_sec    # 주문 응답 제한시간
pos_mismatch_timeout_sec # 포지션 불일치 허용시간
```

---

## 5. 상태머신

```text
BOOTSTRAP
READY
BUY_PENDING
HOLDING
SELL_PENDING
BUY_BLOCKED
OBSERVE_ONLY
COOLDOWN
MANUAL_REVIEW
HALTED
```

### 상태 설명

- **BOOTSTRAP**: 장 시작 전 초기화, 브로커/데이터 상태 확인
- **READY**: 신규 진입 가능한 상태
- **BUY_PENDING**: 매수 주문 발사 후 체결 대기
- **HOLDING**: 포지션 보유 중
- **SELL_PENDING**: 매도 주문 발사 후 체결 대기
- **BUY_BLOCKED**: 신규 매수 금지, 매도만 허용
- **OBSERVE_ONLY**: 신규 주문 금지, 상태 감시만
- **COOLDOWN**: 청산 후 일정 시간 재진입 금지
- **MANUAL_REVIEW**: 포지션/체결 이상으로 사람 확인 필요
- **HALTED**: 전략 정지

### 핵심 전이

```text
BOOTSTRAP -> READY                : 장 시작 점검 통과
READY -> BUY_PENDING              : 진입 신호 + 모든 가드 통과
BUY_PENDING -> HOLDING            : 매수 체결 완료
HOLDING -> SELL_PENDING           : 익절/리스크청산 신호
SELL_PENDING -> COOLDOWN          : 전량 청산 완료
COOLDOWN -> READY                 : 쿨다운 종료
ANY -> BUY_BLOCKED               : 매크로/변동성/갭 위험
ANY -> OBSERVE_ONLY              : 시세 지연, 부분체결 불안정
ANY -> MANUAL_REVIEW             : 포지션 불일치
ANY -> HALTED                    : 중대 오류 또는 킬스위치
```

---

## 6. 의사결정 우선순위

같은 시점에 매수·매도 신호를 동시에 계산하더라도, 주문은 절대 동시에 보내지 않는다.

우선순위는 아래 순서로 고정한다.

1. 킬스위치 여부 확인
2. 브로커/시세/포지션 정상 여부 확인
3. 기존 미체결 주문 정리
4. 매도 신호 평가
5. 보류/관망 여부 평가
6. 매수 신호 평가

즉, 규칙은 한 줄이다.

> **sell > hold > buy**

### 같은 시점 충돌 처리

- 매도 조건과 매수 조건이 동시에 참이면: 매도
- 미체결 매도 주문이 있으면: 매수 금지
- 부분체결 상태면: 반대 주문 금지
- 포지션 수량이 브로커와 다르면: 매수·매도 모두 정지
- 직전 체결 후 안정화 시간이 지나지 않았으면: 반대 방향 주문 금지

---

## 7. 진입 규칙

진입은 “신호”보다 “게이트 통과”가 먼저다.

### 7-1. 진입 게이트

아래를 모두 만족해야 첫 매수를 허용한다.

```yaml
entry_gate:
  market_session_open: true
  no_open_orders: true
  no_position_mismatch: true
  not_in_cooldown: true
  regime_filter: ON or CAUTION
  not_in_blackout: true
  spread_ok: true
  gap_ok: true
  vol_ok: true
  quote_fresh: true
  broker_healthy: true
```

### 7-2. 첫 매수

flat 상태에서 진입 게이트를 통과하면 tranche 1을 매수한다.

권장 조건:

- 장 시작 직후 5분은 신규 매수 금지
- 장 마감 20분 전부터 신규 매수 금지
- 첫 매수는 시장가 금지, limit만 허용

---

## 8. 추가매수 규칙

### PRICE_LADDER 모드

```text
if current_mid <= last_buy_fill_price * (1 - add_trigger_pct):
    buy next tranche
```

단, 아래 조건을 모두 만족해야 한다.

- `steps_used < tranche_count`
- `daily_buy_count < max_daily_buys`
- `not in BUY_BLOCKED`
- `not in OBSERVE_ONLY`
- `soft_drawdown` 미초과
- 미체결 주문 없음
- 포지션 동기화 정상

### DAILY_TRANCHE 모드

```text
if now == scheduled_buy_time and trading_day_has_buy_slot:
    buy 1 tranche
```

### 급락 시 연속 매수 방지

```yaml
cascade_protection:
  max_new_tranches_per_bar: 1
  min_seconds_between_buys: 60
  max_daily_buys: 3
```

---

## 9. 매도 규칙

매도는 크게 3종류다.

### 9-1. 익절 청산

사이클 전체 손익이 목표치에 도달하면 전량 청산한다.

```text
cycle_pnl_pct >= take_profit_pct
```

권장 기준은 **평균단가 기준 + 수수료/슬리피지 반영 순손익**이다.

### 9-2. 소프트 리스크 청산

아직 강제청산은 아니지만 위험이 커졌을 때는 신규 매수를 막고, 반등 시 청산 우선으로 운용한다.

예:

- soft_drawdown 초과
- blackout 진입 임박
- regime OFF 전환
- intraday vol 급등

이 상태에선 `BUY_BLOCKED`로 전환한다.

### 9-3. 하드 리스크 청산

아래는 무조건 실행한다.

- hard_drawdown 초과
- 일일 손실 한도 초과
- 포지션이 최대 step 근처인데 시장 레짐 악화
- 브로커는 살아있지만 전략 손실 제한이 깨짐

이 경우는 전량 청산 후 `COOLDOWN` 또는 `HALTED`로 전이한다.

---

## 10. 보류/관망 규칙

### 10-1. BUY_BLOCKED

신규 매수만 막고, 매도는 허용한다.

이 상태로 보내는 조건:

- FOMC/CPI/NFP 같은 매크로 이벤트 블랙아웃 구간
- 장 초반/장 후반 제한 시간
- `soft_drawdown_pct` 초과
- `regime_filter == OFF`
- 갭이 너무 큰 날
- 단기 변동성이 임계치 초과
- 스프레드 확대

### 10-2. OBSERVE_ONLY

매수·매도 모두 즉시 실행하지 않고 감시만 한다.

이 상태로 보내는 조건:

- 시세 데이터가 stale
- 부분체결 후 잔량 처리 중
- 주문 응답이 늦음
- cancel/replace 중
- 마지막 체결 직후 평균단가 재산정 중

### 10-3. MANUAL_REVIEW

사람 확인이 필요하다.

- 내부 포지션 수량 ≠ 브로커 수량
- 체결 로그와 주문 상태가 어긋남
- 중복 주문 의심
- 주문 취소 여부 미확정
- 브로커 reconnect 후 포지션 재동기화 실패

---

## 11. 킬스위치 규칙

킬스위치는 “전략 손실”보다 “운영 실패”를 막기 위한 장치다.

### 즉시 HALTED

아래는 즉시 정지한다.

- 연속 주문 reject 3회 이상
- 브로커 연결 장애
- 시세 지연이 임계시간 초과
- 포지션 불일치가 `pos_mismatch_timeout_sec` 초과
- 동일 심볼 중복 주문 감지
- `client_order_id` 중복 발생
- 시스템 시계 오차가 임계치 초과
- 전략 프로세스 재시작 후 상태 복구 실패

### 즉시 청산 후 HALTED

아래는 위험 청산 후 정지한다.

- 일 손실 한도 초과
- hard_drawdown 초과
- 운영자가 수동 정지
- 시장 구조 이상으로 정상 체결 불가

예시:

```yaml
kill_switch:
  max_consecutive_rejects: 3
  stale_quote_sec: 2
  order_ack_timeout_sec: 5
  pos_mismatch_timeout_sec: 60
  daily_loss_limit_pct: 0.02
  duplicate_order_detected: true
```

---

## 12. 변수 차단 / 동시성 차단 규칙

### 12-1. 심볼 락

동일 심볼에 대해 동시에 두 워커가 주문 로직을 돌리지 못하게 한다.

```text
lock key = strategy_id + symbol
```

### 12-2. 주문 idempotency

모든 주문은 재전송되어도 중복 발사되지 않게 한다.

```text
client_order_id = hash(strategy_id, cycle_id, symbol, action, step_no, decision_ts)
```

### 12-3. 포지션 버전 체크

의사결정 시점의 포지션과 실제 제출 직전 포지션이 같아야 한다.

```text
if decision_snapshot.position_version != latest.position_version:
    abort and re-evaluate
```

### 12-4. 반대 주문 차단

다음 중 하나라도 참이면 반대 방향 주문 금지다.

- open order exists
- partial fill exists
- cancel pending
- replace pending
- avg_cost recalculation pending
- broker sync pending

### 12-5. 직후 안정화 시간

체결 직후 바로 반대 매매하는 걸 막는다.

```yaml
stabilization_window:
  after_buy_fill_sec: 5
  after_sell_fill_sec: 5
```

### 12-6. 스냅샷 유효성

신호 계산에 쓰는 데이터는 최신이어야 한다.

```text
if now - quote_timestamp > stale_quote_sec:
    do not trade
```

---

## 13. 레짐 필터

“요즘 같은 때도 써도 되나?”에 대한 운영형 해답은, **레짐이 켜졌을 때만 신규 사이클을 허용하는 것**이다.

### v1 권장 레짐 필터

기준 심볼은 `QQQ`로 둔다.

```text
REGIME_ON:
  QQQ_close_d1 > SMA200(QQQ)
  and SMA20(QQQ) slope >= 0

REGIME_CAUTION:
  위 둘 중 하나만 만족

REGIME_OFF:
  둘 다 불만족
```

### 레짐별 동작

- **ON**: 정상 운용
- **CAUTION**: `cycle_budget` 50% 축소, `max_daily_buys` 1로 감소
- **OFF**: 신규 매수 금지, 기존 포지션은 익절/리스크 청산만

---

## 14. v1 권장 기본값

아래는 **실전 전 종이매매/백테스트 시작값**이다.

### QLD v1 기본값

```yaml
strategy:
  symbol: QLD
  buy_mode: PRICE_LADDER
  cycle_budget_ratio: 0.08
  tranche_count: 16
  take_profit_pct: 0.014
  add_trigger_pct: 0.015
  soft_drawdown_pct: 0.06
  hard_drawdown_pct: 0.12
  max_daily_buys: 3
  cooldown_after_exit_min: 30

session:
  no_new_buy_first_min: 5
  no_new_buy_last_min: 20
  regular_session_only: true

risk:
  spread_guard_bps: 12
  gap_guard_pct: 0.022
  vol_guard_15m_ann: 0.65
  daily_loss_limit_pct: 0.02
  stale_quote_sec: 2
  order_ack_timeout_sec: 5
  pos_mismatch_timeout_sec: 60

execution:
  order_type: limit
  buy_limit_offset_bps: 4
  sell_limit_offset_bps: 4
  cancel_after_sec: 20
  max_replace_count: 2
```

### TQQQ v1 기본값

```yaml
strategy:
  symbol: TQQQ
  buy_mode: PRICE_LADDER
  cycle_budget_ratio: 0.05
  tranche_count: 20
  take_profit_pct: 0.022
  add_trigger_pct: 0.022
  soft_drawdown_pct: 0.09
  hard_drawdown_pct: 0.18
  max_daily_buys: 2
  cooldown_after_exit_min: 45

session:
  no_new_buy_first_min: 10
  no_new_buy_last_min: 30
  regular_session_only: true

risk:
  spread_guard_bps: 15
  gap_guard_pct: 0.035
  vol_guard_15m_ann: 0.90
  daily_loss_limit_pct: 0.015
  stale_quote_sec: 2
  order_ack_timeout_sec: 5
  pos_mismatch_timeout_sec: 45

execution:
  order_type: limit
  buy_limit_offset_bps: 5
  sell_limit_offset_bps: 5
  cancel_after_sec: 15
  max_replace_count: 2
```

---

## 15. 주문 실행 규칙

실행 품질이 전략 성과를 망친다.

### 기본 원칙

- 시장가 금지
- limit only
- buy는 ask 근처
- sell은 bid 근처
- timeout 후 cancel/replace
- replace 횟수 상한 존재
- 강제청산은 marketable limit 사용

### 예시

```text
buy_limit_price  = min(best_ask, decision_mid * (1 + buy_limit_offset_bps/10000))
sell_limit_price = max(best_bid, decision_mid * (1 - sell_limit_offset_bps/10000))
```

### 부분체결 처리

- 부분매수 체결 시: 잔량 취소 후 다음 bar에 재평가
- 부분매도 체결 시: 신규 매수 금지
- 부분체결 상태가 길어지면: `OBSERVE_ONLY`

---

## 16. 백테스트 체크리스트

이 전략은 백테스트 함정이 많다.

반드시 체크할 항목:

1. 신호봉 당일 체결 편향 금지
2. bid/ask 또는 슬리피지 반영
3. 정규장만 사용
4. 반대 주문 동시 체결 금지
5. 부분체결 가정 포함
6. 공휴일/반장 반영
7. event blackout historical calendar 반영
8. walk-forward 분리
9. 파라미터 overfit 검증
10. order reject / data lag / missed fill 스트레스 테스트

### 꼭 봐야 할 성과 지표

- 총수익률
- MDD
- time under water
- 평균 보유일
- 평균 step 사용 개수
- 최대 step 사용 개수
- 사이클당 손익 분포
- 일별 손익 tail
- 자본 사용률
- 주문 reject 비율
- 포지션 불일치 발생 횟수

---

## 17. 운영 배포 순서

### 1단계
백테스트

### 2단계
페이퍼 트레이딩 20거래일 이상

### 3단계
QLD 소액 실전

### 4단계
킬스위치/복구/재기동 시나리오 리허설

### 5단계
TQQQ feature flag 오픈

### 실전 오픈 조건

- 중복 주문 0건
- 포지션 불일치 자동복구 성공
- kill switch 테스트 통과
- slippage 허용 범위 내
- 20거래일 이상 로그 안정

---

## 18. 의사코드

```python
def evaluate(symbol, snapshot):
    if not system_healthy(snapshot):
        return halt(symbol)

    if position_mismatch(symbol):
        return manual_review(symbol)

    if has_open_order(symbol):
        return observe_only(symbol)

    mode = risk_mode(snapshot)   # NORMAL / BUY_BLOCKED / OBSERVE_ONLY / HALTED
    if mode == "HALTED":
        return halt(symbol)
    if mode == "OBSERVE_ONLY":
        return observe_only(symbol)

    pos = get_position(symbol)

    # 1) sell first
    if pos.qty > 0 and should_hard_exit(pos, snapshot):
        return submit_sell_all(symbol, reason="hard_exit")

    if pos.qty > 0 and should_take_profit(pos, snapshot):
        return submit_sell_all(symbol, reason="take_profit")

    # 2) buy blocked zone
    if mode == "BUY_BLOCKED":
        return hold(symbol)

    # 3) buy logic
    if pos.qty == 0:
        if entry_gate_ok(symbol, snapshot):
            return submit_buy_next_tranche(symbol, step_no=1)

    if pos.qty > 0:
        if can_add_tranche(symbol, snapshot, pos):
            return submit_buy_next_tranche(symbol, step_no=pos.steps_used + 1)

    return hold(symbol)
```

---

## 19. 한 줄 요약

> **QLD 1종목 + 정규장만 + PRICE_LADDER + sell 우선 + BUY_BLOCKED/OBSERVE_ONLY/HALTED 3중 방어 + 강한 idempotency/position sync**

이렇게 가면 “라오어 무한매수법”은 단순 무한매수 봇이 아니라, **통제 가능한 평균단가 회복 전략**이 된다.

---

## 20. 구현 메모

실제 구현 시 추천하는 기술 포인트:

- 주문 워커와 시그널 워커 분리
- Redis 분산락 사용
- `client_order_id` 강제 일관성 유지
- 포지션 스냅샷 버전 관리
- 체결 로그 영속화
- 전략 상태는 DB에 저장 후 재기동 복구 가능하게 설계
- 수동 정지 버튼 제공
- 운영자용 대시보드에서 현재 상태(`READY`, `BUY_BLOCKED`, `OBSERVE_ONLY`, `HALTED`)를 바로 보이도록 구성

