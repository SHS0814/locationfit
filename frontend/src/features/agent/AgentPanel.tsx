import { useState, type FormEvent } from 'react'
import type {
  AgentMessage,
  AgentPhase,
  AgentAssumption,
  AreaComparison,
  DataGap,
  FounderContext,
  MetadataResponse,
  RecommendationDraft,
  RelaxationOption,
  StrategyScenario,
  TradeoffInsight,
} from '../../types/api'
import { isDraftReady, toggleDraftValue } from './model'

interface Props {
  metadata: MetadataResponse
  history: AgentMessage[]
  draft: RecommendationDraft
  phase: AgentPhase
  context: FounderContext
  assumptions: AgentAssumption[]
  explorationSummary: Record<string, unknown>
  scenarios: StrategyScenario[]
  tradeoffs: TradeoffInsight[]
  relaxationOptions: RelaxationOption[]
  dataGaps: DataGap[]
  selectedScenarioId: 'condition_fit' | 'growth' | 'stability' | null
  comparison: AreaComparison[]
  loading: boolean
  onSend: (message: string) => void
  onConfirm: () => void
  onSelectScenario: (id: 'condition_fit' | 'growth' | 'stability') => void
  onApplyRelaxation: (option: RelaxationOption) => void
  onAssumptionStatus: (id: string, status: AgentAssumption['status']) => void
  onDraftChange: (draft: RecommendationDraft) => void
}

const importanceFields: Array<{ key: keyof RecommendationDraft; label: string }> = [
  { key: 'floating_population_importance', label: '유동인구' },
  { key: 'resident_population_importance', label: '상주인구' },
  { key: 'worker_population_importance', label: '직장인구' },
  { key: 'weekend_importance', label: '주말 유동' },
  { key: 'apartment_importance', label: '아파트 배후' },
  { key: 'transport_facility_importance', label: '교통시설' },
  { key: 'education_facility_importance', label: '교육시설' },
  { key: 'medical_facility_importance', label: '의료시설' },
  { key: 'shopping_facility_importance', label: '쇼핑시설' },
  { key: 'culture_facility_importance', label: '문화시설' },
]

export function AgentPanel({
  metadata, history, draft, phase, context, assumptions, explorationSummary, scenarios,
  tradeoffs, relaxationOptions, dataGaps, selectedScenarioId, comparison, loading,
  onSend, onConfirm, onSelectScenario, onApplyRelaxation, onAssumptionStatus, onDraftChange,
}: Props) {
  const [message, setMessage] = useState('')
  const update = <K extends keyof RecommendationDraft>(key: K, value: RecommendationDraft[K]) => {
    onDraftChange({ ...draft, [key]: value })
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = message.trim()
    if (!trimmed || loading) return
    setMessage('')
    onSend(trimmed)
  }

  return (
    <aside className="agent-panel" aria-label="AI 입지 상담">
      <div className="agent-heading">
        <span className="eyebrow">AI LOCATION AGENT</span>
        <h2>창업 조건을 함께 정리해요</h2>
        <p>AI는 조건을 해석하고, 점수와 순위는 검증된 추천 엔진이 계산합니다.</p>
      </div>

      <div className="chat-log" aria-live="polite">
        {history.map((item, index) => (
          <div key={`${item.role}-${index}`} className={`chat-message ${item.role}`}>
            <span>{item.role === 'assistant' ? 'AI' : '나'}</span>
            <p>{item.content}</p>
          </div>
        ))}
        {loading && <div className="chat-message assistant pending"><span>AI</span><p>조건과 데이터를 확인하고 있어요…</p></div>}
      </div>

      <form className="chat-composer" onSubmit={submit}>
        <label className="sr-only" htmlFor="agent-message">상담 메시지</label>
        <textarea
          id="agent-message"
          rows={2}
          maxLength={2000}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="예: 강남에서 20대 대상 카페를 열고 싶어요"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !message.trim()}>보내기</button>
      </form>

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
                  {selectedScenarioId === scenario.id ? '선택됨' : '이 전략 선택'}
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

      <section className="condition-card" aria-label="추천 조건 카드">
        <div className="condition-heading">
          <div><span>추천 조건</span><strong>{phaseLabel(phase, selectedScenarioId)}</strong></div>
          <select value={draft.top_n} onChange={(event) => update('top_n', Number(event.target.value))} aria-label="추천 결과 개수">
            {[5, 10, 15, 20].map((count) => <option key={count} value={count}>{count}곳</option>)}
          </select>
        </div>

        <label>
          <span>업종</span>
          <select value={draft.industry_code || ''} onChange={(event) => update('industry_code', event.target.value || null)}>
            <option value="">대화로 업종을 알려주세요</option>
            {metadata.industries.map((option) => <option key={option.code} value={option.code}>{option.name}</option>)}
          </select>
        </label>
        <label>
          <span>선호 자치구</span>
          <select value={draft.preferred_districts[0] || ''} onChange={(event) => update('preferred_districts', event.target.value ? [event.target.value] : [])}>
            <option value="">서울 전체</option>
            {metadata.districts.map((district) => <option key={district}>{district}</option>)}
          </select>
        </label>

        <div className="condition-group">
          <span>주요 고객 연령</span>
          <div className="chip-group">
            {metadata.age_groups.map((option) => (
              <button key={option.code} type="button" className={draft.target_age_groups.includes(option.code) ? 'chip active' : 'chip'}
                onClick={() => update('target_age_groups', toggleDraftValue(draft.target_age_groups, option.code))}>
                {option.name}
              </button>
            ))}
          </div>
        </div>

        <details className="condition-details">
          <summary>시간대·상권 유형·중요도 조정</summary>
          <div className="condition-group">
            <span>선호 시간대</span>
            <div className="chip-group">
              {metadata.time_bands.map((option) => (
                <button key={option.code} type="button" className={draft.preferred_time_bands.includes(option.code) ? 'chip active' : 'chip'}
                  onClick={() => update('preferred_time_bands', toggleDraftValue(draft.preferred_time_bands, option.code))}>
                  {option.name}
                </button>
              ))}
            </div>
          </div>
          <div className="condition-group">
            <span>상권 유형</span>
            <div className="chip-group">
              {metadata.area_types.map((option) => (
                <button key={option.code} type="button" className={draft.preferred_area_types.includes(option.code) ? 'chip active' : 'chip'}
                  onClick={() => update('preferred_area_types', toggleDraftValue(draft.preferred_area_types, option.code))}>
                  {option.name}
                </button>
              ))}
            </div>
          </div>
          <div className="slider-list">
            {importanceFields.map(({ key, label }) => (
              <label className="slider-row" key={key}>
                <span>{label}</span>
                <input type="range" min="0" max="1" step="0.1" value={Number(draft[key])}
                  onChange={(event) => update(key, Number(event.target.value) as never)} />
                <strong>{Number(draft[key]).toFixed(1)}</strong>
              </label>
            ))}
          </div>
        </details>

        <button className="confirm-button" type="button" onClick={onConfirm} disabled={loading || !isDraftReady(draft) || !selectedScenarioId}>
          이 조건으로 분석
        </button>
        {dataGaps.map((gap) => <small className="data-gap" key={gap.code}>{gap.message}</small>)}
        <small>아파트 시세는 주거 구매력 참고치이며 상가 임대료·보증금으로 해석하지 않습니다.</small>
      </section>

      {comparison.length > 0 && (
        <section className="comparison-card" aria-label="상권 비교 지표">
          <h3>비교한 상권</h3>
          {comparison.map((area) => (
            <div key={area.area_code}>
              <strong>{area.area_name}</strong>
              <span>유동 {formatNumber(area.floating_population)} · 직장 {formatNumber(area.worker_population)}</span>
              <span>동종업종 점포 {formatStoreCount(area.recent_store_count)} · 밀도 {formatStoreDensity(area.same_industry_store_density)}</span>
              <span>최근 성장률 {formatPercent(area.recent_4q_growth_rate)} · 신뢰도 {area.reliability_grade || '-'}</span>
            </div>
          ))}
        </section>
      )}
    </aside>
  )
}

function phaseLabel(phase: AgentPhase, selected: string | null): string {
  if (phase === 'results') return '분석 완료'
  if (phase === 'exploring') return '데이터 탐색 중'
  if (selected || phase === 'ready_for_confirmation') return '최종 확인'
  if (phase === 'scenarios_ready') return '전략 비교'
  return '맥락 파악 중'
}

function formatContextValue(value: string): string {
  return ({ fixed: '지역 고정', flexible: '인접 지역 가능', open: '서울 전체', low: '안정 우선', medium: '균형', high: '기회 우선' } as Record<string, string>)[value] || value
}

function formatNumber(value: number | null): string {
  return value == null ? '-' : Math.round(value).toLocaleString('ko-KR')
}

function formatPercent(value: number | null): string {
  return value == null ? '-' : `${(value * 100).toFixed(1)}%`
}

function formatStoreCount(value: number | null): string {
  return value == null ? '-' : `${Math.round(value).toLocaleString('ko-KR')}개`
}

function formatStoreDensity(value: number | null): string {
  return value == null ? '-' : `${value.toLocaleString('ko-KR', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}개/㎢`
}
