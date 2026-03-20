import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchOrders, fetchCompletedSummary, fetchEvents } from '../api/client';
import TradeTable from '../components/TradeTable';
import StatsCard from '../components/StatsCard';

type Tab = 'orders' | 'events';

export default function TradesPage() {
  const [tab, setTab] = useState<Tab>('orders');
  const [sideFilter, setSideFilter] = useState<'all' | 'BUY' | 'SELL'>('all');

  const { data: orders, isLoading: ordersLoading } = useQuery({
    queryKey: ['orders', sideFilter],
    queryFn: () => fetchOrders({
      side: sideFilter === 'all' ? undefined : sideFilter,
      limit: 100,
    }),
    enabled: tab === 'orders',
  });

  const { data: summary } = useQuery({
    queryKey: ['completedSummary'],
    queryFn: fetchCompletedSummary,
  });

  const { data: events, isLoading: eventsLoading } = useQuery({
    queryKey: ['events'],
    queryFn: () => fetchEvents({ limit: 100 }),
    enabled: tab === 'events',
    refetchInterval: 10_000,
  });

  return (
    <div className="page">
      <h2>주문 & 이벤트</h2>

      {summary && (
        <div className="stats-grid stats-grid--3">
          <StatsCard label="완료 사이클" value={summary.total_cycles} accent="blue" />
          <StatsCard
            label="누적 PnL"
            value={`$${summary.total_pnl.toLocaleString()}`}
            accent={summary.total_pnl >= 0 ? 'green' : 'red'}
          />
          <StatsCard label="평균 수익률" value={`${summary.avg_pnl_pct}%`} accent="green" />
        </div>
      )}

      <div className="filter-bar">
        <button
          className={`btn btn--tab ${tab === 'orders' ? 'btn--tab-active' : ''}`}
          onClick={() => setTab('orders')}
        >
          주문내역
        </button>
        <button
          className={`btn btn--tab ${tab === 'events' ? 'btn--tab-active' : ''}`}
          onClick={() => setTab('events')}
        >
          이벤트 로그
        </button>
      </div>

      {tab === 'orders' && (
        <>
          <div className="filter-bar">
            {(['all', 'BUY', 'SELL'] as const).map((f) => (
              <button
                key={f}
                className={`btn btn--tab ${sideFilter === f ? 'btn--tab-active' : ''}`}
                onClick={() => setSideFilter(f)}
              >
                {f === 'all' ? '전체' : f}
              </button>
            ))}
          </div>
          {ordersLoading ? (
            <p className="loading">불러오는 중...</p>
          ) : (
            <TradeTable orders={orders ?? []} />
          )}
        </>
      )}

      {tab === 'events' && (
        eventsLoading ? (
          <p className="loading">불러오는 중...</p>
        ) : (
          <div className="table-wrap">
            <table className="trade-table">
              <thead>
                <tr>
                  <th>시간</th>
                  <th>유형</th>
                  <th>레벨</th>
                  <th>메시지</th>
                </tr>
              </thead>
              <tbody>
                {(events ?? []).map((e) => (
                  <tr key={e.id}>
                    <td>{new Date(e.created_at).toLocaleString('ko-KR')}</td>
                    <td><span className="badge">{e.event_type}</span></td>
                    <td>
                      <span className={`badge badge--level-${e.level.toLowerCase()}`}>
                        {e.level}
                      </span>
                    </td>
                    <td className="trade-note">{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
