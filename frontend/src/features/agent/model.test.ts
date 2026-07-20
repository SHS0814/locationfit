import { describe, expect, it } from 'vitest'
import { draftToRequest, emptyDraft, isDraftReady, restoreSession } from './model'

describe('agent session model', () => {
  it('requires an industry and at least one preference before confirmation', () => {
    expect(isDraftReady(emptyDraft)).toBe(false)
    expect(isDraftReady({ ...emptyDraft, industry_code: 'CS100001' })).toBe(false)
    expect(isDraftReady({
      ...emptyDraft,
      industry_code: 'CS100001',
      preferred_districts: ['강남구'],
    })).toBe(true)
  })

  it('restores a valid session and falls back from malformed JSON', () => {
    const draft = { ...emptyDraft, industry_code: 'CS100001', target_age_groups: ['20'] }
    const restored = restoreSession(JSON.stringify({
      history: [{ role: 'user', content: '카페를 열고 싶어요' }],
      draft,
      phase: 'ready_for_confirmation',
      items: [],
      comparison: [],
      activeRequest: draftToRequest(draft),
    }))
    expect(restored.draft.industry_code).toBe('CS100001')
    expect(restored.schemaVersion).toBe(4)
    expect(restored.recommendationReport).toBeNull()
    expect(restored.context.discovery_question_count).toBe(0)
    expect(restoreSession('{broken').phase).toBe('discovering')
  })

  it('does not treat a strategy selection as a location preference', () => {
    expect(isDraftReady({ ...emptyDraft, industry_code: 'CS100001', strategy: 'growth' })).toBe(false)
  })

  it('requires complete rent conditions only when a monthly cap is used', () => {
    const base = { ...emptyDraft, industry_code: 'CS100001', preferred_districts: ['강남구'] }
    expect(isDraftReady({ ...base, total_startup_budget_krw: 100_000_000 })).toBe(true)
    expect(isDraftReady({ ...base, monthly_converted_rent_limit_krw: 4_000_000 })).toBe(false)
    expect(isDraftReady({ ...base, rentable_area_sqm: 66 })).toBe(false)
    expect(isDraftReady({
      ...base,
      monthly_converted_rent_limit_krw: 4_000_000,
      rentable_area_sqm: 66,
      commercial_property_type: 'medium_large_retail',
      floor: 'f1',
    })).toBe(true)
  })
})
