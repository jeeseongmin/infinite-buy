import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchSettings,
  updateSettings,
  fetchSymbols,
  toggleSymbol,
  type StrategySettings,
  type RegimeSettings,
} from '../api/client';

function pct(v: number): string {
  return (v * 100).toFixed(1);
}

function fromPct(s: string): number {
  return parseFloat(s) / 100;
}

export default function SettingsPage() {
  const queryClient = useQueryClient();

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  });

  const { data: symbols } = useQuery({
    queryKey: ['symbols'],
    queryFn: fetchSymbols,
  });

  const [strategy, setStrategy] = useState<StrategySettings | null>(null);
  const [regime, setRegime] = useState<RegimeSettings | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (settings) {
      setStrategy(settings.strategy);
      setRegime(settings.regime);
      setDirty(false);
    }
  }, [settings]);

  const saveMut = useMutation({
    mutationFn: () => updateSettings({
      strategy: strategy ?? undefined,
      regime: regime ?? undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setDirty(false);
    },
  });

  const toggleMut = useMutation({
    mutationFn: toggleSymbol,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['symbols'] }),
  });

  function updateStrategy<K extends keyof StrategySettings>(key: K, value: StrategySettings[K]) {
    if (!strategy) return;
    setStrategy({ ...strategy, [key]: value });
    setDirty(true);
  }

  function updateRegime<K extends keyof RegimeSettings>(key: K, value: RegimeSettings[K]) {
    if (!regime) return;
    setRegime({ ...regime, [key]: value });
    setDirty(true);
  }

  if (isLoading || !strategy || !regime) return <p className="loading">불러오는 중...</p>;

  const perTranche = strategy.tranche_count > 0
    ? (strategy.cycle_budget / strategy.tranche_count).toFixed(0)
    : '0';

  return (
    <div className="page">
      <div className="page-header">
        <h2>설정</h2>
        {dirty && (
          <button
            className="btn btn--primary"
            onClick={() => saveMut.mutate()}
            disabled={saveMut.isPending}
          >
            {saveMut.isPending ? '저장 중...' : '설정 저장'}
          </button>
        )}
      </div>

      {saveMut.isSuccess && (
        <div className="routine-tip" style={{ marginBottom: 16 }}>설정이 저장되었습니다.</div>
      )}

      {/* 종목 & 자금 */}
      <h3 className="section-title">종목 & 자금</h3>
      <div className="settings-grid">
        <div className="form-group">
          <label>매매 종목</label>
          <input
            type="text"
            value={strategy.symbol}
            onChange={(e) => updateStrategy('symbol', e.target.value.toUpperCase())}
          />
          <small>3배 레버리지 ETF 추천 (TQQQ, SOXL 등)</small>
        </div>
        <div className="form-group">
          <label>사이클 예산 ($)</label>
          <input
            type="number"
            value={strategy.cycle_budget}
            onChange={(e) => updateStrategy('cycle_budget', parseFloat(e.target.value) || 0)}
          />
          <small>이번 사이클에 투입할 총 금액</small>
        </div>
        <div className="form-group">
          <label>트랜치 횟수</label>
          <input
            type="number"
            value={strategy.tranche_count}
            min={4}
            max={40}
            onChange={(e) => updateStrategy('tranche_count', parseInt(e.target.value) || 16)}
          />
          <small>1회 매수 금액: ${perTranche}</small>
        </div>
      </div>

      {/* LOC 매수 설정 */}
      <h3 className="section-title">LOC 매수 설정</h3>
      <p className="section-desc">매일 2건의 LOC 매수를 걸어놓고 잡니다.</p>
      <div className="settings-grid">
        <div className="form-group">
          <label>매수 LOC 1: 평단 하락률 (%)</label>
          <input
            type="number"
            step="0.1"
            value={pct(strategy.loc_buy1_trigger)}
            onChange={(e) => updateStrategy('loc_buy1_trigger', fromPct(e.target.value))}
          />
          <small>평단 × (1 - {pct(strategy.loc_buy1_trigger)}%) 이하에서 매수. 기본 물타기.</small>
        </div>
        <div className="form-group">
          <label>매수 LOC 2: 평단 하락률 (%) - 몸집 불리기</label>
          <input
            type="number"
            step="0.5"
            value={pct(strategy.loc_buy2_trigger)}
            onChange={(e) => updateStrategy('loc_buy2_trigger', fromPct(e.target.value))}
          />
          <small>평단 × (1 - {pct(strategy.loc_buy2_trigger)}%) 이하에서 매수. 큰 하락 대비.</small>
        </div>
        <div className="form-group">
          <label>몸집 불리기 수량 비율 (%)</label>
          <input
            type="number"
            step="5"
            value={pct(strategy.loc_buy2_ratio)}
            onChange={(e) => updateStrategy('loc_buy2_ratio', fromPct(e.target.value))}
          />
          <small>트랜치의 {pct(strategy.loc_buy2_ratio)}%만큼 추가 매수</small>
        </div>
      </div>

      {/* LOC 매도 설정 */}
      <h3 className="section-title">LOC 매도 설정</h3>
      <p className="section-desc">매일 2건의 LOC 매도를 걸어놓고 잡니다. 수수료 감안 최소 +5%.</p>
      <div className="settings-grid">
        <div className="form-group">
          <label>매도 LOC 1: 목표 수익률 (%)</label>
          <input
            type="number"
            step="0.5"
            value={pct(strategy.loc_sell1_target)}
            onChange={(e) => updateStrategy('loc_sell1_target', fromPct(e.target.value))}
          />
          <small>평단 + {pct(strategy.loc_sell1_target)}%에서 1차 매도</small>
        </div>
        <div className="form-group">
          <label>1차 매도 수량 (%)</label>
          <input
            type="number"
            step="5"
            value={pct(strategy.loc_sell1_ratio)}
            onChange={(e) => updateStrategy('loc_sell1_ratio', fromPct(e.target.value))}
          />
          <small>보유의 {pct(strategy.loc_sell1_ratio)}% 매도</small>
        </div>
        <div className="form-group">
          <label>매도 LOC 2: 목표 수익률 (%)</label>
          <input
            type="number"
            step="0.5"
            value={pct(strategy.loc_sell2_target)}
            onChange={(e) => updateStrategy('loc_sell2_target', fromPct(e.target.value))}
          />
          <small>평단 + {pct(strategy.loc_sell2_target)}%에서 2차 매도</small>
        </div>
        <div className="form-group">
          <label>2차 매도 수량 (%)</label>
          <input
            type="number"
            step="5"
            value={pct(strategy.loc_sell2_ratio)}
            onChange={(e) => updateStrategy('loc_sell2_ratio', fromPct(e.target.value))}
          />
          <small>보유의 {pct(strategy.loc_sell2_ratio)}% 매도 (나머지 전부)</small>
        </div>
      </div>

      {/* 리스크 관리 */}
      <h3 className="section-title">리스크 관리</h3>
      <div className="settings-grid">
        <div className="form-group">
          <label>손절 기준 (%)</label>
          <input
            type="number"
            step="1"
            value={pct(strategy.hard_drawdown_pct)}
            onChange={(e) => updateStrategy('hard_drawdown_pct', fromPct(e.target.value))}
          />
          <small>평단 대비 -{pct(strategy.hard_drawdown_pct)}% 이상 하락 시 전량 손절</small>
        </div>
        <div className="form-group">
          <label>트랜치 소진 시 롤백</label>
          <select
            value={strategy.rollback_on_exhaust ? 'true' : 'false'}
            onChange={(e) => updateStrategy('rollback_on_exhaust', e.target.value === 'true')}
          >
            <option value="true">활성 (손절 후 재사이클)</option>
            <option value="false">비활성 (대기만)</option>
          </select>
          <small>16트랜치 소진 + 매도 안 되면 일부 손절 → {strategy.rollback_target_tranche}회차로 롤백</small>
        </div>
        <div className="form-group">
          <label>롤백 목표 트랜치</label>
          <input
            type="number"
            min={4}
            max={strategy.tranche_count - 1}
            value={strategy.rollback_target_tranche}
            onChange={(e) => updateStrategy('rollback_target_tranche', parseInt(e.target.value) || 12)}
          />
          <small>손절 후 돌아갈 트랜치 수준</small>
        </div>
      </div>

      {/* 레짐 필터 */}
      <h3 className="section-title">레짐 필터 (시장 건강 체크)</h3>
      <div className="settings-grid">
        <div className="form-group">
          <label>레짐 필터</label>
          <select
            value={regime.enabled ? 'true' : 'false'}
            onChange={(e) => updateRegime('enabled', e.target.value === 'true')}
          >
            <option value="true">활성</option>
            <option value="false">비활성 (항상 매수 허용)</option>
          </select>
          <small>비활성화하면 하락장에서도 매수합니다. 주의!</small>
        </div>
        <div className="form-group">
          <label>레짐 기준 종목</label>
          <input
            type="text"
            value={regime.symbol}
            onChange={(e) => updateRegime('symbol', e.target.value.toUpperCase())}
          />
          <small>이 종목이 SMA{regime.sma_period} 아래면 매수 중단</small>
        </div>
        <div className="form-group">
          <label>SMA 기간 (일)</label>
          <input
            type="number"
            value={regime.sma_period}
            onChange={(e) => updateRegime('sma_period', parseInt(e.target.value) || 200)}
          />
        </div>
        <div className="form-group">
          <label>VIX 필터</label>
          <select
            value={regime.vix_filter_enabled ? 'true' : 'false'}
            onChange={(e) => updateRegime('vix_filter_enabled', e.target.value === 'true')}
          >
            <option value="false">비활성</option>
            <option value="true">활성</option>
          </select>
          <small>VIX &gt; {regime.vix_max}이면 매수 중단 (공포 구간)</small>
        </div>
      </div>

      {/* 브로커 상태 */}
      <h3 className="section-title">브로커</h3>
      <div className="config-grid">
        <div className="config-card">
          <h4>현재 브로커</h4>
          <div className="config-items">
            <div className="config-item">
              <span className="config-key">broker_type</span>
              <span className="config-value">{settings?.broker_type}</span>
            </div>
            <div className="config-item">
              <span className="config-key">상태</span>
              <span className="config-value">
                {settings?.broker_type === 'kiwoom' ? '키움증권 (LOC 지원)' :
                 settings?.broker_type === 'live' ? 'yfinance (시세만)' : 'Mock (테스트)'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 등록 종목 */}
      <h3 className="section-title">등록 종목</h3>
      {!symbols || symbols.length === 0 ? (
        <p className="empty-state">등록된 종목이 없습니다.</p>
      ) : (
        <div className="table-wrap">
          <table className="trade-table">
            <thead>
              <tr>
                <th>티커</th>
                <th>종목명</th>
                <th>시장</th>
                <th>상태</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {symbols.map((s) => (
                <tr key={s.id}>
                  <td><strong>{s.ticker}</strong></td>
                  <td>{s.name}</td>
                  <td>{s.market}</td>
                  <td>
                    <span className={`badge badge--${s.is_enabled ? 'buy' : 'sell'}`}>
                      {s.is_enabled ? '활성' : '비활성'}
                    </span>
                  </td>
                  <td>
                    <button
                      className={`btn btn--sm ${s.is_enabled ? 'btn--danger' : 'btn--primary'}`}
                      onClick={() => toggleMut.mutate(s.id)}
                    >
                      {s.is_enabled ? '비활성화' : '활성화'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
