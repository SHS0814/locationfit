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
  ActiveMarketLookupQuery,
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
export const DEMO_FLOW_QUERY_VALUE = 'hongdae-cafe'

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

export type AgentCommandStageId =
  | 'understand_conditions'
  | 'explore_market'
  | 'compare_strategies'
  | 'run_recommendation'
  | 'review_lease'
  | 'prepare_funding'

export type AgentCommandStageStatus = 'pending' | 'active' | 'complete'

export interface AgentCommandStage {
  id: AgentCommandStageId
  label: string
  status: AgentCommandStageStatus
  detail: string
}

export interface AgentBriefing {
  eyebrow: string
  title: string
  summary: string
  evidence: string[]
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

export const hongdaeCafeDemoDraft: RecommendationDraft = {
  ...emptyDraft,
  industry_code: 'CS100010',
  preferred_districts: ['마포구'],
  target_age_groups: ['20'],
  weekend_importance: 0.8,
  top_n: 3,
  strategy: 'growth',
  total_startup_budget_krw: 150_000_000,
  monthly_converted_rent_limit_krw: 5_000_000,
  rentable_area_sqm: 66,
  floor: 'f1',
}

export function createHongdaeCafeDemoSession(): AgentSession {
  return {
    ...initialSession,
    history: [
      ...initialMessages,
      {
        role: 'user',
        content: '마포구 홍대권에서 20대 주말 수요를 보는 커피-음료 매장을 검토합니다.',
      },
    ],
    draft: { ...hongdaeCafeDemoDraft },
    context: {
      ...emptyContext,
      business_description: '20대 방문 수요를 겨냥한 커피-음료 매장',
      target_customer: '홍대권을 찾는 20대 고객',
      operating_pattern: '주말 유동 수요를 중요하게 봅니다.',
      location_flexibility: 'fixed',
      risk_tolerance: 'high',
      budget_note: '총 창업예산 1.5억, 월 환산임대료 한도 500만원',
      priorities: ['주말 유동', '성장 가능성', '임대료 한도'],
    },
    phase: 'discovering',
  }
}

export function shouldRunDemoFlow(search: string): boolean {
  return new URLSearchParams(search).get('demo') === DEMO_FLOW_QUERY_VALUE
}

export function marketLookupToQuery(lookup: MarketLookupResult | null): ActiveMarketLookupQuery | null {
  if (!lookup) return null
  return {
    group_by: lookup.group_by,
    metric: lookup.metric,
    top_n: lookup.rows.length,
    order: lookup.order,
    district_name: lookup.filters.district_name || null,
    admin_dong_name: lookup.filters.admin_dong_name || null,
    industry_code: lookup.filters.industry_code || null,
  }
}

export function createDemoLeaseCandidate(area: RecommendationItem): LeaseCandidateRecord {
  const timestamp = '2026-07-24T00:00:00.000Z'
  return {
    id: `demo-lease-${area.area_code}`,
    areaCode: area.area_code,
    areaName: area.area_name,
    industryCode: area.industry_code,
    industryName: area.industry_name,
    sourceUrl: null,
    sourceKind: 'manual',
    title: `${area.area_name} 1층 커피 매장 후보 (데모)`,
    address: `서울 ${area.district_name} ${area.area_name} 인근`,
    depositKrw: 50_000_000,
    monthlyRentKrw: 4_200_000,
    managementFeeKrw: 400_000,
    keyMoneyKrw: 20_000_000,
    rentableAreaSqm: 66,
    floor: '1층',
    notes: '시연을 위해 임의로 입력한 매물입니다. 실제 임대 가능 여부와 계약 조건은 확인되지 않았습니다.',
    warnings: ['데모용 임의 매물입니다. 실제 매물이나 계약 정보로 사용하지 마세요.'],
    createdAt: timestamp,
    updatedAt: timestamp,
  }
}

export function createDemoLeaseFinanceState(): LeaseCandidateFinanceState {
  return {
    additionalCosts: {
      interior_krw: 40_000_000,
      equipment_krw: 15_000_000,
      initial_inventory_krw: 8_000_000,
      working_capital_krw: 20_000_000,
      other_krw: 0,
    },
    eligibility: {
      own_capital_krw: 80_000_000,
      business_status: 'pre_startup',
      business_age_months: null,
      is_small_business: true,
      vulnerability: 'unknown',
      has_policy_excluded_industry: false,
    },
    plan: null,
  }
}

export function isDraftReady(draft: RecommendationDraft): boolean {
  const rentFields = [draft.rentable_area_sqm, draft.floor]
  const hasAnyRentField = rentFields.some((value) => value != null)
  const hasAllRentFields = rentFields.every((value) => value != null)
  const rentReady = (!hasAnyRentField || hasAllRentFields)
    && (draft.monthly_converted_rent_limit_krw == null || hasAllRentFields)
  return Boolean(draft.industry_code) && rentReady
}

export function deriveAgentCommandStages(session: AgentSession, loading = false): AgentCommandStage[] {
  const conditionsReady = isDraftReady(session.draft)
  const marketExplored = session.scenarios.length > 0 || session.recommendationReport != null
  const strategySelected = session.selectedScenarioId != null || session.recommendationReport != null
  const recommendationReady = session.recommendationReport != null && session.items.length > 0
  const leaseReviewed = session.leaseCandidates.length > 0
  const fundingPrepared = Object.values(session.leaseFinanceById).some((finance) => finance.plan != null)

  const completed = [conditionsReady, marketExplored, strategySelected, recommendationReady, leaseReviewed, fundingPrepared]
  const activeIndex = completed.findIndex((value) => !value)
  const eligibleAreaCount = Number(session.explorationSummary.eligible_area_count)
  const marketScopeDetail = Number.isFinite(eligibleAreaCount) && eligibleAreaCount > 0
    ? `${eligibleAreaCount.toLocaleString('ko-KR')}개 후보 범위를 탐색했습니다.`
    : '서울 전역의 후보 범위를 탐색했습니다.'
  const details = [
    conditionsReady ? '업종과 핵심 조건을 구조화했습니다.' : '대화에서 업종과 운영 조건을 정리합니다.',
    marketExplored ? marketScopeDetail : '조건에 맞는 서울 상권 후보를 탐색합니다.',
    strategySelected ? `${strategyName(session.selectedScenarioId || session.draft.strategy)}을 주 전략으로 설정했습니다.` : '조건 충실·성장·안정 가설을 비교합니다.',
    recommendationReady ? `${session.items.length}개 상권의 순위와 근거를 산출했습니다.` : '확인된 조건으로 추천 분석 도구를 실행합니다.',
    leaseReviewed ? `${session.leaseCandidates.length}개 임대매물을 후보로 연결했습니다.` : '추천 상권의 실제 임대매물 조건을 검토합니다.',
    fundingPrepared ? '매물 기준 자금계획을 계산했습니다.' : '보증금·초기비용과 정책자금 가능성을 점검합니다.',
  ]
  const labels = ['조건 이해', '시장 범위 탐색', '전략 가설 비교', '추천 실행', '매물 후보 검토', '자금계획 준비']
  const ids: AgentCommandStageId[] = [
    'understand_conditions', 'explore_market', 'compare_strategies',
    'run_recommendation', 'review_lease', 'prepare_funding',
  ]

  return ids.map((id, index) => ({
    id,
    label: labels[index],
    status: completed[index] ? 'complete' : index === activeIndex ? 'active' : 'pending',
    detail: index === activeIndex && loading ? `${details[index]} 지금 처리 중입니다.` : details[index],
  }))
}

export function createAgentBriefing(session: AgentSession, stages = deriveAgentCommandStages(session)): AgentBriefing {
  const report = session.recommendationReport
  const topArea = report?.areas[0]
  if (report && topArea) {
    const positive = topArea.positive_reasons[0]
    const negative = topArea.negative_reasons[0]
    const alternatives = report.areas.slice(1, 3).map((area) => `${area.rank}위 ${area.area_name}`).join(' · ')
    const evidence = [
      positive ? `추천 이유 · ${positive.factor}` : null,
      negative ? `확인 필요 · ${negative.factor}` : null,
      alternatives ? `대안 · ${alternatives}` : null,
    ].filter((item): item is string => item != null)
    return {
      eyebrow: 'AI RECOMMENDATION BRIEF',
      title: `${topArea.area_name}을 1순위로 제안합니다`,
      summary: `확인된 조건과 과거 관측 성과를 함께 보면 ${positive ? `${positive.factor} 적합도가 핵심 강점입니다.` : '종합적인 조건 부합도가 가장 높습니다.'} 세부 수치는 아래 보고서에서 확인하고, 궁금한 이유나 후보 간 차이는 AI에게 이어서 물어볼 수 있습니다.`,
      evidence,
    }
  }

  const activeStage = stages.find((stage) => stage.status === 'active') || stages[stages.length - 1]
  return {
    eyebrow: 'AI COMMAND CENTER',
    title: activeStage.label,
    summary: activeStage.detail,
    evidence: [],
  }
}

function strategyName(strategy: RecommendationDraft['strategy'] | null): string {
  return ({
    balanced: '균형형',
    condition_fit: '조건 충실형',
    growth: '성장 기회형',
    stability: '안정성 우선형',
  } as const)[strategy || 'balanced']
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

function restoreLeaseFinanceStates(value: unknown): Record<string, LeaseCandidateFinanceState> {
  if (!value || typeof value !== 'object') return {}
  return Object.fromEntries(Object.entries(value).map(([key, rawState]) => {
    const state = rawState as LeaseCandidateFinanceState
    const candidates = state.plan?.policy_candidates
    const compatiblePlan = state.plan == null || (
      Array.isArray(candidates)
      && candidates.every((candidate) => (
        typeof candidate.product_type === 'string'
        && typeof candidate.catalog_status === 'string'
        && Array.isArray(candidate.benefits)
      ))
    )
    return [key, compatiblePlan ? state : { ...state, plan: null }]
  }))
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
      leaseFinanceById: currentSchema ? restoreLeaseFinanceStates(parsed.leaseFinanceById) : {},
      selectedLeaseCandidateId: currentSchema && typeof parsed.selectedLeaseCandidateId === 'string'
        ? parsed.selectedLeaseCandidateId : null,
      financeAreaCode: currentSchema && typeof parsed.financeAreaCode === 'string' ? parsed.financeAreaCode : null,
    }
  } catch {
    return initialSession
  }
}
