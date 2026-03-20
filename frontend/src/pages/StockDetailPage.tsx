import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchSymbolDetail, fetchOrders } from '../api/client';
import CycleCard from '../components/CycleCard';
import TradeTable from '../components/TradeTable';

export default function StockDetailPage() {
  const { ticker } = useParams<{ ticker: string }>();

  const { data: detail, isLoading } = useQuery({
    queryKey: ['symbolDetail', ticker],
    queryFn: () => fetchSymbolDetail(ticker!),
    enabled: !!ticker,
  });

  const { data: orders } = useQuery({
    queryKey: ['orders', ticker],
    queryFn: () => fetchOrders({ ticker, limit: 50 }),
    enabled: !!ticker,
  });

  if (isLoading) return <p className="loading">불러오는 중...</p>;
  if (!detail || 'error' in detail) return <p className="empty-state">종목을 찾을 수 없습니다</p>;

  const { symbol, cycles } = detail;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h2>{symbol.ticker}</h2>
          <p className="section-desc">{symbol.name} | {symbol.market} / {symbol.exchange}</p>
        </div>
        <span className={`badge badge--${symbol.is_enabled ? 'buy' : 'sell'}`}>
          {symbol.is_enabled ? '활성' : '비활성'}
        </span>
      </div>

      <h3 className="section-title">사이클 히스토리</h3>
      {cycles.length === 0 ? (
        <p className="empty-state">사이클 내역이 없습니다</p>
      ) : (
        <div className="cycle-grid">
          {cycles.map((c) => (
            <CycleCard key={c.id} cycle={c} />
          ))}
        </div>
      )}

      <h3 className="section-title">주문 내역</h3>
      <TradeTable orders={orders ?? []} />
    </div>
  );
}
