import { describe, expect, it } from 'vitest'
import type { StorePoint } from '../../types/api'
import { filterStores } from './model'

const store = (overrides: Partial<StorePoint>): StorePoint => ({
  store_id: 'A', name: '테스트 카페', branch_name: null,
  industry_large_code: null, industry_large_name: '음식',
  industry_middle_code: null, industry_middle_name: '음료',
  industry_small_code: null, industry_small_name: '커피 전문점',
  ksic_code: null, ksic_name: null, road_address: '서울특별시 강남구 테스트로 1',
  lot_address: null, building_name: null, building_management_number: null,
  floor: null, unit: null, longitude: 127, latitude: 37.5,
  relation: 'competitor',
  ...overrides,
})

describe('store explorer filtering', () => {
  it('filters by deterministic relation and Korean search text', () => {
    const stores = [
      store({ store_id: 'A' }),
      store({ store_id: 'B', name: '생활 편의점', relation: 'daily_life', industry_small_name: '편의점' }),
    ]
    expect(filterStores(stores, ['competitor'], '')).toHaveLength(1)
    expect(filterStores(stores, ['competitor', 'daily_life'], '강남구').map((item) => item.store_id)).toEqual(['A', 'B'])
    expect(filterStores(stores, ['competitor', 'daily_life'], '편의점').map((item) => item.store_id)).toEqual(['B'])
  })
})
