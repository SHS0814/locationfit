import { Fragment } from 'react'
import type {
  AgentAssumption,
  FounderContext,
  RelaxationOption,
  StrategyScenario,
  TradeoffInsight,
} from '../../types/api'

interface Props {
  context: FounderContext
  assumptions: AgentAssumption[]
  explorationSummary: Record<string, unknown>
  scenarios: StrategyScenario[]
  tradeoffs: TradeoffInsight[]
  relaxationOptions: RelaxationOption[]
  selectedScenarioId: 'condition_fit' | 'growth' | 'stability' | null
  loading: boolean
  onSelectScenario: (id: 'condition_fit' | 'growth' | 'stability') => void
  onApplyRelaxation: (option: RelaxationOption) => void
  onAssumptionStatus: (id: string, status: AgentAssumption['status']) => void
}

export function AgentAnalysisPanels({
  context, assumptions, explorationSummary, scenarios, tradeoffs, relaxationOptions,
  selectedScenarioId, loading, onSelectScenario, onApplyRelaxation, onAssumptionStatus,
}: Props) {
  return (
    <Fragment>
      {(context.business_description || context.target_customer || context.operating_pattern || assumptions.length > 0) && (
        <section className="context-card" aria-label="창업 맥락과 가정">
          <div className="section-title"><span>창업 맥락</span><small>질문 {context.discovery_question_count}/4</small></div>
          <dl>
            {context.business_description && <><dt>사업</dt><dd>{context.business_description}</dd></>}
            {context.target_customer && <><dt>고객</dt><dd>{context.target_customer}</dd></>}
            {context.operating_pattern && <><dt>운영</dt><dd>{context.operating_pattern}</dd></>}
            {context.location_flexibility && <><dt>지역</dt><dd>{formatContextValue(context.location_flexibility)}</dd></>}
            {context.risk_tolerance && <><dt>위험 선호</dt><dd>{formatContextValue(context.risk_tolerance)}</dd></>}
          </dl>
          {assumptions.length > 0 && (
            <div className="assumption-list">
              <strong>확인할 가정</strong>
              {assumptions.filter((item) => item.status !== 'rejected').map((item) => (
                <div key={item.id} className="assumption-row">
                  <p>{item.status === 'confirmed' ? '확인됨' : '가정'} · {item.text}</p>
                  {item.status === 'inferred' && <span>
                    <button type="button" onClick={() => onAssumptionStatus(item.id, 'confirmed')}>맞아요</button>
                    <button type="button" onClick={() => onAssumptionStatus(item.id, 'rejected')}>수정할게요</button>
                  </span>}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {scenarios.length > 0 && (
        <section className="scenario-section" aria-label="전략 시나리오 비교">
          <div className="section-title">
            <span>전략 가설</span>
            <small>후보 {String(explorationSummary.eligible_area_count || '-')}곳 탐색</small>
          </div>
          <div className="scenario-list">
            {scenarios.map((scenario) => (
              <article key={scenario.id} className={selectedScenarioId === scenario.id ? 'scenario-card selected' : 'scenario-card'}>
                <div><h3>{scenario.title}</h3><strong>{scenario.candidate_count}곳</strong></div>
                <p>{scenario.description}</p>
                <ol>
                  {scenario.recommendations.slice(0, 3).map((item) => (
                    <li key={item.area_code}><span>{item.area_name}</span><b>{item.final_score.toFixed(1)}</b></li>
                  ))}
                </ol>
                <button type="button" disabled={loading || selectedScenarioId === scenario.id} onClick={() => onSelectScenario(scenario.id)}>
                  {selectedScenarioId === scenario.id ? '분석 완료' : '이 전략으로 분석'}
                </button>
              </article>
            ))}
          </div>
        </section>
      )}

      {(tradeoffs.length > 0 || relaxationOptions.length > 0) && (
        <section className="tradeoff-card" aria-label="상충 조건과 대안">
          <div className="section-title"><span>상충 조건과 대안</span></div>
          {tradeoffs.map((item, index) => <p key={`${item.kind}-${index}`} className={item.severity}>• {item.message}</p>)}
          {relaxationOptions.map((option) => (
            <button key={option.id} type="button" disabled={loading} onClick={() => onApplyRelaxation(option)}>
              {option.label} · 후보 {option.candidate_count_before}→{option.candidate_count_after}곳
            </button>
          ))}
        </section>
      )}
    </Fragment>
  )
}

function formatContextValue(value: string): string {
  return ({ fixed: '지역 고정', flexible: '인접 지역 가능', open: '서울 전체', low: '안정 우선', medium: '균형', high: '기회 우선' } as Record<string, string>)[value] || value
}
