import { describe, expect, it } from 'vitest'
import { formatBenchmarkDelta, formatReportValue } from './report'

describe('recommendation report formatting', () => {
  it('formats money, percentages, indices, and missing values with explicit units', () => {
    expect(formatReportValue('recent_4q_average_sales', 123456789)).toBe('123,456,789원')
    expect(formatReportValue('estimated_converted_monthly_rent_krw', 3504754.54)).toBe('3,504,755원')
    expect(formatReportValue('unit_converted_rent_krw_sqm', 53000.4)).toBe('53,000원/㎡·월')
    expect(formatReportValue('recent_4q_growth_rate', 0.123)).toBe('12.3%')
    expect(formatReportValue('recent_store_count', 12)).toBe('12개')
    expect(formatReportValue('same_industry_store_density', 56.74)).toBe('56.7개/㎢')
    expect(formatReportValue('floating_population', 12345.6)).toBe('12,346명')
    expect(formatReportValue('closing_rate', null)).toBe('자료 없음')
  })

  it('uses relative differences for amounts and percentage points for rates', () => {
    expect(formatBenchmarkDelta('recent_4q_average_sales', 120, 100)).toBe('중앙값 대비 +20.0%')
    expect(formatBenchmarkDelta('recent_4q_growth_rate', 0.08, 0.05)).toBe('중앙값 대비 +3.0%p')
    expect(formatBenchmarkDelta('recent_store_count', 12, 10)).toBe('중앙값 대비 +20.0%')
    expect(formatBenchmarkDelta('same_industry_store_density', 40, 50)).toBe('중앙값 대비 -20.0%')
    expect(formatBenchmarkDelta('recent_store_count', 3, 0)).toBe('중앙값 대비 +3개')
    expect(formatBenchmarkDelta('closing_rate', null, 0.05)).toBe('비교 불가')
  })
})
