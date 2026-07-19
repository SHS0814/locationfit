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
        <p>조건 적합도 60% · 과거 성과 40%</p>
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
