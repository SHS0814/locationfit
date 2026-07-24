import { useState, type FormEvent } from 'react'
import type {
  AgentMessage,
  AgentPhase,
  AgentAssumption,
  AreaComparison,
  DataGap,
  FounderContext,
  MarketLookupResult,
  MetadataResponse,
  RecommendationDraft,
  RelaxationOption,
  StrategyScenario,
  TradeoffInsight,
  FloorType,
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
  marketLookup: MarketLookupResult | null
  loading: boolean
  onSend: (message: string) => void
  onConfirm: () => void
  onSelectScenario: (id: 'condition_fit' | 'growth' | 'stability') => void
  onApplyRelaxation: (option: RelaxationOption) => void
  onAssumptionStatus: (id: string, status: AgentAssumption['status']) => void
  onDraftChange: (draft: RecommendationDraft) => void
  onReset: () => void
  onRunDemo: () => void
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

const followUpPrompts = [
  '1위가 추천된 핵심 이유를 자세히 설명해줘',
  '1위와 2위 후보의 차이를 비교해줘',
  '가장 주의해서 볼 지표가 뭐야?',
  '이 추천의 데이터 출처와 점수 산식을 설명해줘',
]

export function AgentPanel({
  metadata, history, draft, phase, context, assumptions, explorationSummary, scenarios,
  tradeoffs, relaxationOptions, dataGaps, selectedScenarioId, comparison, marketLookup, loading,
  onSend, onConfirm, onSelectScenario, onApplyRelaxation, onAssumptionStatus, onDraftChange,
  onReset, onRunDemo,
}: Props) {
  const [message, setMessage] = useState('')
  const [areaUnit, setAreaUnit] = useState<'sqm' | 'pyeong'>('sqm')
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
        <div className="agent-heading-top">
          <span className="eyebrow">AI LOCATION AGENT</span>
          <span className="agent-heading-actions">
            <button type="button" onClick={onRunDemo} disabled={loading} aria-label="홍대 커피 매장 데모 불러오기">
              데모 불러오기
            </button>
            <button type="button" onClick={onReset} disabled={loading} aria-label="대화와 분석 결과 초기화">
              대화·분석 초기화
            </button>
          </span>
        </div>
        <h2>AI에게 사업 조건 전달</h2>
        <p>AI가 조건을 구조화하고 시장 탐색부터 매물·자금계획까지 단계별로 지휘합니다.</p>
      </div>

      <div className="chat-log" aria-live="polite">
        {history.map((item, index) => (
          <div key={`${item.role}-${index}`} className={`chat-message ${item.role}`}>
            <span>{item.role === 'assistant' ? 'AI' : '나'}</span>
            <p>{item.content}</p>
          </div>
        ))}
        {loading && <div className="chat-message assistant pending"><span>AI</span><p>다음 단계에 필요한 데이터와 분석 도구를 확인하고 있어요…</p></div>}
      </div>

      <form className="chat-composer" onSubmit={submit}>
        <label className="sr-only" htmlFor="agent-message">상담 메시지</label>
        <textarea
          id="agent-message"
          rows={2}
          maxLength={2000}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={phase === 'results' ? '추천 결과에서 궁금한 점을 물어보세요' : '예: 매출 높은 상권 5곳 알려줘'}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !message.trim()}>보내기</button>
      </form>

      {phase === 'results' && (
        <div className="follow-up-prompts" aria-label="추천 결과 후속 질문">
          {followUpPrompts.map((prompt) => (
            <button key={prompt} type="button" disabled={loading} onClick={() => onSend(prompt)}>{prompt}</button>
          ))}
        </div>
      )}

      {marketLookup && (
        <section className="lookup-card" aria-label="상권 통계 조회 결과">
          <div className="section-title">
            <span>바로 조회</span>
            <small>{marketLookup.data_period}</small>
          </div>
          <h3>{marketLookup.title}</h3>
          {Object.keys(marketLookup.filters).length > 0 && (
            <p className="lookup-filters">조회 조건 · {Object.values(marketLookup.filters).filter((value, index, values) => values.indexOf(value) === index).join(' · ')}</p>
          )}
          <dl className="lookup-distribution">
            <div><dt>평균</dt><dd>{marketLookup.distribution.mean_display}</dd></div>
            <div><dt>중앙값</dt><dd>{marketLookup.distribution.median_display}</dd></div>
            <div><dt>표준편차</dt><dd>{marketLookup.distribution.standard_deviation_display}</dd></div>
          </dl>
          <p className="lookup-population">필터 적용 후 전체 {marketLookup.distribution.population_count.toLocaleString('ko-KR')}개 대상 기준</p>
          <ol>
            {marketLookup.rows.map((row) => (
              <li key={`${row.rank}-${row.entity_code || row.entity_name}-${row.district_name || ''}`}>
                <b>{row.rank}</b>
                <span>
                  <strong>{row.entity_name}</strong>
                  <small>{[
                    row.district_name,
                    row.admin_dong_name,
                    row.area_count > 1 ? `관측 상권 ${row.area_count}곳` : null,
                  ].filter(Boolean).join(' · ')}</small>
                  <small>평균 대비 {row.difference_from_mean_display} · 중앙값 대비 {row.difference_from_median_display} · {formatSigma(row.standard_deviation_distance)}</small>
                </span>
                <em>{row.metric_display_value}</em>
              </li>
            ))}
          </ol>
          <small>{marketLookup.disclosure}</small>
        </section>
      )}

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
            {[3, 5, 10, 15, 20].map((count) => <option key={count} value={count}>{count}곳</option>)}
          </select>
        </div>

        <label>
          <span>업종</span>
          <select value={draft.industry_code || ''} onChange={(event) => update('industry_code', event.target.value || null)}>
            <option value="">대화로 업종을 알려주세요</option>
            {metadata.industries.map((option) => <option key={option.code} value={option.code}>{option.name}</option>)}
          </select>
        </label>

        <div className="budget-rent-card">
          <div className="section-title"><span>예산·예상 임대료</span><small>선택 입력</small></div>
          <div className="money-input-grid">
            <label><span>총 창업예산</span><div><input type="number" min="1" value={toManwon(draft.total_startup_budget_krw)} onChange={(event) => update('total_startup_budget_krw', fromManwon(event.target.value))} placeholder="예: 15000" /><small>만원</small></div></label>
            <label><span>월 환산임대료 한도</span><div><input type="number" min="1" value={toManwon(draft.monthly_converted_rent_limit_krw)} onChange={(event) => update('monthly_converted_rent_limit_krw', fromManwon(event.target.value))} placeholder="예: 500" /><small>만원</small></div></label>
          </div>
          {(draft.monthly_converted_rent_limit_krw != null || draft.rentable_area_sqm != null) && (
            <div className="rent-condition-grid">
              <label><span>임대면적(전용+공용)</span><div className="area-input"><input type="number" min="0.1" step="0.1" value={formatAreaInput(draft.rentable_area_sqm, areaUnit)} onChange={(event) => update('rentable_area_sqm', parseAreaInput(event.target.value, areaUnit))} /><button type="button" onClick={() => setAreaUnit(areaUnit === 'sqm' ? 'pyeong' : 'sqm')}>{areaUnit === 'sqm' ? '㎡' : '평'}</button></div></label>
              <label><span>층 구분</span><select value={draft.floor || ''} onChange={(event) => update('floor', (event.target.value || null) as FloorType | null)}><option value="">선택</option>{metadata.rent_floors.map((floor) => <option key={floor.code} value={floor.code}>{floor.name}</option>)}</select></label>
            </div>
          )}
          <small>월 한도와 임대조건을 모두 입력한 경우에만 예산 적합도 20%를 반영합니다. 총 창업예산만 입력하면 순위는 바뀌지 않습니다.</small>
        </div>
        <label>
          <span>선호 자치구</span>
          <select value={draft.preferred_districts[0] || ''} onChange={(event) => update('preferred_districts', event.target.value ? [event.target.value] : [])}>
            <option value="">서울 전체</option>
            {metadata.districts.map((district) => <option key={district}>{district}</option>)}
          </select>
        </label>

        <div className="condition-group">
          <span>주요 고객 연령 <small>미지정 시 전 연령</small></span>
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
            <span>선호 시간대 <small>미지정 시 전 시간대</small></span>
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
            <span>상권 유형 <small>미지정 시 전체 유형</small></span>
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

function formatSigma(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `평균에서 ${sign}${value.toFixed(2)}σ`
}

function formatStoreDensity(value: number | null): string {
  return value == null ? '-' : `${value.toLocaleString('ko-KR', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}개/㎢`
}

function toManwon(value: number | null): string {
  return value == null ? '' : String(value / 10_000)
}

function fromManwon(value: string): number | null {
  const parsed = Number(value)
  return value === '' || !Number.isFinite(parsed) || parsed <= 0 ? null : parsed * 10_000
}

function formatAreaInput(value: number | null, unit: 'sqm' | 'pyeong'): string {
  if (value == null) return ''
  return String(Number((unit === 'sqm' ? value : value / 3.305785).toFixed(2)))
}

function parseAreaInput(value: string, unit: 'sqm' | 'pyeong'): number | null {
  const parsed = Number(value)
  if (value === '' || !Number.isFinite(parsed) || parsed <= 0) return null
  return unit === 'sqm' ? parsed : parsed * 3.305785
}
