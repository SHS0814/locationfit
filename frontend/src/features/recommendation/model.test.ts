import { describe, expect, it } from 'vitest'
import { emptyRecommendationRequest, hasPreference, toggleValue } from './model'

describe('recommendation form model', () => {
  it('requires at least one preference in addition to the industry', () => {
    expect(hasPreference({ ...emptyRecommendationRequest, industry_code: 'CS100001' })).toBe(false)
    expect(hasPreference({ ...emptyRecommendationRequest, industry_code: 'CS100001', target_age_groups: ['20'] })).toBe(true)
  })

  it('toggles multi-select values', () => {
    expect(toggleValue(['A'], 'D')).toEqual(['A', 'D'])
    expect(toggleValue(['A', 'D'], 'A')).toEqual(['D'])
  })
})
