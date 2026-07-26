import { useState } from 'react'
import type {
  MetadataResponse,
  PerformanceGroupWeights,
  PerformanceWeightPreset,
} from '../../types/api'
import {
  normalizePerformanceWeights,
  performanceGroups,
  updatePerformanceWeight,
} from './performanceWeights'

interface Props {
  metadata: MetadataResponse
  value: PerformanceGroupWeights | null
  onChange: (weights: PerformanceGroupWeights) => void
}

const presetLabels: Record<PerformanceWeightPreset, string> = {
  balanced: '균형형',
  growth_focused: '성장 중심',
  stability_focused: '안정성 중심',
}

function sameWeights(left: PerformanceGroupWeights, right: PerformanceGroupWeights): boolean {
  return performanceGroups.every(({ key }) => Math.abs(left[key] - right[key]) < 1e-8)
}

export function PerformanceWeightsControl({ metadata, value, onChange }: Props) {
  const [manualMode, setManualMode] = useState(false)
  const balanced = metadata.performance_weight_presets.balanced
  const normalized = normalizePerformanceWeights(value || balanced) || balanced
  const matchingPreset = (Object.keys(presetLabels) as PerformanceWeightPreset[])
    .find((preset) => sameWeights(normalized, metadata.performance_weight_presets[preset]))
  const direct = manualMode || (value != null && matchingPreset == null)
  const activePreset = direct ? undefined : matchingPreset

  return (
    <fieldset className="performance-weights">
      <legend>성과 평가 기준</legend>
      <div className="performance-presets" aria-label="성과 평가 프리셋">
        {(Object.keys(presetLabels) as PerformanceWeightPreset[]).map((preset) => (
          <button
            key={preset}
            type="button"
            className={activePreset === preset ? 'active' : ''}
            aria-pressed={activePreset === preset}
            onClick={() => {
              setManualMode(false)
              onChange({ ...metadata.performance_weight_presets[preset] })
            }}
          >
            {presetLabels[preset]}
          </button>
        ))}
        <button type="button" className={direct ? 'active' : ''} aria-pressed={direct} onClick={() => {
          setManualMode(true)
          onChange({ ...normalized })
        }}>
          직접 설정
        </button>
      </div>
      <div className="performance-weight-list">
        {performanceGroups.map(({ key, label }) => {
          const percent = normalized[key] * 100
          return (
            <label className="performance-weight-row" key={key}>
              <span>{label}</span>
              <input
                type="range"
                min="0"
                max="100"
                step="0.1"
                value={percent}
                aria-label={`${label} 비중`}
                onChange={(event) => {
                  setManualMode(true)
                  onChange(updatePerformanceWeight(normalized, key, Number(event.target.value)))
                }}
              />
              <span className="performance-number"><input
                type="number"
                min="0"
                max="100"
                step="0.1"
                value={Number(percent.toFixed(1))}
                aria-label={`${label} 비중 숫자 입력`}
                onChange={(event) => {
                  setManualMode(true)
                  onChange(updatePerformanceWeight(normalized, key, Number(event.target.value)))
                }}
              /><b>%</b></span>
            </label>
          )
        })}
      </div>
      <output className="performance-total">합계: 100%</output>
    </fieldset>
  )
}
