import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { LeasePlan, RecommendationItem } from '../../types/api'

interface Props {
  item: RecommendationItem
  totalStartupBudgetKrw: number | null
}

export function LeasePlanCard({ item, totalStartupBudgetKrw }: Props) {
  const [depositManwon, setDepositManwon] = useState('')
  const [plan, setPlan] = useState<LeasePlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const estimate = item.rental_estimate

  useEffect(() => {
    setPlan(null)
    setError(null)
    setDepositManwon('')
  }, [item.area_code])

  if (!estimate) return null

  const calculate = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.leasePlan({
        area_code: item.area_code,
        floor: estimate.floor,
        rentable_area_sqm: estimate.rentable_area_sqm,
        deposit_krw: depositManwon ? Number(depositManwon) * 10_000 : null,
        total_startup_budget_krw: totalStartupBudgetKrw,
      })
      setPlan(response.lease_plan)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '임대 계획을 계산하지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="lease-plan-card" aria-labelledby="lease-plan-title">
      <div>
        <span className="eyebrow">LEASE PLAN</span>
        <h2 id="lease-plan-title">{item.area_name} 임대 계획</h2>
        <p>
          환산 월 점유비용 <strong>{formatWon(estimate.estimated_converted_monthly_rent_krw)}</strong>
          {' · '}{estimate.rent_basis_name} · {estimate.rent_basis_geography === 'district' ? '자치구' : '행정동'} 기준 · {floorName(estimate.rent_basis_floor)}
          {estimate.fallback_used && ' (전체 층 평균 대체)'}
          {estimate.geography_fallback_used && ' (자치구 기준 대체)'}
        </p>
      </div>
      <div className="lease-plan-input">
        <label><span>예상 보증금</span><input type="number" min="0" value={depositManwon} onChange={(event) => setDepositManwon(event.target.value)} placeholder="예: 5000" /><small>만원</small></label>
        <button type="button" onClick={calculate} disabled={loading}>{loading ? '계산 중…' : depositManwon ? '현금 월세 계산' : '환산비용 확인'}</button>
      </div>
      {error && <p className="lease-plan-error">{error}</p>}
      {plan && (
        <dl className="lease-plan-grid">
          <div><dt>현금 월세</dt><dd>{plan.cash_monthly_rent_krw == null ? '보증금 입력 시 계산' : formatWon(plan.cash_monthly_rent_krw)}</dd></div>
          <div><dt>연간 현금 월세</dt><dd>{formatNullableWon(plan.annual_cash_rent_krw)}</dd></div>
          <div><dt>첫해 현금 지출</dt><dd>{formatNullableWon(plan.first_year_cash_outlay_krw)}</dd></div>
          <div><dt>남는 창업예산</dt><dd>{formatNullableWon(plan.remaining_startup_budget_krw)}</dd></div>
          <div><dt>반환 가능 보증금</dt><dd>{formatNullableWon(plan.refundable_deposit_krw)}</dd></div>
          <div><dt>예산 중 보증금 비중</dt><dd>{plan.deposit_share_of_budget == null ? '-' : `${(plan.deposit_share_of_budget * 100).toFixed(1)}%`}</dd></div>
        </dl>
      )}
      <small className="lease-plan-disclosure">{plan?.disclosure || estimate.disclosure}</small>
    </section>
  )
}

function formatWon(value: number): string {
  return `${Math.round(value).toLocaleString('ko-KR')}원`
}

function formatNullableWon(value: number | null): string {
  return value == null ? '-' : formatWon(value)
}

function floorName(floor: 'all' | 'f1' | 'non_f1'): string {
  return floor === 'all' ? '전체 층 평균' : floor === 'f1' ? '1층' : '1층 외'
}
