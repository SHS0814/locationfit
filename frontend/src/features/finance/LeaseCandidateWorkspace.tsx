import { useState } from 'react'
import { api } from '../../api/client'
import type { CatalogBenefit, FinancePlanRequest, FinancialVulnerability, RecommendationItem } from '../../types/api'
import {
  buildFinancePlanRequest,
  candidateMissingCosts,
  emptyFinanceState,
  firstYearLeaseCash,
  formatKrw,
  krwToManwon,
  manwonToKrw,
  type LeaseCandidateFinanceState,
  type LeaseCandidateRecord,
  type StartupMoneyField,
} from './model'


const startupFields: Array<{ key: StartupMoneyField; label: string }> = [
  { key: 'interior', label: '인테리어' }, { key: 'equipment', label: '설비·집기' },
  { key: 'inventory', label: '초도 물품' }, { key: 'workingCapital', label: '초기 운영자금' },
  { key: 'other', label: '기타' }, { key: 'ownCapital', label: '내 자기자금' },
]

const statusLabel = {
  basic_fit: '기본조건 부합', needs_review: '추가 확인 필요', not_eligible: '입력조건상 비대상',
}

const productTypeLabel = {
  bank_loan: 'KB 은행대출', policy_fund: '정책자금', support_program: '지원사업', guarantee: '보증상품',
}

const catalogStatusLabel = {
  active: '현재 안내 중', upcoming: '접수 예정', unknown: '접수상태 확인 필요',
}

function benefitText(benefit: CatalogBenefit): string {
  const terms: string[] = []
  if (benefit.amount_max_krw != null) terms.push(`최대 ${formatKrw(benefit.amount_max_krw)}`)
  if (benefit.interest_rate_min_pct != null || benefit.interest_rate_max_pct != null) {
    const minimum = benefit.interest_rate_min_pct == null ? '' : `${benefit.interest_rate_min_pct}%`
    const maximum = benefit.interest_rate_max_pct == null ? '' : `${benefit.interest_rate_max_pct}%`
    terms.push(`금리 ${minimum && maximum ? `${minimum}~${maximum}` : minimum || maximum}`)
  }
  if (benefit.guarantee_rate_pct != null) terms.push(`보증비율 ${benefit.guarantee_rate_pct}%`)
  if (benefit.interest_subsidy_rate_pct != null) terms.push(`이차보전 ${benefit.interest_subsidy_rate_pct}%p`)
  if (benefit.guarantee_fee_rate_pct != null) terms.push(`보증료율 ${benefit.guarantee_fee_rate_pct}%`)
  if (benefit.term_max_months != null) terms.push(`최대 ${benefit.term_max_months}개월`)
  return terms.join(' · ') || benefit.original_text || '세부 혜택은 공식 원문에서 확인해야 합니다.'
}

function startupValue(state: LeaseCandidateFinanceState, key: StartupMoneyField): number {
  if (key === 'ownCapital') return state.eligibility.own_capital_krw
  const map = {
    interior: 'interior_krw', equipment: 'equipment_krw', inventory: 'initial_inventory_krw',
    workingCapital: 'working_capital_krw', other: 'other_krw',
  } as const
  return state.additionalCosts[map[key]]
}

export function LeaseCandidateWorkspace({
  area, candidates, selectedId, financeById,
  onBack, onAdd, onEdit, onDelete, onSelect, onFinanceChange,
}: {
  area: RecommendationItem
  candidates: LeaseCandidateRecord[]
  selectedId: string | null
  financeById: Record<string, LeaseCandidateFinanceState>
  onBack: () => void
  onAdd: () => void
  onEdit: (id: string) => void
  onDelete: (id: string) => void
  onSelect: (id: string) => void
  onFinanceChange: (id: string, state: LeaseCandidateFinanceState) => void
}) {
  const selected = candidates.find((item) => item.id === selectedId) || null
  const state = selected ? financeById[selected.id] || emptyFinanceState() : null
  const [planning, setPlanning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateState = (patch: Partial<LeaseCandidateFinanceState>) => {
    if (!selected || !state) return
    onFinanceChange(selected.id, { ...state, ...patch, plan: null })
    setError(null)
  }

  const updateStartup = (key: StartupMoneyField, input: string) => {
    if (!state) return
    const value = manwonToKrw(input)
    if (key === 'ownCapital') return updateState({ eligibility: { ...state.eligibility, own_capital_krw: value } })
    const map = {
      interior: 'interior_krw', equipment: 'equipment_krw', inventory: 'initial_inventory_krw',
      workingCapital: 'working_capital_krw', other: 'other_krw',
    } as const
    updateState({ additionalCosts: { ...state.additionalCosts, [map[key]]: value } })
  }

  const updateEligibility = (patch: Partial<FinancePlanRequest['eligibility']>) => {
    if (state) updateState({ eligibility: { ...state.eligibility, ...patch } })
  }

  const createPlan = async () => {
    if (!selected || !state) return
    if (state.eligibility.business_status === 'operating' && state.eligibility.business_age_months == null) {
      setError('영업 중이라면 업력(개월)을 입력해주세요.')
      return
    }
    setPlanning(true)
    setError(null)
    try {
      const plan = await api.financePlan(buildFinancePlanRequest(selected, state))
      onFinanceChange(selected.id, { ...state, plan })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '자금계획을 만들지 못했습니다.')
    } finally {
      setPlanning(false)
    }
  }

  return (
    <section className="lease-candidate-workspace">
      <header className="candidate-workspace-header">
        <button type="button" className="back-button" onClick={onBack}>← 주변 점포 다시 보기</button>
        <div><span className="eyebrow">STEP 3 · LEASE SHORTLIST</span><h2>{area.area_name} 임대매물 후보함</h2><p>{area.industry_name} · 직접 찾은 실제 임대매물을 비교합니다.</p></div>
        <button type="button" className="candidate-add-button" onClick={onAdd}>+ 임대매물 추가</button>
      </header>

      {candidates.length === 0 ? <div className="candidate-empty"><h3>추가한 임대매물이 없습니다</h3><p>직접 확인한 임대매물 정보를 입력해 비교하세요.</p><button type="button" onClick={onAdd}>첫 임대매물 추가</button></div> : <div className="candidate-grid">{candidates.map((candidate) => {
        const total = firstYearLeaseCash(candidate)
        const missing = candidateMissingCosts(candidate)
        return <article key={candidate.id} className={selectedId === candidate.id ? 'selected' : ''}>
          <div className="candidate-card-top"><span>{candidate.sourceKind === 'manual' ? '직접 입력' : '외부 매물'}</span><span>{candidate.floor || '층 미입력'} · {candidate.rentableAreaSqm ? `${candidate.rentableAreaSqm.toLocaleString('ko-KR')}㎡` : '면적 미입력'}</span></div>
          <h3>{candidate.title}</h3><p>{candidate.address}</p>
          <dl><div><dt>보증금</dt><dd>{formatKrw(candidate.depositKrw)}</dd></div><div><dt>월세+관리비</dt><dd>{candidate.managementFeeKrw == null ? '관리비 미확인' : formatKrw(candidate.monthlyRentKrw + candidate.managementFeeKrw)}</dd></div><div><dt>권리금</dt><dd>{candidate.keyMoneyKrw == null ? '미확인' : formatKrw(candidate.keyMoneyKrw)}</dd></div><div><dt>첫해 임차 현금</dt><dd>{total == null ? '비용 확인 필요' : formatKrw(total)}</dd></div></dl>
          {missing.length > 0 && <p className="candidate-missing">확인 필요: {missing.join(', ')}</p>}
          <div className="candidate-actions"><button type="button" onClick={() => onEdit(candidate.id)}>편집</button><button type="button" onClick={() => onDelete(candidate.id)}>삭제</button><button type="button" className="select" onClick={() => onSelect(candidate.id)}>{selectedId === candidate.id ? '선택됨' : '이 매물로 자금계획'}</button></div>
        </article>
      })}</div>}

      {selected && state && <section className="candidate-finance-section">
        <div className="finance-heading"><div><span className="eyebrow">FUNDING PLAN</span><h2>{selected.title} 자금계획</h2></div><span>{selected.address}</span></div>
        {candidateMissingCosts(selected).length > 0 ? <div className="finance-incomplete"><strong>임차비 확인이 더 필요합니다.</strong><p>{candidateMissingCosts(selected).join(', ')}에 0원 또는 실제 금액을 입력한 뒤 자금계획을 만들 수 있습니다.</p><button type="button" onClick={() => onEdit(selected.id)}>매물 정보 수정</button></div> : <>
          <div className="finance-step"><div className="finance-step-title"><b>1</b><div><h3>추가 창업비와 자기자금</h3><p>모두 만원 단위이며 입력하지 않은 추가비용은 0원으로 계산합니다.</p></div></div><div className="finance-fields money startup-grid">{startupFields.map((field) => <label key={field.key}><span>{field.label}</span><div><input inputMode="numeric" value={krwToManwon(startupValue(state, field.key))} onChange={(event) => updateStartup(field.key, event.target.value)} /><small>만원</small></div></label>)}</div></div>
          <div className="finance-step"><div className="finance-step-title"><b>2</b><div><h3>정책지원 기본조건</h3><p>승인 여부가 아니라 공식 제도의 1차 후보만 판정합니다.</p></div></div><div className="finance-fields eligibility">
            <label><span>사업 상태</span><select value={state.eligibility.business_status} onChange={(event) => updateEligibility({ business_status: event.target.value as 'pre_startup' | 'operating', business_age_months: event.target.value === 'pre_startup' ? null : state.eligibility.business_age_months })}><option value="pre_startup">예비창업</option><option value="operating">영업 중</option></select></label>
            {state.eligibility.business_status === 'operating' && <label><span>현재 업력(개월)</span><input type="number" min="0" value={state.eligibility.business_age_months ?? ''} onChange={(event) => updateEligibility({ business_age_months: event.target.value === '' ? null : Number(event.target.value) })} /></label>}
            <label><span>소상공인 기준</span><select value={state.eligibility.is_small_business == null ? 'unknown' : String(state.eligibility.is_small_business)} onChange={(event) => updateEligibility({ is_small_business: event.target.value === 'unknown' ? null : event.target.value === 'true' })}><option value="unknown">아직 모름</option><option value="true">해당</option><option value="false">비해당</option></select></label>
            <label><span>금융취약 요건</span><select value={state.eligibility.vulnerability} onChange={(event) => updateEligibility({ vulnerability: event.target.value as FinancialVulnerability })}><option value="unknown">아직 모름</option><option value="low_credit">개인신용평점 하위 20%</option><option value="basic_livelihood">기초생활수급자</option><option value="near_poverty">차상위계층 이하</option><option value="earned_income_tax_credit">근로장려금 신청자격</option><option value="none">해당 없음</option></select></label>
            <label><span>정책자금 융자제외 업종</span><select value={state.eligibility.has_policy_excluded_industry == null ? 'unknown' : String(state.eligibility.has_policy_excluded_industry)} onChange={(event) => updateEligibility({ has_policy_excluded_industry: event.target.value === 'unknown' ? null : event.target.value === 'true' })}><option value="unknown">아직 모름</option><option value="false">아님</option><option value="true">해당</option></select></label>
          </div><button className="finance-primary" type="button" onClick={createPlan} disabled={planning}>{planning ? '자금계획 계산 중…' : '자금계획·정책지원 후보 보기'}</button>{error && <div className="finance-error" role="alert">{error}</div>}</div>
        </>}

        {state.plan && <div className="finance-result">
          <div className="funding-summary"><div><span>첫해 총 필요자금</span><strong>{formatKrw(state.plan.funding.total_first_year_cash_need_krw)}</strong></div><div><span>내 자기자금</span><strong>{formatKrw(state.plan.funding.own_capital_krw)}</strong></div><div className={state.plan.funding.funding_gap_krw > 0 ? 'gap' : ''}><span>부족자금</span><strong>{formatKrw(state.plan.funding.funding_gap_krw)}</strong></div></div>
          <dl className="funding-breakdown"><div><dt>반환 가능 보증금</dt><dd>{formatKrw(state.plan.funding.refundable_deposit_krw)}</dd></div><div><dt>권리금</dt><dd>{formatKrw(state.plan.funding.one_time_nonrefundable_krw)}</dd></div><div><dt>12개월 월세·관리비</dt><dd>{formatKrw(state.plan.funding.annual_occupancy_cost_krw)}</dd></div><div><dt>추가 창업비</dt><dd>{formatKrw(state.plan.funding.additional_startup_cost_krw)}</dd></div></dl>
          <h3>금융지원 상품 1차 후보</h3>
          <p className="catalog-result-summary">
            DB 카탈로그 {state.plan.policy_candidates.length}개 · 기본조건 부합 {state.plan.policy_candidates.filter((item) => item.status === 'basic_fit').length}개 · 추가 확인 {state.plan.policy_candidates.filter((item) => item.status === 'needs_review').length}개
          </p>
          <div className="policy-list">{state.plan.policy_candidates.map((candidate) => <article key={candidate.program_id} className={`policy-card ${candidate.status}`}>
            <div className="policy-card-header"><span>{productTypeLabel[candidate.product_type]} · {candidate.provider}</span><b>{statusLabel[candidate.status]}</b></div>
            <h4>{candidate.name}</h4>
            {candidate.summary && <p className="policy-summary">{candidate.summary}</p>}
            <p>{candidate.reasons.join(' ')}</p>
            {candidate.benefits.length > 0 && <ul className="policy-benefits">{candidate.benefits.map((benefit, index) => <li key={`${candidate.program_id}-benefit-${index}`}>{benefitText(benefit)}</li>)}</ul>}
            {candidate.checks_required.length > 0 && <details><summary>추가 확인사항 {candidate.checks_required.length}개</summary><ul>{candidate.checks_required.map((check) => <li key={check}>{check}</li>)}</ul></details>}
            <div className="policy-card-footer"><span>{catalogStatusLabel[candidate.catalog_status]}{candidate.application_end_date ? ` · ${candidate.application_end_date} 마감` : ''}</span><a href={candidate.application_url || candidate.source_url} target="_blank" rel="noreferrer">공식 원문 · {candidate.source_checked_at}</a></div>
          </article>)}</div>
          <small className="finance-final-disclosure">{state.plan.disclosure}</small>
        </div>}
      </section>}
    </section>
  )
}
