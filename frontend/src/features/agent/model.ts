import type {
  AgentMessage,
  AgentPhase,
  AgentAssumption,
  AreaStoresResponse,
  AreaComparison,
  DataGap,
  FounderContext,
  MarketLookupResult,
  RecommendationDraft,
  RecommendationItem,
  RecommendationReport,
  RecommendationRequest,
  RelaxationOption,
  StrategyScenario,
  TradeoffInsight,
  StoreRelation,
  WebResearchResponse,
} from '../../types/api'
import type { LeaseCandidateFinanceState, LeaseCandidateRecord } from '../finance/model'

export const AGENT_SESSION_KEY = 'kb-location-agent-session-v8'
export const AGENT_V7_SESSION_KEY = 'kb-location-agent-session-v7'
export const AGENT_V6_SESSION_KEY = 'kb-location-agent-session-v6'
export const AGENT_V5_SESSION_KEY = 'kb-location-agent-session-v5'
export const AGENT_V4_SESSION_KEY = 'kb-location-agent-session-v4'
export const AGENT_V3_SESSION_KEY = 'kb-location-agent-session-v3'
export const AGENT_V2_SESSION_KEY = 'kb-location-agent-session-v2'
export const AGENT_LEGACY_SESSION_KEY = 'kb-location-agent-session-v1'

export const emptyDraft: RecommendationDraft = {
  industry_code: null,
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

export const emptyContext: FounderContext = {
  business_description: null,
  target_customer: null,
  operating_pattern: null,
  location_flexibility: null,
  risk_tolerance: null,
  budget_note: null,
  priorities: [],
  discovery_question_count: 0,
}

export const initialMessages: AgentMessage[] = [{
  role: 'assistant',
  content: '입지를 추천받거나 상권 통계를 바로 조회할 수 있어요. 말하지 않은 조건은 전체 범위로 보고, 확실히 알려주신 조건만 반영합니다.',
}]

export interface AgentSession {
  schemaVersion: 8
  history: AgentMessage[]
  draft: RecommendationDraft
  phase: AgentPhase
  context: FounderContext
  assumptions: AgentAssumption[]
  explorationSummary: Record<string, unknown>
  scenarios: StrategyScenario[]
  tradeoffs: TradeoffInsight[]
  relaxationOptions: RelaxationOption[]
  dataGaps: DataGap[]
  selectedScenarioId: 'condition_fit' | 'growth' | 'stability' | null
  analysisRevision: number
  items: RecommendationItem[]
  comparison: AreaComparison[]
  recommendationReport: RecommendationReport | null
  activeRequest: RecommendationRequest | null
  marketLookup: MarketLookupResult | null
  storeAreaCode: string | null
  storeAnalysis: AreaStoresResponse | null
  selectedStoreId: string | null
  storeRelations: StoreRelation[]
  storeSearch: string
  webResearch: WebResearchResponse[]
  leaseCandidates: LeaseCandidateRecord[]
  leaseFinanceById: Record<string, LeaseCandidateFinanceState>
  selectedLeaseCandidateId: string | null
  financeAreaCode: string | null
}

export const initialSession: AgentSession = {
  schemaVersion: 8,
  history: initialMessages,
  draft: emptyDraft,
  phase: 'discovering',
  context: emptyContext,
  assumptions: [],
  explorationSummary: {},
  scenarios: [],
  tradeoffs: [],
  relaxationOptions: [],
  dataGaps: [],
  selectedScenarioId: null,
  analysisRevision: 0,
  items: [],
  comparison: [],
  recommendationReport: null,
  activeRequest: null,
  marketLookup: null,
  storeAreaCode: null,
  storeAnalysis: null,
  selectedStoreId: null,
  storeRelations: ['competitor', 'complementary', 'daily_life', 'other'],
  storeSearch: '',
  webResearch: [],
  leaseCandidates: [],
  leaseFinanceById: {},
  selectedLeaseCandidateId: null,
  financeAreaCode: null,
}

export function isDraftReady(draft: RecommendationDraft): boolean {
  const rentFields = [draft.rentable_area_sqm, draft.floor]
  const hasAnyRentField = rentFields.some((value) => value != null)
  const hasAllRentFields = rentFields.every((value) => value != null)
  const rentReady = (!hasAnyRentField || hasAllRentFields)
    && (draft.monthly_converted_rent_limit_krw == null || hasAllRentFields)
  return Boolean(draft.industry_code) && rentReady
}

export function draftToRequest(draft: RecommendationDraft): RecommendationRequest {
  if (!draft.industry_code) throw new Error('업종이 선택되지 않았습니다.')
  return { ...draft, industry_code: draft.industry_code }
}

export function toggleDraftValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]
}

export function hasAreaBoundary(item: unknown): item is RecommendationItem {
  if (!item || typeof item !== 'object') return false
  const candidate = item as Partial<RecommendationItem>
  return Boolean(
    typeof candidate.area_size_sqm === 'number'
    && candidate.area_size_sqm > 0
    && candidate.boundary
    && ['Polygon', 'MultiPolygon'].includes(candidate.boundary.type)
    && Array.isArray(candidate.boundary.coordinates)
    && candidate.boundary.coordinates.length > 0,
  )
}

export function restoreSession(raw: string | null): AgentSession {
  if (!raw) return initialSession
  try {
    const parsed = JSON.parse(raw) as Partial<AgentSession>
    if (!Array.isArray(parsed.history) || !parsed.draft || !parsed.phase) return initialSession
    const parsedVersion = Number((parsed as { schemaVersion?: unknown }).schemaVersion)
    const currentSchema = parsedVersion === 8
    const analysisCompatible = currentSchema || parsedVersion === 7
    const legacyDraft = parsed.draft as Partial<RecommendationDraft> & { commercial_property_type?: unknown; floor?: string | null }
    const { commercial_property_type: _removedPropertyType, ...draftValues } = legacyDraft
    const floor = legacyDraft.floor && ['all', 'f1', 'non_f1'].includes(legacyDraft.floor)
      ? legacyDraft.floor as RecommendationDraft['floor']
      : null
    const restoredItems = analysisCompatible && Array.isArray(parsed.items) && parsed.items.every(hasAreaBoundary)
      ? parsed.items
      : []
    return {
      schemaVersion: 8,
      history: parsed.history.slice(-20),
      draft: { ...emptyDraft, ...draftValues, floor },
      phase: !analysisCompatible || parsed.phase === ('gathering' as AgentPhase) ? 'discovering' : parsed.phase,
      context: { ...emptyContext, ...parsed.context },
      assumptions: Array.isArray(parsed.assumptions) ? parsed.assumptions : [],
      explorationSummary: parsed.explorationSummary || {},
      scenarios: analysisCompatible && Array.isArray(parsed.scenarios) ? parsed.scenarios : [],
      tradeoffs: Array.isArray(parsed.tradeoffs) ? parsed.tradeoffs : [],
      relaxationOptions: Array.isArray(parsed.relaxationOptions) ? parsed.relaxationOptions : [],
      dataGaps: Array.isArray(parsed.dataGaps) ? parsed.dataGaps : [],
      selectedScenarioId: parsed.selectedScenarioId || null,
      analysisRevision: Number(parsed.analysisRevision || 0),
      items: restoredItems,
      comparison: Array.isArray(parsed.comparison) ? parsed.comparison : [],
      recommendationReport: analysisCompatible ? parsed.recommendationReport || null : null,
      activeRequest: analysisCompatible ? parsed.activeRequest || null : null,
      marketLookup: parsed.marketLookup || null,
      storeAreaCode: analysisCompatible && typeof parsed.storeAreaCode === 'string' ? parsed.storeAreaCode : null,
      storeAnalysis: analysisCompatible && parsed.storeAnalysis ? parsed.storeAnalysis : null,
      selectedStoreId: analysisCompatible && typeof parsed.selectedStoreId === 'string' ? parsed.selectedStoreId : null,
      storeRelations: analysisCompatible && Array.isArray(parsed.storeRelations)
        ? parsed.storeRelations
        : ['competitor', 'complementary', 'daily_life', 'other'],
      storeSearch: analysisCompatible && typeof parsed.storeSearch === 'string' ? parsed.storeSearch : '',
      webResearch: analysisCompatible && Array.isArray(parsed.webResearch) ? parsed.webResearch : [],
      leaseCandidates: currentSchema && Array.isArray(parsed.leaseCandidates) ? parsed.leaseCandidates : [],
      leaseFinanceById: currentSchema && parsed.leaseFinanceById && typeof parsed.leaseFinanceById === 'object'
        ? parsed.leaseFinanceById : {},
      selectedLeaseCandidateId: currentSchema && typeof parsed.selectedLeaseCandidateId === 'string'
        ? parsed.selectedLeaseCandidateId : null,
      financeAreaCode: currentSchema && typeof parsed.financeAreaCode === 'string' ? parsed.financeAreaCode : null,
    }
  } catch {
    return initialSession
  }
}
