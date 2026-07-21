import type { FinancePlanRequest, FinancePlanResponse, LeaseCandidateExtractResponse, RecommendationItem } from '../../types/api'

export type LeaseMoneyField = 'deposit' | 'monthlyRent' | 'managementFee' | 'keyMoney'
export type StartupMoneyField = 'interior' | 'equipment' | 'inventory' | 'workingCapital' | 'other' | 'ownCapital'

export interface LeaseCandidateDraft {
  sourceUrl: string
  sourceText: string
  title: string
  address: string
  areaSqm: string
  floor: string
  money: Record<LeaseMoneyField, string>
  notes: string | null
  warnings: string[]
}

export interface LeaseCandidateRecord {
  id: string
  areaCode: string
  areaName: string
  industryCode: string
  industryName: string
  sourceUrl: string | null
  sourceKind: 'manual' | 'url' | 'text' | 'url_and_text'
  title: string
  address: string
  depositKrw: number
  monthlyRentKrw: number
  managementFeeKrw: number | null
  keyMoneyKrw: number | null
  rentableAreaSqm: number | null
  floor: string | null
  notes: string | null
  warnings: string[]
  createdAt: string
  updatedAt: string
}

export interface LeaseCandidateFinanceState {
  additionalCosts: FinancePlanRequest['additional_costs']
  eligibility: FinancePlanRequest['eligibility']
  plan: FinancePlanResponse | null
}

export const emptyLeaseDraft = (): LeaseCandidateDraft => ({
  sourceUrl: '', sourceText: '', title: '', address: '', areaSqm: '', floor: '',
  money: { deposit: '', monthlyRent: '', managementFee: '', keyMoney: '' },
  notes: null, warnings: [],
})

export const emptyFinanceState = (): LeaseCandidateFinanceState => ({
  additionalCosts: {
    interior_krw: 0, equipment_krw: 0, initial_inventory_krw: 0,
    working_capital_krw: 0, other_krw: 0,
  },
  eligibility: {
    own_capital_krw: 0, business_status: 'pre_startup', business_age_months: null,
    is_small_business: null, vulnerability: 'unknown', has_policy_excluded_industry: null,
  },
  plan: null,
})

export function krwToManwon(value: number | null): string {
  return value == null ? '' : String(Math.round(value / 10_000))
}

export function manwonToKrw(value: string): number {
  const parsed = Number(value.replaceAll(',', '').trim())
  return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed * 10_000) : 0
}

export function manwonToNullableKrw(value: string): number | null {
  return value.trim() === '' ? null : manwonToKrw(value)
}

export function draftFromExtraction(response: LeaseCandidateExtractResponse, current: LeaseCandidateDraft): LeaseCandidateDraft {
  const item = response.extracted
  return {
    ...current,
    title: item.listing_title || '',
    address: item.address || '',
    areaSqm: item.rentable_area_sqm == null ? '' : String(item.rentable_area_sqm),
    floor: item.floor || '',
    money: {
      deposit: krwToManwon(item.deposit_krw),
      monthlyRent: krwToManwon(item.monthly_rent_krw),
      managementFee: krwToManwon(item.management_fee_krw),
      keyMoney: krwToManwon(item.key_money_krw),
    },
    notes: item.notes,
    warnings: response.warnings,
  }
}

export function draftFromCandidate(candidate: LeaseCandidateRecord): LeaseCandidateDraft {
  return {
    sourceUrl: candidate.sourceUrl || '', sourceText: '', title: candidate.title,
    address: candidate.address,
    areaSqm: candidate.rentableAreaSqm == null ? '' : String(candidate.rentableAreaSqm),
    floor: candidate.floor || '',
    money: {
      deposit: krwToManwon(candidate.depositKrw),
      monthlyRent: krwToManwon(candidate.monthlyRentKrw),
      managementFee: krwToManwon(candidate.managementFeeKrw),
      keyMoney: krwToManwon(candidate.keyMoneyKrw),
    },
    notes: candidate.notes, warnings: candidate.warnings,
  }
}

export function validateLeaseDraft(draft: LeaseCandidateDraft): string | null {
  if (draft.sourceUrl.trim()) {
    try {
      const parsed = new URL(draft.sourceUrl.trim())
      if (!['http:', 'https:'].includes(parsed.protocol)) return 'http 또는 https 매물 URL을 입력해주세요.'
    } catch {
      return '매물 URL 형식을 확인해주세요.'
    }
  }
  if (!draft.address.trim()) return '매물 주소를 입력해주세요.'
  if (draft.money.deposit.trim() === '') return '보증금을 입력해주세요. 보증금이 없으면 0을 입력하세요.'
  if (draft.money.monthlyRent.trim() === '') return '월세를 입력해주세요. 월세가 없으면 0을 입력하세요.'
  return null
}

export function normalizeSourceUrl(value: string | null): string | null {
  if (!value?.trim()) return null
  try {
    const parsed = new URL(value.trim())
    parsed.hash = ''
    if (parsed.pathname.length > 1) parsed.pathname = parsed.pathname.replace(/\/$/, '')
    return parsed.toString()
  } catch {
    return value.trim()
  }
}

export function hasDuplicateSourceUrl(candidates: LeaseCandidateRecord[], candidate: LeaseCandidateRecord): boolean {
  const normalized = normalizeSourceUrl(candidate.sourceUrl)
  return Boolean(normalized && candidates.some((item) => (
    item.id !== candidate.id && item.areaCode === candidate.areaCode
    && normalizeSourceUrl(item.sourceUrl) === normalized
  )))
}

export function candidateFromDraft(
  draft: LeaseCandidateDraft,
  area: RecommendationItem,
  existing?: LeaseCandidateRecord | null,
): LeaseCandidateRecord {
  const now = new Date().toISOString()
  const areaSqm = Number(draft.areaSqm)
  const sourceUrl = draft.sourceUrl.trim() || null
  const sourceKind = sourceUrl && draft.sourceText.trim() ? 'url_and_text'
    : sourceUrl ? (existing?.sourceUrl === sourceUrl ? existing.sourceKind : 'url')
      : draft.sourceText.trim() ? 'text' : existing?.sourceKind === 'text' ? 'text' : 'manual'
  return {
    id: existing?.id || globalThis.crypto?.randomUUID?.() || `lease-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    areaCode: area.area_code, areaName: area.area_name,
    industryCode: area.industry_code, industryName: area.industry_name,
    sourceUrl, sourceKind,
    title: draft.title.trim() || `${draft.address.trim()}${draft.floor.trim() ? ` ${draft.floor.trim()}` : ''}`,
    address: draft.address.trim(),
    depositKrw: manwonToKrw(draft.money.deposit),
    monthlyRentKrw: manwonToKrw(draft.money.monthlyRent),
    managementFeeKrw: manwonToNullableKrw(draft.money.managementFee),
    keyMoneyKrw: manwonToNullableKrw(draft.money.keyMoney),
    rentableAreaSqm: Number.isFinite(areaSqm) && areaSqm > 0 ? areaSqm : null,
    floor: draft.floor.trim() || null,
    notes: draft.notes,
    warnings: draft.warnings,
    createdAt: existing?.createdAt || now,
    updatedAt: now,
  }
}

export function candidateMissingCosts(candidate: LeaseCandidateRecord): string[] {
  const missing: string[] = []
  if (candidate.managementFeeKrw == null) missing.push('관리비')
  if (candidate.keyMoneyKrw == null) missing.push('권리금')
  return missing
}

export function firstYearLeaseCash(candidate: LeaseCandidateRecord): number | null {
  if (candidate.managementFeeKrw == null || candidate.keyMoneyKrw == null) return null
  return candidate.depositKrw + candidate.keyMoneyKrw
    + 12 * (candidate.monthlyRentKrw + candidate.managementFeeKrw)
}

export function buildFinancePlanRequest(
  candidate: LeaseCandidateRecord,
  state: LeaseCandidateFinanceState,
): FinancePlanRequest {
  if (candidate.managementFeeKrw == null || candidate.keyMoneyKrw == null) {
    throw new Error('관리비와 권리금을 확인한 뒤 자금계획을 만들 수 있습니다.')
  }
  return {
    candidate: {
      source_url: candidate.sourceUrl,
      listing_title: candidate.title,
      address: candidate.address,
      deposit_krw: candidate.depositKrw,
      monthly_rent_krw: candidate.monthlyRentKrw,
      management_fee_krw: candidate.managementFeeKrw,
      key_money_krw: candidate.keyMoneyKrw,
      rentable_area_sqm: candidate.rentableAreaSqm,
      floor: candidate.floor,
    },
    additional_costs: state.additionalCosts,
    eligibility: state.eligibility,
  }
}

export function formatKrw(value: number): string {
  if (value >= 100_000_000) {
    const eok = value / 100_000_000
    return `${Number.isInteger(eok) ? eok : eok.toFixed(1)}억원`
  }
  return `${Math.round(value / 10_000).toLocaleString('ko-KR')}만원`
}
