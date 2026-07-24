import { useEffect, useState } from 'react'
import type { MarketLookupResult } from '../../types/api'

interface Props {
  result: MarketLookupResult
  position: number
  total: number
  onPrevious: () => void
  onNext: () => void
}

export function MarketLookupCard({ result, position, total, onPrevious, onNext }: Props) {
  const [open, setOpen] = useState(true)

  useEffect(() => setOpen(true), [result])

  return (
    <details className="lookup-drawer" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary><span>일반 조회 결과</span><small>{total}개 보관</small></summary>
      <section className="lookup-card" aria-label="상권 통계 조회 결과">
        <div className="section-title">
          <span>바로 조회</span>
          <div className="lookup-history-controls" aria-label="조회 결과 이력">
            <small>{position + 1} / {total}</small>
            <button type="button" onClick={onPrevious} disabled={position <= 0} aria-label="이전 조회 결과">←</button>
            <button type="button" onClick={onNext} disabled={position >= total - 1} aria-label="다음 조회 결과">→</button>
          </div>
        </div>
        <h3>{result.title}</h3>
        <small className="lookup-period">{result.data_period}</small>
        {Object.keys(result.filters).length > 0 && (
          <p className="lookup-filters">조회 조건 · {Object.values(result.filters).filter((value, index, values) => values.indexOf(value) === index).join(' · ')}</p>
        )}
        <dl className="lookup-distribution">
          <div><dt>평균</dt><dd>{result.distribution.mean_display}</dd></div>
          <div><dt>중앙값</dt><dd>{result.distribution.median_display}</dd></div>
          <div><dt>표준편차</dt><dd>{result.distribution.standard_deviation_display}</dd></div>
        </dl>
        <p className="lookup-population">필터 적용 후 전체 {result.distribution.population_count.toLocaleString('ko-KR')}개 대상 기준</p>
        <ol>
          {result.rows.map((row) => (
            <li key={`${row.rank}-${row.entity_code || row.entity_name}-${row.district_name || ''}`}>
              <b>{row.rank}</b>
              <span>
                <strong>{row.entity_name}</strong>
                <small>{[
                  row.district_name,
                  row.admin_dong_name,
                  row.area_count > 1 ? `관측 상권 ${row.area_count}곳` : null,
                ].filter(Boolean).join(' · ')}</small>
                <small>평균 대비 {row.difference_from_mean_display} · 중앙값 대비 {row.difference_from_median_display} · {formatSigma(row.standard_deviation_distance)}</small>
              </span>
              <em>{row.metric_display_value}</em>
            </li>
          ))}
        </ol>
        <small>{result.disclosure}</small>
      </section>
    </details>
  )
}

function formatSigma(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `평균에서 ${sign}${value.toFixed(2)}σ`
}
