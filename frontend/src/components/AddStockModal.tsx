import { useState } from 'react';

interface AddStockModalProps {
  onSubmit: (data: { ticker: string; name: string; market: string; exchange: string }) => void;
  onClose: () => void;
}

export default function AddStockModal({ onSubmit, onClose }: AddStockModalProps) {
  const [ticker, setTicker] = useState('');
  const [name, setName] = useState('');
  const [market, setMarket] = useState('US');
  const [exchange, setExchange] = useState('NAS');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticker || !name) return;
    onSubmit({ ticker: ticker.toUpperCase(), name, market, exchange });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>종목 추가</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>티커</label>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="예: QLD"
              required
            />
          </div>
          <div className="form-group">
            <label>종목명</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: ProShares Ultra QQQ"
              required
            />
          </div>
          <div className="form-group">
            <label>시장</label>
            <select value={market} onChange={(e) => setMarket(e.target.value)}>
              <option value="US">미국</option>
            </select>
          </div>
          <div className="form-group">
            <label>거래소</label>
            <select value={exchange} onChange={(e) => setExchange(e.target.value)}>
              <option value="NAS">NASDAQ</option>
              <option value="NYSE">NYSE</option>
            </select>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn--ghost" onClick={onClose}>취소</button>
            <button type="submit" className="btn btn--primary">추가</button>
          </div>
        </form>
      </div>
    </div>
  );
}
