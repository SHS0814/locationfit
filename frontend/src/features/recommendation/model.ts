import type { RecommendationRequest } from '../../types/api'

export const emptyRecommendationRequest: RecommendationRequest = {
  industry_code: '',
  preferred_area_types: [],
  target_gender: null,
  target_age_groups: [],
  preferred_time_bands: [],
  weekend_importance: 0,
  floating_population_importance: 0,
  resident_population_importance: 0,
  worker_population_importance: 0,
  apartment_importance: 0,
  transport_facility_importance: 0,
  education_facility_importance: 0,
  medical_facility_importance: 0,
  shopping_facility_importance: 0,
  culture_facility_importance: 0,
  store_density_preference: null,
  franchise_preference: null,
  preferred_districts: [],
  excluded_districts: [],
  min_data_reliability: 0,
  top_n: 10,
  strategy: 'balanced',
  total_startup_budget_krw: null,
  monthly_converted_rent_limit_krw: null,
  rentable_area_sqm: null,
  floor: null,
}

const preferenceKeys: Array<keyof RecommendationRequest> = [
  'preferred_area_types', 'target_gender', 'target_age_groups', 'preferred_time_bands',
  'weekend_importance', 'floating_population_importance', 'resident_population_importance',
  'worker_population_importance', 'apartment_importance', 'transport_facility_importance',
  'education_facility_importance', 'medical_facility_importance', 'shopping_facility_importance',
  'culture_facility_importance', 'store_density_preference', 'franchise_preference',
  'preferred_districts', 'excluded_districts', 'min_data_reliability',
]

export function hasPreference(request: RecommendationRequest): boolean {
  return preferenceKeys.some((key) => {
    const value = request[key]
    return Array.isArray(value) ? value.length > 0 : Boolean(value)
  })
}

export function toggleValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]
}
