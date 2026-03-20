import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchStrategyGuide, fetchManualGuide, type StrategyGuide } from '../api/client';

type GuideTab = 'strategy' | 'manual';

// ===== 전략 이해 탭 컴포넌트들 =====

function AnalogyStory({ guide }: { guide: StrategyGuide }) {
  const { analogy } = guide;
  return (
    <div className="guide-card guide-card--highlight">
      <h3 className="guide-card__title">{analogy.title}</h3>
      <p className="guide-card__intro">{analogy.intro}</p>
      <div className="story-timeline">
        {analogy.story.map((scene, i) => (
          <div key={i} className="story-item">
            <div className="story-connector">
              <div className="story-dot">{i + 1}</div>
              {i < analogy.story.length - 1 && <div className="story-line" />}
            </div>
            <div className="story-content">
              <h4 className="story-scene">{scene.scene}</h4>
              <div className="story-analogy">{scene.analogy}</div>
              <div className="story-actual">{scene.actual}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="guide-insight">{analogy.key_insight}</div>
    </div>
  );
}

function WhyItWorks({ guide }: { guide: StrategyGuide }) {
  return (
    <div className="why-grid">
      {guide.why_it_works.map((w, i) => (
        <div key={i} className="why-card">
          <h4 className="why-title">{w.title}</h4>
          <div className="why-analogy">{w.analogy}</div>
          <div className="why-detail">{w.detail}</div>
        </div>
      ))}
    </div>
  );
}

function PhaseTimeline({ guide }: { guide: StrategyGuide }) {
  return (
    <div className="phase-timeline">
      {guide.phases.map((phase, i) => (
        <div key={phase.id} className="phase-item">
          <div className="phase-connector">
            <div className="phase-dot">{phase.id}</div>
            {i < guide.phases.length - 1 && <div className="phase-line" />}
          </div>
          <div className="phase-content">
            <h4 className="phase-name">{phase.name}</h4>
            <p className="phase-desc">{phase.description}</p>
            {phase.analogy && <div className="phase-analogy">{phase.analogy}</div>}
            <div className="phase-example">{phase.example}</div>
            {phase.key_param && <code className="phase-param">{phase.key_param}</code>}
          </div>
        </div>
      ))}
    </div>
  );
}

function SimulationChart({ guide }: { guide: StrategyGuide }) {
  const sim = guide.simulation_example;
  const maxInvested = Math.max(...sim.steps.map((s) => s.invested));
  return (
    <div>
      <div className="sim-info">
        {sim.symbol} / 예산 ${sim.budget.toLocaleString()} / {sim.tranches}트랜치 (1회 ${sim.per_tranche})
      </div>
      <div className="sim-chart">
        {sim.steps.map((step) => (
          <div key={step.step} className="sim-row">
            <div className="sim-step">Step {step.step}</div>
            <div className="sim-bar-area">
              <div
                className={`sim-bar ${step.action?.startsWith('SELL') ? 'sim-bar--sell' : step.qty > 0 ? 'sim-bar--buy' : 'sim-bar--hold'}`}
                style={{ width: `${(step.invested / maxInvested) * 100}%` }}
              />
            </div>
            <div className="sim-details">
              <span className="sim-price">${step.price.toFixed(2)}</span>
              {step.qty > 0 && <span className="sim-qty">+{step.qty}주</span>}
              <span className="sim-invested">${step.invested.toLocaleString()}</span>
              <span className="sim-avg">평단 ${step.avg_cost.toFixed(2)}</span>
              {step.action && (
                <span className={`sim-action ${step.action.startsWith('SELL') ? 'sim-action--sell' : ''}`}>
                  {step.action}
                </span>
              )}
              {step.pnl != null && <span className="sim-pnl">+${step.pnl.toFixed(2)}</span>}
            </div>
          </div>
        ))}
        <div className="sim-comments">
          {sim.steps.filter((s) => s.comment).map((step) => (
            <div key={step.step} className="sim-comment">
              <span className="sim-comment__step">Step {step.step}</span>
              <span className="sim-comment__text">{step.comment}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function RiskControls({ guide }: { guide: StrategyGuide }) {
  return (
    <div className="risk-grid">
      {guide.risk_controls.map((rc) => (
        <div key={rc.name} className="risk-item">
          <div className="risk-name">{rc.name}</div>
          <div className="risk-desc">{rc.description}</div>
          {rc.analogy && <div className="risk-analogy">{rc.analogy}</div>}
          <code className="risk-param">{rc.param}</code>
        </div>
      ))}
    </div>
  );
}

function FAQSection({ guide }: { guide: StrategyGuide }) {
  return (
    <div className="faq-list">
      {guide.faq.map((item, i) => (
        <details key={i} className="faq-item">
          <summary className="faq-question">{item.q}</summary>
          <div className="faq-answer">{item.a}</div>
        </details>
      ))}
    </div>
  );
}

function StrategyTab({ guide }: { guide: StrategyGuide }) {
  return (
    <>
      <div className="guide-hero">
        <h2>{guide.title}</h2>
        <p className="guide-subtitle">{guide.subtitle}</p>
        <p className="guide-summary">{guide.summary}</p>
      </div>
      <AnalogyStory guide={guide} />
      <h3 className="section-title">왜 이 전략이 작동하나요?</h3>
      <WhyItWorks guide={guide} />
      <h3 className="section-title">전략 5단계</h3>
      <PhaseTimeline guide={guide} />
      <h3 className="section-title">시뮬레이션 예시</h3>
      <SimulationChart guide={guide} />
      <h3 className="section-title">안전장치</h3>
      <RiskControls guide={guide} />
      <h3 className="section-title">자주 묻는 질문</h3>
      <FAQSection guide={guide} />
    </>
  );
}

// ===== 수동 실전 (키움) 탭 =====

/* eslint-disable @typescript-eslint/no-explicit-any */
function ManualTab({ data }: { data: any }) {
  return (
    <>
      <div className="guide-hero">
        <h2>{data.title}</h2>
        <p className="guide-subtitle">{data.subtitle}</p>
      </div>

      {/* 준비물 */}
      <h3 className="section-title">{data.prerequisites.title}</h3>
      <div className="prereq-list">
        {data.prerequisites.items.map((item: any, i: number) => (
          <div key={i} className="prereq-item">
            <div className="prereq-number">{i + 1}</div>
            <div className="prereq-content">
              <h4 className="prereq-name">{item.name}</h4>
              <p className="prereq-detail">{item.detail}</p>
              <div className="prereq-how">{item.how}</div>
            </div>
          </div>
        ))}
      </div>

      {/* 매일 밤 루틴 */}
      <h3 className="section-title">{data.daily_routine.title}</h3>
      <div className="routine-timezone">{data.daily_routine.timezone_note}</div>
      <div className="routine-timeline">
        {data.daily_routine.steps.map((step: any, i: number) => (
          <div key={i} className="routine-step">
            <div className="routine-connector">
              <div className="routine-time">{step.time}</div>
              {i < data.daily_routine.steps.length - 1 && <div className="routine-line" />}
            </div>
            <div className="routine-content">
              <div className="routine-header">
                <h4 className="routine-title">{step.title}</h4>
                <span className="routine-duration">{step.duration}</span>
              </div>
              <ul className="routine-actions">
                {step.actions.map((action: string, j: number) =>
                  action === '' ? (
                    <li key={j} className="routine-divider" />
                  ) : (
                    <li key={j} className={action.startsWith('■') ? 'routine-subheader' : ''}>
                      {action}
                    </li>
                  )
                )}
              </ul>
              {step.menu_path && (
                <div className="routine-menu">
                  <span className="routine-menu__label">메뉴 경로</span>
                  {step.menu_path}
                </div>
              )}
              {step.decision && (
                <div className="routine-decision">{step.decision}</div>
              )}
              {step.decision_tree && (
                <div className="decision-tree">
                  {step.decision_tree.map((d: any, j: number) => (
                    <div key={j} className={`decision-row decision-row--p${d.priority}`}>
                      <span className="decision-priority">{d.priority}</span>
                      <span className="decision-condition">{d.condition}</span>
                      <span className="decision-arrow">&rarr;</span>
                      <span className="decision-action">{d.action}</span>
                    </div>
                  ))}
                </div>
              )}
              {step.warning && (
                <div className="routine-warning">{step.warning}</div>
              )}
              {step.tip && (
                <div className="routine-tip">{step.tip}</div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 요일별 루틴 */}
      <h3 className="section-title">{data.weekly_schedule.title}</h3>
      <p className="section-desc">{data.weekly_schedule.note}</p>
      <div className="weekly-grid">
        {data.weekly_schedule.days.map((day: any, i: number) => (
          <div key={i} className={`weekly-card ${day.day.includes('토/일') ? 'weekly-card--rest' : ''}`}>
            <div className="weekly-day">{day.day}</div>
            <div className="weekly-focus">{day.focus}</div>
            {day.extra && <div className="weekly-extra">{day.extra}</div>}
          </div>
        ))}
      </div>

      {/* 키움 화면번호 */}
      <h3 className="section-title">{data.kiwoom_screens.title}</h3>
      <div className="table-wrap">
        <table className="trade-table">
          <thead>
            <tr>
              <th>화면번호</th>
              <th>화면명</th>
              <th>용도</th>
            </tr>
          </thead>
          <tbody>
            {data.kiwoom_screens.screens.map((s: any) => (
              <tr key={s.code}>
                <td><code className="screen-code">[{s.code}]</code></td>
                <td style={{ fontWeight: 600 }}>{s.name}</td>
                <td style={{ color: 'var(--text-dim)' }}>{s.use}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 엑셀 기록 */}
      <h3 className="section-title">{data.excel_template.title}</h3>
      <div className="table-wrap">
        <table className="trade-table">
          <thead>
            <tr>
              {data.excel_template.columns.map((col: string) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.excel_template.example_rows.map((row: string[], i: number) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} style={{
                    fontFamily: j >= 2 ? 'ui-monospace, monospace' : undefined,
                    color: cell === '매수' ? 'var(--accent)' : cell === '매도' ? 'var(--green)' : undefined,
                    fontWeight: cell === '매수' || cell === '매도' ? 600 : undefined,
                  }}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 흔한 실수 */}
      <h3 className="section-title">흔한 실수 & 해결법</h3>
      <div className="mistakes-list">
        {data.common_mistakes.map((m: any, i: number) => (
          <div key={i} className="mistake-item">
            <div className="mistake-header">
              <span className="mistake-x">X</span>
              <span className="mistake-text">{m.mistake}</span>
            </div>
            <div className="mistake-consequence">{m.consequence}</div>
            <div className="mistake-fix">
              <span className="mistake-check">O</span>
              {m.fix}
            </div>
          </div>
        ))}
      </div>

      {/* 매일 체크리스트 */}
      <h3 className="section-title">{data.checklist.title}</h3>
      <div className="checklist">
        {data.checklist.items.map((item: string, i: number) => (
          <label key={i} className="checklist-item">
            <input type="checkbox" />
            <span>{item}</span>
          </label>
        ))}
      </div>
    </>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// ===== 메인 =====

export default function GuidePage() {
  const [tab, setTab] = useState<GuideTab>('strategy');

  const { data: guide, isLoading: guideLoading } = useQuery({
    queryKey: ['strategy-guide'],
    queryFn: fetchStrategyGuide,
    enabled: tab === 'strategy',
  });

  const { data: manual, isLoading: manualLoading } = useQuery({
    queryKey: ['manual-guide'],
    queryFn: fetchManualGuide,
    enabled: tab === 'manual',
  });

  const tabs: { key: GuideTab; label: string }[] = [
    { key: 'strategy', label: '전략 이해하기' },
    { key: 'manual', label: '수동 실전 (키움증권)' },
  ];

  return (
    <div className="page guide-page">
      <div className="filter-bar" style={{ marginBottom: 24 }}>
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

      {tab === 'strategy' && (
        guideLoading
          ? <p className="loading">로딩 중...</p>
          : guide
            ? <StrategyTab guide={guide} />
            : <p className="empty-state">가이드를 불러올 수 없습니다</p>
      )}

      {tab === 'manual' && (
        manualLoading
          ? <p className="loading">로딩 중...</p>
          : manual
            ? <ManualTab data={manual} />
            : <p className="empty-state">가이드를 불러올 수 없습니다</p>
      )}
    </div>
  );
}
