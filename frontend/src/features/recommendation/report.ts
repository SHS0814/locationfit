import type { RecommendationReportMetricKey } from '../../types/api'

const percentMetrics = new Set<RecommendationReportMetricKey>([
  'recent_4q_growth_rate',
  'closing_rate',
  'data_reliability',
])
const scoreMetrics = new Set<RecommendationReportMetricKey>([
  'final_score',
  'condition_fit_score',
  'reliability_adjusted_evidence_score',
])
const populationMetrics = new Set<RecommendationReportMetricKey>([
  'floating_population',
  'resident_population',
  'worker_population',
])

export function formatReportValue(metric: RecommendationReportMetricKey, value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '자료 없음'
  if (scoreMetrics.has(metric)) return `${value.toFixed(1)}점`
  if (metric === 'recent_4q_average_sales' || metric === 'estimated_converted_monthly_rent_krw') {
    return `${Math.round(value).toLocaleString('ko-KR')}원`
  }
  if (metric === 'unit_converted_rent_krw_sqm') {
    return `${Math.round(value).toLocaleString('ko-KR')}원/㎡·월`
  }
  if (percentMetrics.has(metric)) return `${(value * 100).toFixed(1)}%`
  if (metric === 'recent_store_count') return `${Math.round(value).toLocaleString('ko-KR')}개`
  if (metric === 'same_industry_store_density') return `${value.toLocaleString('ko-KR', { maximumFractionDigits: 1, minimumFractionDigits: 1 })}개/㎢`
  if (populationMetrics.has(metric)) return `${Math.round(value).toLocaleString('ko-KR')}명`
  return value.toLocaleString('ko-KR')
}

export function formatBenchmarkDelta(
  metric: RecommendationReportMetricKey,
  value: number | null,
  benchmark: number | null,
): string {
  if (value == null || benchmark == null || !Number.isFinite(value) || !Number.isFinite(benchmark)) return '비교 불가'
  const delta = value - benchmark
  if (Math.abs(delta) < 1e-12) return '중앙값과 같음'
  if (scoreMetrics.has(metric)) {
    return `중앙값 대비 ${delta >= 0 ? '+' : ''}${delta.toFixed(1)}점`
  }
  if (percentMetrics.has(metric)) {
    const points = delta * 100
    return `중앙값 대비 ${points >= 0 ? '+' : ''}${points.toFixed(1)}%p`
  }
  if (benchmark === 0) {
    if (metric === 'recent_store_count') return `중앙값 대비 ${delta >= 0 ? '+' : ''}${Math.round(delta)}개`
    if (metric === 'same_industry_store_density') return `중앙값 대비 ${delta >= 0 ? '+' : ''}${delta.toFixed(1)}개/㎢`
    return '중앙값 대비 계산 불가'
  }
  const relative = delta / Math.abs(benchmark) * 100
  return `중앙값 대비 ${relative >= 0 ? '+' : ''}${relative.toFixed(1)}%`
}
