import { describe, expect, it } from 'vitest'
import type { LeaseCandidateExtractResponse } from '../../types/api'
import {
  buildFinancePlanRequest, candidateMissingCosts, draftFromExtraction, emptyFinanceState,
  emptyLeaseDraft, firstYearLeaseCash, formatKrw, hasDuplicateSourceUrl, manwonToKrw,
  validateLeaseDraft, type LeaseCandidateRecord,
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
    expect(manwonToKrw('invalid')).toBe(0)
  })

  it('keeps missing management fee distinct from zero', () => {
    const response: LeaseCandidateExtractResponse = {
      request_id: 'r1', source_url: null, source_kind: 'text', requires_confirmation: true, warnings: [],
      extracted: {
        listing_title: '테스트 매물', address: '서울시 중구', deposit_krw: 50_000_000,
        monthly_rent_krw: 2_000_000, management_fee_krw: null, key_money_krw: 0,
        rentable_area_sqm: 33.1, floor: '1층', notes: null, missing_fields: ['management_fee_krw'],
      },
    }
    const draft = draftFromExtraction(response, emptyLeaseDraft())
    expect(draft.money.deposit).toBe('5000')
    expect(draft.money.managementFee).toBe('')
    expect(draft.money.keyMoney).toBe('0')
  })

  it('does not calculate or finance a candidate with unknown costs', () => {
    const incomplete = candidate({ managementFeeKrw: null })
    expect(candidateMissingCosts(incomplete)).toEqual(['관리비'])
    expect(firstYearLeaseCash(incomplete)).toBeNull()
    expect(() => buildFinancePlanRequest(incomplete, emptyFinanceState())).toThrow('관리비와 권리금')
  })

  it('calculates comparison cash and builds the selected candidate request', () => {
    const complete = candidate()
    const state = emptyFinanceState()
    state.eligibility.own_capital_krw = 60_000_000
    expect(firstYearLeaseCash(complete)).toBe(87_600_000)
    const request = buildFinancePlanRequest(complete, state)
    expect(request.candidate.deposit_krw).toBe(50_000_000)
    expect(request.eligibility.own_capital_krw).toBe(60_000_000)
    expect(formatKrw(150_000_000)).toBe('1.5억원')
  })

  it('validates source URLs and detects duplicates only inside the same area', () => {
    const draft = emptyLeaseDraft()
    draft.sourceUrl = 'javascript:alert(1)'
    expect(validateLeaseDraft(draft)).toContain('http 또는 https')
    const existing = candidate({ sourceUrl: 'https://example.com/listing/1/' })
    expect(hasDuplicateSourceUrl([existing], candidate({ id: 'listing-2', sourceUrl: 'https://example.com/listing/1#detail' }))).toBe(true)
    expect(hasDuplicateSourceUrl([existing], candidate({ id: 'listing-2', areaCode: 'A2', sourceUrl: 'https://example.com/listing/1' }))).toBe(false)
  })
})
