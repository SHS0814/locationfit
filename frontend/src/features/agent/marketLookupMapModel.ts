import type { MarketLookupResult, MarketLookupRow } from '../../types/api'

export function isMappableLookup(result: MarketLookupResult): result is MarketLookupResult & { group_by: 'area' | 'district' } {
  return result.group_by === 'area' || result.group_by === 'district'
}

export function marketLookupEntityKey(result: MarketLookupResult, row: MarketLookupRow): string | null {
  if (result.group_by === 'area') return row.entity_code
  if (result.group_by === 'district') return row.entity_name
  return null
}

export function marketLookupMapCacheKey(result: MarketLookupResult): string | null {
  if (!isMappableLookup(result)) return null
  return `${result.group_by}:${result.rows.map((row) => marketLookupEntityKey(result, row)).join(',')}`
}
