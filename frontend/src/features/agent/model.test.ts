import { describe, expect, it } from 'vitest'
import { draftToRequest, emptyDraft, isDraftReady, restoreSession } from './model'

describe('agent session model', () => {
  it('accepts an industry alone and treats omitted preferences as unrestricted', () => {
    expect(isDraftReady(emptyDraft)).toBe(false)
    expect(isDraftReady({ ...emptyDraft, industry_code: 'CS100001' })).toBe(true)
    expect(isDraftReady({
      ...emptyDraft,
      industry_code: 'CS100001',
      preferred_districts: ['강남구'],
    })).toBe(true)
  })

  it('restores a valid session and falls back from malformed JSON', () => {
    const draft = { ...emptyDraft, industry_code: 'CS100001', target_age_groups: ['20'] }
    const restored = restoreSession(JSON.stringify({
      schemaVersion: 7,
      history: [{ role: 'user', content: '카페를 열고 싶어요' }],
      draft,
      phase: 'ready_for_confirmation',
      items: [],
      comparison: [],
      activeRequest: draftToRequest(draft),
    }))
    expect(restored.draft.industry_code).toBe('CS100001')
    expect(restored.schemaVersion).toBe(7)
    expect(restored.recommendationReport).toBeNull()
    expect(restored.context.discovery_question_count).toBe(0)
    expect(restored.storeRelations).toEqual(['competitor', 'complementary', 'daily_life', 'other'])
    expect(restoreSession('{broken').phase).toBe('discovering')
  })

  it('drops cached recommendation items that predate map boundaries', () => {
    const draft = { ...emptyDraft, industry_code: 'CS100001', target_age_groups: ['20'] }
    const restored = restoreSession(JSON.stringify({
      schemaVersion: 7,
      history: [{ role: 'user', content: '카페를 열고 싶어요' }],
      draft,
      phase: 'results',
      items: [{ area_code: '3110001', area_name: '오래된 결과' }],
      activeRequest: draftToRequest(draft),
    }))
    expect(restored.items).toEqual([])
    expect(restored.activeRequest?.industry_code).toBe('CS100001')
  })

  it('keeps an industry-only draft ready after strategy selection', () => {
    expect(isDraftReady({ ...emptyDraft, industry_code: 'CS100001', strategy: 'growth' })).toBe(true)
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
      floor: 'f1',
    })).toBe(true)
  })

  it('drops legacy property type and unsupported floor values during session migration', () => {
    const restored = restoreSession(JSON.stringify({
      schemaVersion: 5,
      history: [{ role: 'user', content: '기존 조건' }],
      draft: { ...emptyDraft, commercial_property_type: 'small_retail', floor: 'f2' },
      phase: 'results',
    }))
    expect(restored.schemaVersion).toBe(7)
    expect(restored.draft.floor).toBeNull()
    expect('commercial_property_type' in restored.draft).toBe(false)
    expect(restored.phase).toBe('discovering')
  })
})
