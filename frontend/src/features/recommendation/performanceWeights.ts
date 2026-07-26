import type { PerformanceGroupKey, PerformanceGroupWeights } from '../../types/api'

export const performanceGroups: Array<{ key: PerformanceGroupKey; label: string }> = [
  { key: 'scale_productivity', label: '규모·생산성' },
  { key: 'growth', label: '성장성' },
  { key: 'stability', label: '안정성' },
  { key: 'competition', label: '경쟁 여건' },
  { key: 'closure_risk', label: '폐업 위험' },
]

export function normalizePerformanceWeights(weights: PerformanceGroupWeights): PerformanceGroupWeights | null {
  const values = performanceGroups.map(({ key }) => weights[key])
  if (values.some((value) => !Number.isFinite(value) || value < 0)) return null
  const total = values.reduce((sum, value) => sum + value, 0)
  if (total <= 0) return null
  return Object.fromEntries(
    performanceGroups.map(({ key }) => [key, weights[key] / total]),
  ) as PerformanceGroupWeights
}

export function updatePerformanceWeight(
  weights: PerformanceGroupWeights,
  key: PerformanceGroupKey,
  percent: number,
): PerformanceGroupWeights {
  const current = normalizePerformanceWeights(weights)
  if (!current) return weights
  const target = Math.min(100, Math.max(0, Number.isFinite(percent) ? percent : 0)) / 100
  const otherKeys = performanceGroups.map((group) => group.key).filter((groupKey) => groupKey !== key)
  const otherTotal = otherKeys.reduce((sum, groupKey) => sum + current[groupKey], 0)
  const remaining = 1 - target
  const next = { ...current, [key]: target }
  for (const otherKey of otherKeys) {
    next[otherKey] = otherTotal > 0
      ? current[otherKey] / otherTotal * remaining
      : remaining / otherKeys.length
  }
  return next
}

export function performanceContributionSummary(
  breakdown: Record<PerformanceGroupKey, { score: number | null; contribution: number; available: boolean }>,
): string {
  const available = performanceGroups
    .filter(({ key }) => breakdown[key]?.available)
    .sort((left, right) => breakdown[right.key].contribution - breakdown[left.key].contribution)
  if (!available.length) return '가용한 성과 그룹이 없습니다.'
  const top = available[0]
  return `${top.label} ${breakdown[top.key].score?.toFixed(1) ?? '-'}점이 원시 업종 성과점수에 ${breakdown[top.key].contribution.toFixed(1)}점을 기여했습니다.`
}
