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
  if (metric === 'recent_4q_average_sales') return `${Math.round(value).toLocaleString('ko-KR')}원`
  if (percentMetrics.has(metric)) return `${(value * 100).toFixed(1)}%`
  if (metric === 'competition_intensity') return `${(value * 100).toFixed(1)} / 100`
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
  if (scoreMetrics.has(metric) || metric === 'competition_intensity') {
    const scaled = metric === 'competition_intensity' ? delta * 100 : delta
    return `중앙값 대비 ${scaled >= 0 ? '+' : ''}${scaled.toFixed(1)}점`
  }
  if (percentMetrics.has(metric)) {
    const points = delta * 100
    return `중앙값 대비 ${points >= 0 ? '+' : ''}${points.toFixed(1)}%p`
  }
  if (benchmark === 0) return '중앙값 대비 계산 불가'
  const relative = delta / Math.abs(benchmark) * 100
  return `중앙값 대비 ${relative >= 0 ? '+' : ''}${relative.toFixed(1)}%`
}
