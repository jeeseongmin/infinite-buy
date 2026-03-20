import { Link } from 'react-router-dom';
import type { CycleSummary, CycleState } from '../api/client';

interface CycleCardProps {
  cycle: CycleSummary;
  onHalt?: (id: number) => void;
  onResume?: (id: number) => void;
  onResolve?: (id: number) => void;
}

const STATE_LABELS: Record<CycleState, string> = {
  BOOTSTRAP: '초기화',
  READY: '대기',
  BUY_PENDING: '매수 대기',
  HOLDING: '보유중',
  SELL_PENDING: '매도 대기',
  BUY_BLOCKED: '매수 차단',
  OBSERVE_ONLY: '관망',
  COOLDOWN: '쿨다운',
  MANUAL_REVIEW: '수동 확인',
  HALTED: '정지',
};

const STATE_ACCENTS: Record<string, string> = {
  READY: 'green',
  HOLDING: 'green',
  BUY_PENDING: 'blue',
  SELL_PENDING: 'blue',
  BUY_BLOCKED: 'yellow',
  OBSERVE_ONLY: 'yellow',
  COOLDOWN: 'dim',
  MANUAL_REVIEW: 'red',
  HALTED: 'red',
  BOOTSTRAP: 'dim',
};

export default function CycleCard({ cycle, onHalt, onResume, onResolve }: CycleCardProps) {
  const progress = cycle.tranche_count > 0
    ? Math.round((cycle.steps_used / cycle.tranche_count) * 100)
    : 0;

  const accent = STATE_ACCENTS[cycle.state] || 'dim';

  return (
    <div className="cycle-card">
      <div className="cycle-card-header">
        <Link to={`/symbol/${cycle.ticker}`} className="cycle-stock-code">
          {cycle.ticker}
        </Link>
        <span className="cycle-stock-name">{cycle.name}</span>
        <span className={`cycle-status cycle-status--${accent}`}>
          {STATE_LABELS[cycle.state]}
        </span>
      </div>

      <div className="cycle-card-body">
        {cycle.state_reason && (
          <p className="cycle-reason">{cycle.state_reason}</p>
        )}

        <div className="cycle-row">
          <span>예산</span>
          <strong>${cycle.cycle_budget.toLocaleString()}</strong>
        </div>
        <div className="cycle-row">
          <span>투자금</span>
          <strong>${cycle.total_invested.toLocaleString()}</strong>
        </div>
        {cycle.total_quantity > 0 && (
          <div className="cycle-row">
            <span>보유</span>
            <strong>{cycle.total_quantity}주 @ ${cycle.avg_cost.toFixed(2)}</strong>
          </div>
        )}
        <div className="cycle-row">
          <span>Step</span>
          <strong>{cycle.steps_used} / {cycle.tranche_count}</strong>
        </div>

        <div className="progress-bar">
          <div className="progress-fill" style={{ width: `${progress}%` }} />
        </div>

        <div className="cycle-row">
          <span>모드</span>
          <strong>{cycle.buy_mode}</strong>
        </div>
        <div className="cycle-row">
          <span>목표 익절</span>
          <strong>{cycle.take_profit_pct}%</strong>
        </div>
        <div className="cycle-row">
          <span>추가매수 트리거</span>
          <strong>-{cycle.add_trigger_pct}%</strong>
        </div>
        <div className="cycle-row">
          <span>일일 매수</span>
          <strong>{cycle.daily_buy_count}회</strong>
        </div>
      </div>

      <div className="cycle-card-footer">
        {cycle.state === 'HALTED' && onResume && (
          <button className="btn btn--primary btn--sm" onClick={() => onResume(cycle.id)}>
            재시작
          </button>
        )}
        {cycle.state === 'MANUAL_REVIEW' && onResolve && (
          <button className="btn btn--primary btn--sm" onClick={() => onResolve(cycle.id)}>
            해소
          </button>
        )}
        {!['HALTED', 'COOLDOWN'].includes(cycle.state) && onHalt && (
          <button className="btn btn--danger btn--sm" onClick={() => onHalt(cycle.id)}>
            정지
          </button>
        )}
      </div>
    </div>
  );
}
