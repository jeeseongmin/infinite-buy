import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  fetchUSTop,
  fetchKRTop,
  fetchRecommended,
  type MarketQuote,
  type RecommendedStock,
} from '../api/client';

type Tab = 'us' | 'kr' | 'infinite';

function formatVolume(v: number): string {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

function formatMarketCap(v: number): string {
  if (v >= 1_000_000_000_000) return `$${(v / 1_000_000_000_000).toFixed(1)}T`;
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

function formatKRW(v: number): string {
  if (v >= 1_000_000_000_000) return `${(v / 1_000_000_000_000).toFixed(1)}조`;
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(0)}억`;
  return v.toLocaleString();
}

function MarketTable({ quotes, isKR }: { quotes: MarketQuote[]; isKR: boolean }) {
  return (
    <div className="table-wrap">
      <table className="trade-table">
        <thead>
          <tr>
            <th>#</th>
            <th>종목</th>
            <th style={{ textAlign: 'right' }}>현재가</th>
            <th style={{ textAlign: 'right' }}>등락률</th>
            <th style={{ textAlign: 'right' }}>거래량</th>
            <th style={{ textAlign: 'right' }}>시가총액</th>
            <th style={{ textAlign: 'right' }}>고가</th>
            <th style={{ textAlign: 'right' }}>저가</th>
            <th>거래소</th>
          </tr>
        </thead>
        <tbody>
          {quotes.map((q, i) => (
            <tr key={q.symbol}>
              <td style={{ color: 'var(--text-dim)' }}>{i + 1}</td>
              <td>
                <div style={{ fontWeight: 700 }}>{q.symbol}</div>
                <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>{q.name}</div>
              </td>
              <td style={{ textAlign: 'right', fontFamily: 'ui-monospace, monospace', fontWeight: 600 }}>
                {isKR ? `₩${q.price.toLocaleString()}` : `$${q.price.toFixed(2)}`}
              </td>
              <td
                style={{
                  textAlign: 'right',
                  fontFamily: 'ui-monospace, monospace',
                  fontWeight: 600,
                  color: q.change_pct >= 0 ? 'var(--green)' : 'var(--red)',
                }}
              >
                {q.change_pct >= 0 ? '+' : ''}{q.change_pct.toFixed(2)}%
              </td>
              <td style={{ textAlign: 'right', fontFamily: 'ui-monospace, monospace' }}>
                {formatVolume(q.volume)}
              </td>
              <td style={{ textAlign: 'right', fontFamily: 'ui-monospace, monospace', fontSize: 13 }}>
                {isKR ? formatKRW(q.market_cap) : formatMarketCap(q.market_cap)}
              </td>
              <td style={{ textAlign: 'right', fontFamily: 'ui-monospace, monospace', fontSize: 13 }}>
                {isKR ? `₩${q.day_high.toLocaleString()}` : `$${q.day_high.toFixed(2)}`}
              </td>
              <td style={{ textAlign: 'right', fontFamily: 'ui-monospace, monospace', fontSize: 13 }}>
                {isKR ? `₩${q.day_low.toLocaleString()}` : `$${q.day_low.toFixed(2)}`}
              </td>
              <td style={{ fontSize: 12, color: 'var(--text-dim)' }}>{q.exchange}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecommendedCards({ stocks }: { stocks: RecommendedStock[] }) {
  return (
    <div className="recommended-grid">
      {stocks.map((s) => (
        <div key={s.symbol} className="recommended-card">
          <div className="recommended-header">
            <div>
              <span className="recommended-symbol">{s.symbol}</span>
              <span className={`recommended-risk recommended-risk--${s.risk === '매우 고' ? 'extreme' : s.risk === '고' ? 'high' : 'mid'}`}>
                {s.risk}위험
              </span>
            </div>
            <span className="recommended-leverage">{s.leverage}</span>
          </div>
          <div className="recommended-name">{s.name}</div>
          <div className="recommended-tracking">{s.tracking}</div>
          {s.price != null && (
            <div className="recommended-price-row">
              <span className="recommended-price">${s.price.toFixed(2)}</span>
              <span className={`recommended-change ${(s.change_pct ?? 0) >= 0 ? 'up' : 'down'}`}>
                {(s.change_pct ?? 0) >= 0 ? '+' : ''}{(s.change_pct ?? 0).toFixed(2)}%
              </span>
              {s.above_sma200 != null && (
                <span className={`recommended-sma ${s.above_sma200 ? 'above' : 'below'}`}>
                  SMA200 {s.above_sma200 ? '위' : '아래'}
                </span>
              )}
            </div>
          )}
          <div className="recommended-reason">{s.reason}</div>
        </div>
      ))}
    </div>
  );
}

export default function MarketPage() {
  const [tab, setTab] = useState<Tab>('us');

  const { data: usData, isLoading: usLoading } = useQuery({
    queryKey: ['market-us'],
    queryFn: () => fetchUSTop(10),
    refetchInterval: 60_000,
    enabled: tab === 'us',
  });

  const { data: krData, isLoading: krLoading } = useQuery({
    queryKey: ['market-kr'],
    queryFn: () => fetchKRTop(10),
    refetchInterval: 60_000,
    enabled: tab === 'kr',
  });

  const { data: recData } = useQuery({
    queryKey: ['recommended'],
    queryFn: fetchRecommended,
    enabled: tab === 'infinite',
  });

  const tabs: { key: Tab; label: string }[] = [
    { key: 'us', label: '미장 Top 10' },
    { key: 'kr', label: '국장 Top 10' },
    { key: 'infinite', label: '무한매수법' },
  ];

  return (
    <div className="page">
      <div className="page-header">
        <h2>시장</h2>
      </div>

      <div className="filter-bar">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`btn btn--tab ${tab === t.key ? 'btn--tab-active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'us' && (
        usLoading
          ? <p className="loading">미국 시장 데이터 로딩 중...</p>
          : usData?.quotes.length
            ? <MarketTable quotes={usData.quotes} isKR={false} />
            : <p className="empty-state">데이터를 불러올 수 없습니다</p>
      )}

      {tab === 'kr' && (
        krLoading
          ? <p className="loading">한국 시장 데이터 로딩 중...</p>
          : krData?.quotes.length
            ? <MarketTable quotes={krData.quotes} isKR={true} />
            : <p className="empty-state">데이터를 불러올 수 없습니다</p>
      )}

      {tab === 'infinite' && (
        <div>
          <h3 className="section-title">무한매수법 추천 종목</h3>
          {recData?.recommendations && (
            <RecommendedCards stocks={recData.recommendations} />
          )}
        </div>
      )}
    </div>
  );
}
