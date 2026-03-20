import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchDashboard,
  fetchSymbols,
  addSymbol,
  startCycle,
  haltCycle,
  resumeCycle,
  resolveCycle,
} from '../api/client';
import StatsCard from '../components/StatsCard';
import CycleCard from '../components/CycleCard';
import MarketTicker from '../components/MarketTicker';
import AddStockModal from '../components/AddStockModal';
import StartCycleModal from '../components/StartCycleModal';

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const [showAddSymbol, setShowAddSymbol] = useState(false);
  const [startTicker, setStartTicker] = useState<string | null>(null);

  const { data: dashboard, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 10_000,
  });

  const { data: symbols } = useQuery({
    queryKey: ['symbols'],
    queryFn: fetchSymbols,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    queryClient.invalidateQueries({ queryKey: ['symbols'] });
  };

  const addSymbolMut = useMutation({
    mutationFn: addSymbol,
    onSuccess: () => { invalidate(); setShowAddSymbol(false); },
  });

  const startCycleMut = useMutation({
    mutationFn: startCycle,
    onSuccess: () => { invalidate(); setStartTicker(null); },
  });

  const haltMut = useMutation({ mutationFn: haltCycle, onSuccess: invalidate });
  const resumeMut = useMutation({ mutationFn: resumeCycle, onSuccess: invalidate });
  const resolveMut = useMutation({ mutationFn: resolveCycle, onSuccess: invalidate });

  if (isLoading) return <p className="loading">불러오는 중...</p>;
  if (!dashboard) return <p className="empty-state">데이터를 불러올 수 없습니다</p>;

  const activeTickers = new Set(dashboard.cycles.map((c) => c.ticker));
  const availableSymbols = symbols?.filter(
    (s) => s.is_enabled && !activeTickers.has(s.ticker)
  ) ?? [];

  return (
    <div className="page">
      <MarketTicker />

      <div className="page-header">
        <h2>대시보드</h2>
        <button className="btn btn--primary" onClick={() => setShowAddSymbol(true)}>
          + 종목 추가
        </button>
      </div>

      <div className="stats-grid">
        <StatsCard label="활성 사이클" value={dashboard.active_count} accent="blue" />
        <StatsCard label="완료" value={dashboard.completed_count} accent="green" />
        <StatsCard
          label="정지"
          value={dashboard.halted_count}
          accent={dashboard.halted_count > 0 ? 'red' : 'default'}
        />
        <StatsCard
          label="총 투자금"
          value={`$${dashboard.total_invested.toLocaleString()}`}
        />
        <StatsCard
          label="누적 PnL"
          value={`$${dashboard.total_pnl.toLocaleString()}`}
          sub={`평균 ${dashboard.avg_pnl_pct}%`}
          accent={dashboard.total_pnl >= 0 ? 'green' : 'red'}
        />
      </div>

      {availableSymbols.length > 0 && (
        <div className="start-cycle-bar">
          <span style={{ color: 'var(--text-dim)', fontSize: 14 }}>새 사이클:</span>
          {availableSymbols.map((s) => (
            <button
              key={s.id}
              className="btn btn--ghost btn--sm"
              onClick={() => setStartTicker(s.ticker)}
            >
              {s.ticker}
            </button>
          ))}
        </div>
      )}

      <h3 className="section-title">사이클</h3>
      {dashboard.cycles.length === 0 ? (
        <p className="empty-state">
          진행중인 사이클이 없습니다. 종목을 추가하고 사이클을 시작하세요.
        </p>
      ) : (
        <div className="cycle-grid">
          {dashboard.cycles.map((c) => (
            <CycleCard
              key={c.id}
              cycle={c}
              onHalt={(id) => { if (confirm('사이클을 정지하시겠습니까?')) haltMut.mutate(id); }}
              onResume={(id) => resumeMut.mutate(id)}
              onResolve={(id) => resolveMut.mutate(id)}
            />
          ))}
        </div>
      )}

      {showAddSymbol && (
        <AddStockModal
          onSubmit={(data) => addSymbolMut.mutate(data)}
          onClose={() => setShowAddSymbol(false)}
        />
      )}

      {startTicker && (
        <StartCycleModal
          ticker={startTicker}
          onSubmit={(data) => startCycleMut.mutate(data)}
          onClose={() => setStartTicker(null)}
        />
      )}
    </div>
  );
}
