import type { StorePoint, StoreRelation } from '../../types/api'


export function filterStores(stores: StorePoint[], relations: StoreRelation[], search: string): StorePoint[] {
  const normalisedSearch = search.trim().toLocaleLowerCase('ko-KR')
  return stores.filter((store) => {
    if (!relations.includes(store.relation)) return false
    if (!normalisedSearch) return true
    return [store.name, store.branch_name, store.industry_small_name, store.industry_middle_name, store.road_address]
      .some((value) => value?.toLocaleLowerCase('ko-KR').includes(normalisedSearch))
  })
}
