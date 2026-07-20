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
    expect(restored.schemaVersion).toBe(3)
    expect(restored.recommendationReport).toBeNull()
    expect(restored.context.discovery_question_count).toBe(0)
    expect(restoreSession('{broken').phase).toBe('discovering')
  })

  it('does not treat a strategy selection as a location preference', () => {
    expect(isDraftReady({ ...emptyDraft, industry_code: 'CS100001', strategy: 'growth' })).toBe(false)
  })
})
