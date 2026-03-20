import type { OrderRecord } from '../api/client';

interface TradeTableProps {
  orders: OrderRecord[];
}

export default function TradeTable({ orders }: TradeTableProps) {
  if (orders.length === 0) {
    return <p className="empty-state">주문 내역이 없습니다</p>;
  }

  return (
    <div className="table-wrap">
      <table className="trade-table">
        <thead>
          <tr>
            <th>시간</th>
            <th>종목</th>
            <th>Side</th>
            <th>상태</th>
            <th>Step</th>
            <th>수량</th>
            <th>지정가</th>
            <th>체결</th>
            <th>금액</th>
            <th>사유</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td>{new Date(o.created_at).toLocaleString('ko-KR')}</td>
              <td><strong>{o.ticker}</strong></td>
              <td>
                <span className={`badge badge--${o.side === 'BUY' ? 'buy' : 'sell'}`}>
                  {o.side}
                </span>
              </td>
              <td>
                <span className={`badge badge--status-${o.status.toLowerCase()}`}>
                  {o.status}
                </span>
              </td>
              <td>{o.step_no ?? '-'}</td>
              <td>{o.filled_quantity}/{o.quantity}</td>
              <td>{o.limit_price ? `$${o.limit_price.toFixed(2)}` : '-'}</td>
              <td>{o.filled_avg_price > 0 ? `$${o.filled_avg_price.toFixed(2)}` : '-'}</td>
              <td>${o.filled_amount.toLocaleString()}</td>
              <td className="trade-note">{o.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
