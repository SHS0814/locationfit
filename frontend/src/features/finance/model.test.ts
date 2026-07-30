import { describe, expect, it } from 'vitest'
import {
  buildFinancePlanRequest, candidateFromDraft, candidateMissingCosts, emptyFinanceState,
  emptyLeaseDraft, firstYearLeaseCash, formatKrw, isManwonInput, leaseSelectionForArea, manwonToKrw,
  mergeFinancePlanIfCurrent, validateLeaseDraft, type LeaseCandidateFinanceState,
  type LeaseCandidateRecord,
} from './model'


const candidate = (patch: Partial<LeaseCandidateRecord> = {}): LeaseCandidateRecord => ({
  id: 'listing-1', areaCode: 'A1', areaName: '테스트상권', industryCode: 'CS100001',
  industryName: '한식', sourceUrl: null, sourceKind: 'manual', title: '테스트 매물',
  address: '서울시 중구', depositKrw: 50_000_000, monthlyRentKrw: 2_000_000,
  managementFeeKrw: 300_000, keyMoneyKrw: 10_000_000, rentableAreaSqm: 33.1,
  floor: '1층', notes: null, warnings: [], createdAt: '2026-07-21', updatedAt: '2026-07-21',
  ...patch,
})

describe('finance model', () => {
  it('converts 만원 inputs into integer won values', () => {
    expect(manwonToKrw('5,000')).toBe(50_000_000)
    expect(manwonToKrw('200')).toBe(2_000_000)
    expect(manwonToKrw('1.25')).toBe(12_500)
    expect(() => manwonToKrw('invalid')).toThrow('금액은 0 이상의 숫자')
    expect(() => manwonToKrw('1.2.3')).toThrow('금액은 0 이상의 숫자')
    expect(() => manwonToKrw('')).toThrow('금액은 0 이상의 숫자')
  })

  it('rejects malformed lease money instead of saving it as zero', () => {
    expect(isManwonInput('1.2')).toBe(true)
    expect(isManwonInput('1.2.3')).toBe(false)
    const draft = emptyLeaseDraft()
    draft.address = '서울시 중구'
    draft.money.deposit = '1.2.3'
    draft.money.monthlyRent = '200'
    expect(validateLeaseDraft(draft)).toBe('보증금 금액은 0 이상의 숫자로 입력해주세요.')
    const area = {
      area_code: 'A1', area_name: '테스트상권', industry_code: 'CS100001', industry_name: '한식',
    } as Parameters<typeof candidateFromDraft>[1]
    expect(() => candidateFromDraft(draft, area)).toThrow('보증금 금액은 0 이상의 숫자')
  })

  it('validates malformed optional money fields when they are present', () => {
    const draft = emptyLeaseDraft()
    draft.address = '서울시 중구'
    draft.money.deposit = '5000'
    draft.money.monthlyRent = '200'
    draft.money.managementFee = '.'
    expect(validateLeaseDraft(draft)).toBe('월 관리비 금액은 0 이상의 숫자로 입력해주세요.')
  })

  it('does not merge a finance plan into inputs changed while the request was pending', () => {
    const selected = candidate()
    const requestedState = emptyFinanceState()
    requestedState.additionalCosts.interior_krw = 10_000_000
    const requested = buildFinancePlanRequest(selected, requestedState)
    const plan = { disclosure: '테스트 계획' } as NonNullable<LeaseCandidateFinanceState['plan']>

    expect(mergeFinancePlanIfCurrent(requested, selected, requestedState, plan)).toEqual({
      ...requestedState,
      plan,
    })

    const editedState = {
      ...requestedState,
      additionalCosts: { ...requestedState.additionalCosts, interior_krw: 20_000_000 },
    }
    expect(mergeFinancePlanIfCurrent(requested, selected, editedState, plan)).toBeNull()
    expect(editedState.additionalCosts.interior_krw).toBe(20_000_000)

    const editedCandidate = candidate({ depositKrw: selected.depositKrw + 10_000_000 })
    expect(mergeFinancePlanIfCurrent(requested, editedCandidate, requestedState, plan)).toBeNull()
  })

  it('does not calculate or finance a candidate with unknown costs', () => {
    const incomplete = candidate({ managementFeeKrw: null })
    expect(candidateMissingCosts(incomplete)).toEqual(['관리비'])
    expect(firstYearLeaseCash(incomplete)).toBeNull()
    expect(() => buildFinancePlanRequest(incomplete, emptyFinanceState())).toThrow('관리비와 권리금')
  })

  it('keeps a selected lease candidate only within its own area', () => {
    const candidates = [candidate({ id: 'listing-a', areaCode: 'A1' }), candidate({ id: 'listing-b', areaCode: 'B1' })]
    expect(leaseSelectionForArea(candidates, 'listing-a', 'A1')).toBe('listing-a')
    expect(leaseSelectionForArea(candidates, 'listing-a', 'B1')).toBeNull()
    expect(leaseSelectionForArea(candidates, 'missing', 'A1')).toBeNull()
    expect(leaseSelectionForArea(candidates, 'listing-a', null)).toBeNull()
  })

  it('calculates comparison cash and builds the selected candidate request', () => {
    const complete = candidate()
    const state = emptyFinanceState()
    state.eligibility.own_capital_krw = 60_000_000
    state.eligibility.has_miso_good_repayment_history = true
    expect(firstYearLeaseCash(complete)).toBe(87_600_000)
    const request = buildFinancePlanRequest(complete, state)
    expect(request.candidate.deposit_krw).toBe(50_000_000)
    expect(request.eligibility.own_capital_krw).toBe(60_000_000)
    expect(request.eligibility.has_miso_good_repayment_history).toBe(true)
    expect(formatKrw(150_000_000)).toBe('1.5억원')
  })

  it('creates manual candidates and preserves legacy source metadata when edited', () => {
    const draft = emptyLeaseDraft()
    draft.address = '서울시 중구'
    draft.money.deposit = '5000'
    draft.money.monthlyRent = '200'
    const area = {
      area_code: 'A1', area_name: '테스트상권', industry_code: 'CS100001', industry_name: '한식',
    } as Parameters<typeof candidateFromDraft>[1]
    expect(candidateFromDraft(draft, area).sourceKind).toBe('manual')
    const existing = candidate({ sourceUrl: 'https://example.com/listing/1', sourceKind: 'url' })
    expect(candidateFromDraft(draft, area, existing).sourceUrl).toBe(existing.sourceUrl)
    expect(candidateFromDraft(draft, area, existing).sourceKind).toBe('url')
  })
})
