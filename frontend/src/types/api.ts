export interface MetadataOption {
  code: string
  name: string
}

export interface MetadataResponse {
  artifact_version: string
  data_period: Record<string, string>
  industries: MetadataOption[]
  districts: string[]
  area_types: MetadataOption[]
  age_groups: MetadataOption[]
  time_bands: MetadataOption[]
}

export interface RecommendationRequest {
  industry_code: string
  preferred_area_types: string[]
  target_gender: 'male' | 'female' | null
  target_age_groups: string[]
  preferred_time_bands: string[]
  weekend_importance: number
  floating_population_importance: number
  resident_population_importance: number
  worker_population_importance: number
  apartment_importance: number
  transport_facility_importance: number
  education_facility_importance: number
  medical_facility_importance: number
  shopping_facility_importance: number
  culture_facility_importance: number
  store_density_preference: 'high' | 'low' | null
  franchise_preference: 'high' | 'low' | null
  preferred_districts: string[]
  excluded_districts: string[]
  min_data_reliability: number
  top_n: number
}

export interface FitReason {
  factor: string
  feature: string
  fit_score: number
  weight: number
}

export interface RecommendationItem {
  rank: number
  area_code: string
  area_name: string
  district_name: string
  admin_dong_name: string | null
  area_type: string
  industry_code: string
  industry_name: string
  latitude: number
  longitude: number
  final_score: number
  condition_fit_score: number
  raw_evidence_score: number | null
  reliability_adjusted_evidence_score: number | null
  data_reliability: number
  reliability_grade: string
  positive_reasons: FitReason[]
  negative_reasons: FitReason[]
  evidence_summary: Record<string, unknown>
  warnings: string[]
}

export interface RecommendationResponse {
  request_id: string
  artifact_version: string
  recommendations: RecommendationItem[]
  diagnostics: Record<string, unknown>
}

export interface ApiErrorBody {
  error?: {
    code?: string
    message?: string
    request_id?: string
  }
  detail?: Array<{ msg: string }>
}

export type AgentPhase = 'gathering' | 'ready_for_confirmation' | 'results'

export interface AgentMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface RecommendationDraft extends Omit<RecommendationRequest, 'industry_code'> {
  industry_code: string | null
}

export interface AreaComparison {
  area_code: string
  area_name: string
  district_name: string
  area_type: string
  floating_population: number | null
  resident_population: number | null
  worker_population: number | null
  transport_facility_count: number | null
  education_facility_count: number | null
  medical_facility_count: number | null
  shopping_facility_count: number | null
  culture_facility_count: number | null
  apartment_average_market_price: number | null
  competition_intensity: number | null
  recent_4q_average_sales: number | null
  recent_4q_growth_rate: number | null
  closing_rate: number | null
  data_reliability: number | null
  reliability_grade: string | null
}

export interface AgentTurnRequest {
  action: 'message' | 'confirm_recommendation'
  message: string
  history: AgentMessage[]
  draft: RecommendationDraft
  active_recommendation_request: RecommendationRequest | null
}

export interface AgentTurnResponse {
  request_id: string
  artifact_version: string
  assistant_message: string
  phase: AgentPhase
  draft: RecommendationDraft
  missing_fields: string[]
  confirmation_summary: string | null
  recommendations: RecommendationItem[]
  diagnostics: Record<string, unknown>
  comparison: AreaComparison[]
}
