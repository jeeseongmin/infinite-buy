import { useQuery } from '@tanstack/react-query';
import { fetchMarketOverview } from '../api/client';

export default function MarketTicker() {
  const { data, isLoading } = useQuery({
    queryKey: ['market-overview'],
    queryFn: fetchMarketOverview,
    refetchInterval: 15_000,
  });

  if (isLoading || !data) return null;

  return (
    <div className="market-ticker">
      <div className="market-ticker__badge">
        {data.is_live ? 'LIVE' : 'MOCK'}
      </div>
      {data.quotes.map((q) => (
        <div key={q.symbol} className="market-ticker__item">
          <span className="market-ticker__symbol">{q.symbol}</span>
          <span className="market-ticker__price">${q.last.toFixed(2)}</span>
          <span
            className={`market-ticker__change ${
              q.change_pct >= 0 ? 'market-ticker__change--up' : 'market-ticker__change--down'
            }`}
          >
            {q.change_pct >= 0 ? '+' : ''}{q.change_pct.toFixed(2)}%
          </span>
          <span className="market-ticker__volume">
            {q.volume >= 1_000_000
              ? `${(q.volume / 1_000_000).toFixed(1)}M`
              : `${(q.volume / 1_000).toFixed(0)}K`}
          </span>
        </div>
      ))}
    </div>
  );
}
