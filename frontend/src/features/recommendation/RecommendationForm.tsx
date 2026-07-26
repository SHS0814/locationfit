import type { FormEvent } from 'react'
import type { MetadataResponse, RecommendationRequest } from '../../types/api'
import { toggleValue } from './model'
import { PerformanceWeightsControl } from './PerformanceWeightsControl'

interface Props {
  metadata: MetadataResponse
  value: RecommendationRequest
  loading: boolean
  onChange: (next: RecommendationRequest) => void
  onSubmit: () => void
}

const importanceFields: Array<{ key: keyof RecommendationRequest; label: string }> = [
  { key: 'floating_population_importance', label: '유동인구' },
  { key: 'resident_population_importance', label: '상주인구' },
  { key: 'worker_population_importance', label: '직장인구' },
  { key: 'weekend_importance', label: '주말 유동' },
  { key: 'apartment_importance', label: '아파트' },
  { key: 'transport_facility_importance', label: '교통시설' },
  { key: 'education_facility_importance', label: '교육시설' },
  { key: 'medical_facility_importance', label: '의료시설' },
  { key: 'shopping_facility_importance', label: '쇼핑시설' },
  { key: 'culture_facility_importance', label: '문화시설' },
]

export function RecommendationForm({ metadata, value, loading, onChange, onSubmit }: Props) {
  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit()
  }

  const update = <K extends keyof RecommendationRequest>(key: K, next: RecommendationRequest[K]) => {
    onChange({ ...value, [key]: next })
  }

  return (
    <form className="recommendation-form" onSubmit={submit}>
      <div className="form-heading">
        <span className="eyebrow">MY BUSINESS FIT</span>
        <h2>어떤 상권을 찾으세요?</h2>
        <p>업종과 고객 조건을 알려주시면 과거 성과와 상권 특성을 함께 비교합니다.</p>
      </div>

      <label className="field-label" htmlFor="industry">업종</label>
      <select id="industry" value={value.industry_code} onChange={(e) => update('industry_code', e.target.value)} required>
        <option value="">업종을 선택하세요</option>
        {metadata.industries.map((option) => <option key={option.code} value={option.code}>{option.name}</option>)}
      </select>

      <div className="two-columns">
        <label>
          <span className="field-label">선호 자치구</span>
          <select value={value.preferred_districts[0] || ''} onChange={(e) => update('preferred_districts', e.target.value ? [e.target.value] : [])}>
            <option value="">서울 전체</option>
            {metadata.districts.map((district) => <option key={district}>{district}</option>)}
          </select>
        </label>
        <label>
          <span className="field-label">결과 개수</span>
          <select value={value.top_n} onChange={(e) => update('top_n', Number(e.target.value))}>
            {[5, 10, 15, 20].map((count) => <option key={count} value={count}>{count}개</option>)}
          </select>
        </label>
      </div>

      <PerformanceWeightsControl
        metadata={metadata}
        value={value.performance_group_weights}
        onChange={(weights) => update('performance_group_weights', weights)}
      />

      <details className="advanced-options">
        <summary>
          고급 설정 <span>선택 입력</span>
        </summary>
        <p className="advanced-description">필요한 조건만 선택하세요. 추천하려면 자치구 또는 고급 조건을 하나 이상 입력해야 합니다.</p>

        <fieldset>
          <legend>상권 유형</legend>
          <div className="chip-group">
            {metadata.area_types.map((option) => (
              <button key={option.code} type="button" className={value.preferred_area_types.includes(option.code) ? 'chip active' : 'chip'}
                onClick={() => update('preferred_area_types', toggleValue(value.preferred_area_types, option.code))}>
                {option.name}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend>주요 고객 연령</legend>
          <div className="chip-group">
            {metadata.age_groups.map((option) => (
              <button key={option.code} type="button" className={value.target_age_groups.includes(option.code) ? 'chip active' : 'chip'}
                onClick={() => update('target_age_groups', toggleValue(value.target_age_groups, option.code))}>
                {option.name}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend>선호 시간대</legend>
          <div className="chip-group">
            {metadata.time_bands.map((option) => (
              <button key={option.code} type="button" className={value.preferred_time_bands.includes(option.code) ? 'chip active' : 'chip'}
                onClick={() => update('preferred_time_bands', toggleValue(value.preferred_time_bands, option.code))}>
                {option.name}
              </button>
            ))}
          </div>
        </fieldset>

        <h3 className="advanced-subheading">상세 중요도</h3>
        <div className="slider-list">
          {importanceFields.map(({ key, label }) => (
            <label className="slider-row" key={key}>
              <span>{label}</span>
              <input type="range" min="0" max="1" step="0.1" value={Number(value[key])}
                onChange={(e) => update(key, Number(e.target.value) as never)} />
              <strong>{Number(value[key]).toFixed(1)}</strong>
            </label>
          ))}
        </div>
      </details>

      <button className="submit-button" disabled={loading} type="submit">
        {loading ? '상권을 분석하고 있어요…' : '내 업종에 맞는 상권 찾기'}
      </button>
    </form>
  )
}
