import type {
  RecommendationReport,
  RecommendationReportMetricKey,
} from '../../types/api'
import { formatBenchmarkDelta, formatReportValue } from './report'

interface Props {
  report: RecommendationReport
}

const metricRows: Array<{ key: RecommendationReportMetricKey; label: string; note: string }> = [
  { key: 'recent_4q_average_sales', label: '최근 4분기 평균 매출', note: '분기 평균 관측 매출' },
  { key: 'recent_4q_growth_rate', label: '최근 4분기 성장률', note: '직전 4분기 대비' },
  { key: 'recent_store_count', label: '동종업종 점포 수', note: '최신 관측 분기 실제 점포' },
  { key: 'same_industry_store_density', label: '동종업종 점포 밀도', note: '상권 면적 1㎢당 점포' },
  { key: 'closing_rate', label: '폐업률', note: '낮을수록 안정적' },
  { key: 'floating_population', label: '유동인구', note: '최근 4분기 평균' },
  { key: 'resident_population', label: '상주인구', note: '최근 4분기 평균' },
  { key: 'worker_population', label: '직장인구', note: '최근 4분기 평균' },
]

const rentMetricRows: Array<{ key: RecommendationReportMetricKey; label: string; note: string }> = [
  { key: 'estimated_converted_monthly_rent_krw', label: '예상 월 환산임대료', note: '입력한 임대면적 기준 · 관리비/VAT 제외' },
  { key: 'unit_converted_rent_krw_sqm', label: '㎡당 월 환산임대료', note: '한국부동산원 인근 표본상권 기준' },
]

export function RecommendationReportView({ report }: Props) {
  const visibleMetrics = report.areas.some((area) => area.rental_estimate)
    ? [...metricRows, ...rentMetricRows]
    : metricRows
  return (
    <section className="recommendation-report" aria-labelledby="recommendation-report-title">
      <header className="report-heading">
        <div>
          <span className="eyebrow">DATA-BACKED REPORT</span>
          <h2 id="recommendation-report-title">상권 비교 분석 보고서</h2>
        </div>
        <p>동일 조건의 유효 후보 {report.candidate_count.toLocaleString('ko-KR')}곳 중앙값과 비교했습니다.</p>
      </header>

      <div className="report-area-grid">
        {report.areas.map((area) => (
          <article className="report-area-card" key={area.area_code}>
            <div className="report-area-title">
              <span>{area.rank}위</span>
              <div><h3>{area.area_name}</h3><p>{area.district_name} · {area.area_type}</p></div>
              <b>{area.reliability_grade}등급</b>
            </div>
            <dl className="report-score-grid">
              <div><dt>종합점수</dt><dd>{formatReportValue('final_score', area.metrics.final_score)}</dd></div>
              <div><dt>조건 적합</dt><dd>{formatReportValue('condition_fit_score', area.metrics.condition_fit_score)}</dd></div>
              <div><dt>과거 성과</dt><dd>{formatReportValue('reliability_adjusted_evidence_score', area.metrics.reliability_adjusted_evidence_score)}</dd></div>
              <div><dt>데이터 신뢰도</dt><dd>{formatReportValue('data_reliability', area.metrics.data_reliability)}</dd></div>
            </dl>
            {area.rental_estimate && (
              <p className="report-rent">
                환산 월 임대료 {Math.round(area.rental_estimate.estimated_converted_monthly_rent_krw).toLocaleString('ko-KR')}원
                {area.budget_fit_score != null && ` · 예산 적합 ${area.budget_fit_score.toFixed(1)}점`}
                <small>{area.rental_estimate.survey_area_name} 표본상권 {area.rental_estimate.survey_area_distance_km.toFixed(1)}km · {area.rental_estimate.reference_period}</small>
              </p>
            )}
            {area.positive_reasons.length > 0 && (
              <p className="report-reason positive">
                강점 · {area.positive_reasons.slice(0, 2).map((reason) => `${reason.factor} ${reason.fit_score.toFixed(1)}점`).join(', ')}
              </p>
            )}
            {area.negative_reasons.length > 0 && (
              <p className="report-reason negative">
                확인 · {area.negative_reasons.slice(0, 2).map((reason) => `${reason.factor} ${reason.fit_score.toFixed(1)}점`).join(', ')}
              </p>
            )}
          </article>
        ))}
      </div>

      <div className="report-table-wrap">
        <table className="report-table">
          <caption>추천 상권별 관측 지표와 동일 조건 후보 중앙값</caption>
          <thead>
            <tr>
              <th scope="col">비교 지표</th>
              {report.areas.map((area) => <th scope="col" key={area.area_code}>{area.rank}위 {area.area_name}</th>)}
              <th scope="col">{report.benchmark_label}</th>
            </tr>
          </thead>
          <tbody>
            {visibleMetrics.map(({ key, label, note }) => (
              <tr key={key}>
                <th scope="row"><strong>{label}</strong><small>{note}</small></th>
                {report.areas.map((area) => (
                  <td key={area.area_code}>
                    <strong>{formatReportValue(key, area.metrics[key])}</strong>
                    <small>{formatBenchmarkDelta(key, area.metrics[key], report.benchmark[key])}</small>
                  </td>
                ))}
                <td className="benchmark-cell"><strong>{formatReportValue(key, report.benchmark[key])}</strong><small>기준값</small></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className={report.rental_estimate_uses_default ? 'report-rent-basis default' : 'report-rent-basis'}>
        임대료 산정 기준 · {report.rental_estimate_basis}
        {report.rental_estimate_uses_default && ' · 임대조건을 입력하면 해당 조건으로 다시 계산됩니다.'}
      </p>

      {report.areas.some((area) => area.warnings.length > 0) && (
        <div className="report-warnings">
          <strong>데이터 확인사항</strong>
          {report.areas.flatMap((area) => area.warnings.map((warning) => (
            <p key={`${area.area_code}-${warning}`}>{area.area_name} · {warning}</p>
          )))}
        </div>
      )}
      <footer className="report-footnote">
        경쟁 점포 {report.competition_reference_period} 기준 · 구조 지표 {report.data_period.profile || '-'} · 업종 과거 성과 {report.data_period.performance || '-'} · 관측 데이터 기반이며 미래 매출을 보장하지 않습니다.
      </footer>
    </section>
  )
}
