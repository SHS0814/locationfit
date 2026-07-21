import type { RecommendationItem } from '../../types/api'

interface Props {
  items: RecommendationItem[]
  selectedCode: string | null
  onSelect: (item: RecommendationItem) => void
}

export function RecommendationResults({ items, selectedCode, onSelect }: Props) {
  return (
    <section className="results-panel" aria-label="추천 결과">
      <div className="results-heading">
        <div>
          <span className="eyebrow">RECOMMENDED AREAS</span>
          <h2>추천 상권 {items.length}곳</h2>
        </div>
        <p>{items.some((item) => item.budget_adjusted) ? '기존 종합점수 80% · 예산 적합도 20%' : '조건 적합도 60% · 과거 성과 40%'}</p>
      </div>
      <div className="result-list">
        {items.map((item) => (
          <button key={item.area_code} className={selectedCode === item.area_code ? 'result-card selected' : 'result-card'} onClick={() => onSelect(item)}>
            <span className="rank">{item.rank}</span>
            <div className="result-main">
              <div className="result-title">
                <h3>{item.area_name}</h3>
                <span className={`grade grade-${item.reliability_grade.toLowerCase()}`}>{item.reliability_grade}등급</span>
              </div>
              <p>{item.district_name} · {item.admin_dong_name || item.area_type}</p>
              <div className="reason-row">
                {item.positive_reasons.slice(0, 2).map((reason) => <span key={`${reason.factor}-${reason.feature}`}>✓ {reason.factor}</span>)}
              </div>
              {item.rental_estimate && (
                <p className="rent-summary">
                  환산 월 {formatWon(item.rental_estimate.estimated_converted_monthly_rent_krw)}
                  {' · '}{item.rental_estimate.rent_basis_name} · {item.rental_estimate.rent_basis_geography === 'district' ? '자치구' : '행정동'} 기준 · {floorName(item.rental_estimate.rent_basis_floor)}
                  {item.rental_estimate.fallback_used && ' (전체 층 평균 대체)'}
                  {item.rental_estimate.geography_fallback_used && ' (자치구 기준 대체)'}
                </p>
              )}
              {item.budget_fit_score != null && <span className="budget-fit">예산 적합 {item.budget_fit_score.toFixed(1)}점</span>}
              {item.warnings.length > 0 && <p className="warning">{item.warnings[0]}</p>}
            </div>
            <div className="score">
              <strong>{item.final_score.toFixed(1)}</strong>
              <span>종합점수</span>
            </div>
          </button>
        ))}
      </div>
    </section>
  )
}

function formatWon(value: number): string {
  return `${Math.round(value).toLocaleString('ko-KR')}원`
}

function floorName(floor: 'all' | 'f1' | 'non_f1'): string {
  return floor === 'all' ? '전체 층 평균' : floor === 'f1' ? '1층' : '1층 외'
}
