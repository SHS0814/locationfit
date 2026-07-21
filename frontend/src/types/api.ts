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
  rent_floors: MetadataOption[]
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
  total_startup_budget_krw: number | null
  monthly_converted_rent_limit_krw: number | null
  rentable_area_sqm: number | null
  floor: FloorType | null
}

export type FloorType = 'all' | 'f1' | 'non_f1'

export interface RentalEstimate {
  area_code: string
  area_name: string
  admin_dong_name: string
  rent_basis_geography: 'admin_dong' | 'district'
  rent_basis_name: string
  geography_fallback_used: boolean
  floor: FloorType
  rent_basis_floor: FloorType
  fallback_used: boolean
  rentable_area_sqm: number
  unit_converted_rent_krw_sqm: number
  estimated_converted_monthly_rent_krw: number
  annual_conversion_rate: number
  reference_period: string
  source: string
  disclosure: string
}

export interface FitReason {
  factor: string
  feature: string
  fit_score: number
  weight: number
}

export interface AreaBoundary {
  type: 'Polygon' | 'MultiPolygon'
  coordinates: number[][][] | number[][][][]
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
  area_size_sqm: number
  boundary: AreaBoundary
  final_score: number
  base_final_score: number | null
  budget_fit_score: number | null
  budget_adjusted: boolean
  condition_fit_score: number
  raw_evidence_score: number | null
  reliability_adjusted_evidence_score: number | null
  data_reliability: number
  reliability_grade: string
  positive_reasons: FitReason[]
  negative_reasons: FitReason[]
  evidence_summary: Record<string, unknown>
  warnings: string[]
  rental_estimate: RentalEstimate | null
}

export interface LeasePlanRequest {
  area_code: string
  floor: FloorType
  rentable_area_sqm: number
  deposit_krw: number | null
  total_startup_budget_krw: number | null
}

export interface LeasePlan {
  estimated_converted_monthly_rent_krw: number
  deposit_krw: number | null
  cash_monthly_rent_krw: number | null
  annual_cash_rent_krw: number | null
  first_year_cash_outlay_krw: number | null
  refundable_deposit_krw: number | null
  remaining_startup_budget_krw: number | null
  deposit_share_of_budget: number | null
  annual_conversion_rate: number
  disclosure: string
}

export interface LeasePlanResponse {
  request_id: string
  rental_estimate: RentalEstimate
  lease_plan: LeasePlan
}

export interface RecommendationResponse {
  request_id: string
  artifact_version: string
  recommendations: RecommendationItem[]
  diagnostics: Record<string, unknown>
}

export type StoreRelation = 'competitor' | 'complementary' | 'daily_life' | 'other'

export interface StorePoint {
  store_id: string
  name: string
  branch_name: string | null
  industry_large_code: string | null
  industry_large_name: string | null
  industry_middle_code: string | null
  industry_middle_name: string | null
  industry_small_code: string | null
  industry_small_name: string | null
  ksic_code: string | null
  ksic_name: string | null
  road_address: string | null
  lot_address: string | null
  building_name: string | null
  building_management_number: string | null
  floor: string | null
  unit: string | null
  longitude: number
  latitude: number
  relation: StoreRelation
}

export interface AreaStoresResponse {
  request_id: string
  area_code: string
  area_name: string
  industry_code: string
  industry_name: string
  reference_month: string | null
  fetched_at: string
  cache_status: 'fresh' | 'refreshed' | 'stale'
  source: string
  disclosure: string
  warnings: string[]
  summary: {
    total_count: number
    total_density_per_sqkm: number
    competitor_count: number
    competitor_density_per_sqkm: number
    relation_counts: Array<{ relation: StoreRelation; count: number }>
    top_categories: Array<{ code: string | null; name: string; count: number }>
  }
  stores: StorePoint[]
}

export interface WebResearchSource {
  title: string
  url: string
}

export interface WebResearchRequest {
  scope: 'area' | 'store'
  area_code: string
  industry_code: string
  store_id: string | null
  active_recommendation_request: RecommendationRequest
  context: FounderContext
}

export interface WebResearchResponse {
  request_id: string
  scope: 'area' | 'store'
  area_code: string
  store_id: string | null
  subject: string
  summary: string
  sources: WebResearchSource[]
  searched_at: string
  warnings: string[]
}

export interface LeaseCandidateExtraction {
  listing_title: string | null
  address: string | null
  deposit_krw: number | null
  monthly_rent_krw: number | null
  management_fee_krw: number | null
  key_money_krw: number | null
  rentable_area_sqm: number | null
  floor: string | null
  notes: string | null
  missing_fields: string[]
}

export interface LeaseCandidateExtractRequest {
  source_url: string | null
  source_text: string | null
  selected_area_name: string
}

export interface LeaseCandidateExtractResponse {
  request_id: string
  source_url: string | null
  source_kind: 'url' | 'text' | 'url_and_text'
  extracted: LeaseCandidateExtraction
  warnings: string[]
  requires_confirmation: boolean
}

export type FinancialVulnerability = 'low_credit' | 'basic_livelihood' | 'near_poverty' | 'earned_income_tax_credit' | 'none' | 'unknown'

export interface FinancePlanRequest {
  candidate: {
    source_url: string | null
    listing_title: string | null
    address: string | null
    deposit_krw: number
    monthly_rent_krw: number
    management_fee_krw: number
    key_money_krw: number
    rentable_area_sqm: number | null
    floor: string | null
  }
  additional_costs: {
    interior_krw: number
    equipment_krw: number
    initial_inventory_krw: number
    working_capital_krw: number
    other_krw: number
  }
  eligibility: {
    own_capital_krw: number
    business_status: 'pre_startup' | 'operating'
    business_age_months: number | null
    is_small_business: boolean | null
    vulnerability: FinancialVulnerability
    has_policy_excluded_industry: boolean | null
  }
}

export interface FinancePlanResponse {
  request_id: string
  funding: {
    refundable_deposit_krw: number
    one_time_nonrefundable_krw: number
    annual_occupancy_cost_krw: number
    additional_startup_cost_krw: number
    total_first_year_cash_need_krw: number
    own_capital_krw: number
    funding_gap_krw: number
    own_capital_ratio: number
  }
  policy_candidates: Array<{
    program_id: string
    name: string
    provider: string
    status: 'basic_fit' | 'needs_review' | 'not_eligible'
    reasons: string[]
    checks_required: string[]
    source_title: string
    source_url: string
    source_checked_at: string
  }>
  disclosure: string
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

export interface MarketLookupRow {
  rank: number
  entity_code: string | null
  entity_name: string
  metric_value: number
  metric_display_value: string
  difference_from_mean: number
  difference_from_mean_display: string
  difference_from_median: number
  difference_from_median_display: string
  standard_deviation_distance: number
  district_name: string | null
  admin_dong_name: string | null
  area_count: number
  observation_count: number
}

export interface MarketLookupDistribution {
  population_count: number
  mean: number
  mean_display: string
  median: number
  median_display: string
  standard_deviation: number
  standard_deviation_display: string
}

export interface MarketLookupResult {
  title: string
  group_by: 'area' | 'industry' | 'district' | 'admin_dong'
  metric: 'sales' | 'closing_rate' | 'opening_rate' | 'growth_rate' | 'store_count' | 'store_density' | 'floating_population' | 'resident_population' | 'worker_population'
  metric_label: string
  metric_unit: 'krw' | 'ratio' | 'count' | 'count_per_sqkm' | 'people'
  order: 'desc' | 'asc'
  filters: Record<string, string>
  data_period: string
  distribution: MarketLookupDistribution
  rows: MarketLookupRow[]
  geographic_basis: string
  disclosure: string
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
  recent_store_count: number | null
  same_industry_store_density: number | null
  recent_4q_average_sales: number | null
  recent_4q_growth_rate: number | null
  closing_rate: number | null
  data_reliability: number | null
  reliability_grade: string | null
}

export interface RecommendationReportMetrics {
  final_score: number | null
  condition_fit_score: number | null
  reliability_adjusted_evidence_score: number | null
  recent_4q_average_sales: number | null
  recent_4q_growth_rate: number | null
  recent_store_count: number | null
  same_industry_store_density: number | null
  closing_rate: number | null
  floating_population: number | null
  resident_population: number | null
  worker_population: number | null
  data_reliability: number | null
  estimated_converted_monthly_rent_krw: number | null
  unit_converted_rent_krw_sqm: number | null
}

export type RecommendationReportMetricKey = keyof RecommendationReportMetrics

export interface RecommendationReportArea {
  rank: number
  area_code: string
  area_name: string
  district_name: string
  area_type: string
  reliability_grade: string
  base_final_score: number | null
  budget_fit_score: number | null
  rental_estimate: RentalEstimate | null
  metrics: RecommendationReportMetrics
  benchmark_delta: RecommendationReportMetrics
  positive_reasons: FitReason[]
  negative_reasons: FitReason[]
  warnings: string[]
}

export interface RecommendationReport {
  candidate_count: number
  benchmark_label: string
  data_period: Record<string, string>
  competition_reference_period: string
  rental_estimate_basis: string
  rental_estimate_uses_default: boolean
  benchmark: RecommendationReportMetrics
  areas: RecommendationReportArea[]
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
  recommendation_report: RecommendationReport | null
  market_lookup: MarketLookupResult | null
}
