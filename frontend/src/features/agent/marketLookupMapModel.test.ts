import { describe, expect, it } from 'vitest'
import type { MarketLookupResult, MarketLookupRow } from '../../types/api'
import { isMappableLookup, marketLookupEntityKey, marketLookupMapCacheKey } from './marketLookupMapModel'

const row: MarketLookupRow = {
  rank: 1,
  entity_code: 'A1',
  entity_name: '테스트 상권',
  metric_value: 100,
  metric_display_value: '100원',
  difference_from_mean: 10,
  difference_from_mean_display: '+10원',
  difference_from_median: 5,
  difference_from_median_display: '+5원',
  standard_deviation_distance: 1,
  district_name: '강남구',
  admin_dong_name: '역삼1동',
  area_count: 1,
  observation_count: 1,
}

function result(groupBy: MarketLookupResult['group_by']): MarketLookupResult {
  return {
    title: '조회',
    group_by: groupBy,
    metric: 'sales',
    metric_label: '매출',
    metric_unit: 'krw',
    order: 'desc',
    filters: {},
    data_period: '2025Q1~2025Q4',
    distribution: {
      population_count: 1,
      mean: 90,
      mean_display: '90원',
      median: 95,
      median_display: '95원',
      standard_deviation: 10,
      standard_deviation_display: '10원',
    },
    rows: [row],
    geographic_basis: '서울시 상권영역',
    disclosure: '설명',
  }
}

describe('market lookup map model', () => {
  it('maps only area and district ranking results', () => {
    expect(isMappableLookup(result('area'))).toBe(true)
    expect(isMappableLookup(result('district'))).toBe(true)
    expect(isMappableLookup(result('industry'))).toBe(false)
    expect(isMappableLookup(result('admin_dong'))).toBe(false)
  })

  it('uses area codes and district names as stable geography keys', () => {
    expect(marketLookupEntityKey(result('area'), row)).toBe('A1')
    expect(marketLookupEntityKey(result('district'), row)).toBe('테스트 상권')
    expect(marketLookupMapCacheKey(result('area'))).toBe('area:A1')
    expect(marketLookupMapCacheKey(result('industry'))).toBeNull()
  })

})
