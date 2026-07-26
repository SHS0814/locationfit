import { describe, expect, it } from 'vitest'
import {
  normalizePerformanceWeights,
  performanceContributionSummary,
  updatePerformanceWeight,
} from './performanceWeights'

const balanced = {
  scale_productivity: 0.35,
  growth: 0.27,
  stability: 0.18,
  competition: 0.08,
  closure_risk: 0.12,
}

describe('performance weights', () => {
  it('normalizes percentages and rejects all-zero values', () => {
    expect(normalizePerformanceWeights({
      scale_productivity: 20,
      growth: 40,
      stability: 20,
      competition: 5,
      closure_risk: 15,
    })).toEqual({
      scale_productivity: 0.2,
      growth: 0.4,
      stability: 0.2,
      competition: 0.05,
      closure_risk: 0.15,
    })
    expect(normalizePerformanceWeights({
      scale_productivity: 0, growth: 0, stability: 0, competition: 0, closure_risk: 0,
    })).toBeNull()
  })

  it('changes one value and proportionally adjusts the others to 100%', () => {
    const changed = updatePerformanceWeight(balanced, 'growth', 50)
    expect(changed.growth).toBe(0.5)
    expect(Object.values(changed).reduce((sum, value) => sum + value, 0)).toBeCloseTo(1)
    expect(changed.scale_productivity / changed.stability).toBeCloseTo(0.35 / 0.18)
  })

  it('formats the highest deterministic contribution without color-only meaning', () => {
    const group = (score: number, contribution: number) => ({ score, contribution, available: true })
    expect(performanceContributionSummary({
      scale_productivity: group(72, 14.4),
      growth: group(91, 36.4),
      stability: group(65, 13),
      competition: group(48, 2.4),
      closure_risk: group(80, 12),
    })).toContain('성장성 91.0점')
  })
})
