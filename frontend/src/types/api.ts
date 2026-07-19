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
  strategy: 'balanced' | 'condition_fit' | 'growth' | 'stability'
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

export type AgentPhase = 'discovering' | 'exploring' | 'scenarios_ready' | 'ready_for_confirmation' | 'results'

export interface AgentMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface RecommendationDraft extends Omit<RecommendationRequest, 'industry_code'> {
  industry_code: string | null
}

export interface FounderContext {
  business_description: string | null
  target_customer: string | null
  operating_pattern: string | null
  location_flexibility: 'fixed' | 'flexible' | 'open' | null
  risk_tolerance: 'low' | 'medium' | 'high' | null
  budget_note: string | null
  priorities: string[]
  discovery_question_count: number
}

export interface AgentAssumption {
  id: string
  text: string
  source_field: string
  status: 'inferred' | 'confirmed' | 'rejected'
}

export interface StrategyScenario {
  id: 'condition_fit' | 'growth' | 'stability'
  strategy: 'condition_fit' | 'growth' | 'stability'
  title: string
  description: string
  request: RecommendationRequest
  candidate_count: number
  recommendations: RecommendationItem[]
  diagnostics: Record<string, unknown>
  relaxed_fields: string[]
}

export interface TradeoffInsight {
  kind: 'candidate_scarcity' | 'preference_conflict' | 'strategy_disagreement'
  message: string
  severity: 'info' | 'warning'
}

export interface RelaxationOption {
  id: string
  label: string
  relaxed_fields: Array<'preferred_districts' | 'preferred_area_types'>
  candidate_count_before: number
  candidate_count_after: number
  request: RecommendationRequest
}

export interface DataGap {
  code: 'commercial_cost'
  message: string
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
  action: 'message' | 'select_scenario' | 'confirm_recommendation'
  message: string
  history: AgentMessage[]
  draft: RecommendationDraft
  context: FounderContext
  assumptions: AgentAssumption[]
  scenario_id: 'condition_fit' | 'growth' | 'stability' | null
  selected_scenario_id: 'condition_fit' | 'growth' | 'stability' | null
  analysis_revision: number
  active_recommendation_request: RecommendationRequest | null
}

export interface AgentTurnResponse {
  request_id: string
  artifact_version: string
  assistant_message: string
  phase: AgentPhase
  draft: RecommendationDraft
  context: FounderContext
  assumptions: AgentAssumption[]
  missing_fields: string[]
  confirmation_summary: string | null
  exploration_summary: Record<string, unknown>
  scenarios: StrategyScenario[]
  tradeoffs: TradeoffInsight[]
  relaxation_options: RelaxationOption[]
  data_gaps: DataGap[]
  selected_scenario_id: 'condition_fit' | 'growth' | 'stability' | null
  analysis_revision: number
  recommendations: RecommendationItem[]
  diagnostics: Record<string, unknown>
  comparison: AreaComparison[]
}
