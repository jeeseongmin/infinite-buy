import { useState } from 'react';

interface StartCycleModalProps {
  ticker: string;
  onSubmit: (data: {
    ticker: string;
    cycle_budget: number;
    buy_mode: string;
    tranche_count: number;
    take_profit_pct: number;
    add_trigger_pct: number;
  }) => void;
  onClose: () => void;
}

export default function StartCycleModal({ ticker, onSubmit, onClose }: StartCycleModalProps) {
  const [budget, setBudget] = useState('');
  const [mode, setMode] = useState('PRICE_LADDER');
  const [tranches, setTranches] = useState(16);
  const [takeProfit, setTakeProfit] = useState(1.4);
  const [addTrigger, setAddTrigger] = useState(1.5);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!budget) return;
    onSubmit({
      ticker,
      cycle_budget: Number(budget),
      buy_mode: mode,
      tranche_count: tranches,
      take_profit_pct: takeProfit / 100,
      add_trigger_pct: addTrigger / 100,
    });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{ticker} 사이클 시작</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>사이클 예산 ($)</label>
            <input
              type="number"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              placeholder="5000"
              min="100"
              required
            />
          </div>
          <div className="form-group">
            <label>매수 모드</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="PRICE_LADDER">PRICE_LADDER (권장)</option>
              <option value="DAILY_TRANCHE">DAILY_TRANCHE</option>
            </select>
          </div>
          <div className="form-group">
            <label>Tranche 수</label>
            <input
              type="number"
              value={tranches}
              onChange={(e) => setTranches(Number(e.target.value))}
              min={4}
              max={50}
            />
            <small>총 예산을 몇 회로 분할할지 (기본 16)</small>
          </div>
          <div className="form-group">
            <label>익절 목표 (%)</label>
            <input
              type="number"
              value={takeProfit}
              onChange={(e) => setTakeProfit(Number(e.target.value))}
              step={0.1}
              min={0.1}
            />
            <small>평균단가 대비 목표 수익률 (기본 1.4%)</small>
          </div>
          <div className="form-group">
            <label>추가매수 트리거 (%)</label>
            <input
              type="number"
              value={addTrigger}
              onChange={(e) => setAddTrigger(Number(e.target.value))}
              step={0.1}
              min={0.1}
            />
            <small>마지막 체결가 대비 하락률 (기본 1.5%)</small>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn--ghost" onClick={onClose}>취소</button>
            <button type="submit" className="btn btn--primary">시작</button>
          </div>
        </form>
      </div>
    </div>
  );
}
