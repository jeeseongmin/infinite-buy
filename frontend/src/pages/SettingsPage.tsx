import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchSettings, fetchSymbols, toggleSymbol } from '../api/client';

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

  const toggleMut = useMutation({
    mutationFn: toggleSymbol,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['symbols'] }),
  });

  if (isLoading) return <p className="loading">불러오는 중...</p>;

  return (
    <div className="page">
      <h2>설정</h2>

      <div className="settings-section">
        <h3>전략 기본값</h3>
        <p className="section-desc">
          .env 또는 환경변수로 설정합니다. 사이클 시작 시 스냅샷됩니다.
        </p>
        {settings && (
          <div className="config-grid">
            <ConfigSection title="Strategy" data={settings.strategy} />
            <ConfigSection title="Session" data={settings.session} />
            <ConfigSection title="Risk" data={settings.risk} />
            <ConfigSection title="Execution" data={settings.execution} />
            <ConfigSection title="Cascade Protection" data={settings.cascade} />
            <ConfigSection title="Kill Switch" data={settings.kill_switch} />
          </div>
        )}
      </div>

      <div className="settings-section">
        <h3>등록 종목</h3>
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
                  <th>거래소</th>
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
                    <td>{s.exchange}</td>
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
    </div>
  );
}

function ConfigSection({ title, data }: { title: string; data: Record<string, unknown> }) {
  return (
    <div className="config-card">
      <h4>{title}</h4>
      <div className="config-items">
        {Object.entries(data).map(([key, value]) => (
          <div key={key} className="config-item">
            <span className="config-key">{key}</span>
            <span className="config-value">{String(value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
