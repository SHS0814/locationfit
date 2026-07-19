import type {
  AgentMessage,
  AgentPhase,
  AreaComparison,
  RecommendationDraft,
  RecommendationItem,
  RecommendationRequest,
} from '../../types/api'

export const AGENT_SESSION_KEY = 'kb-location-agent-session-v1'

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
}

export const initialMessages: AgentMessage[] = [{
  role: 'assistant',
  content: '어떤 가게를 어디에 열고 싶으신가요? 업종과 원하는 고객이나 지역을 편하게 말씀해주세요.',
}]

export interface AgentSession {
  history: AgentMessage[]
  draft: RecommendationDraft
  phase: AgentPhase
  items: RecommendationItem[]
  comparison: AreaComparison[]
  activeRequest: RecommendationRequest | null
}

export const initialSession: AgentSession = {
  history: initialMessages,
  draft: emptyDraft,
  phase: 'gathering',
  items: [],
  comparison: [],
  activeRequest: null,
}

export function hasDraftPreference(draft: RecommendationDraft): boolean {
  return Object.entries(draft).some(([key, value]) => {
    if (key === 'industry_code' || key === 'top_n') return false
    return Array.isArray(value) ? value.length > 0 : Boolean(value)
  })
}

export function isDraftReady(draft: RecommendationDraft): boolean {
  return Boolean(draft.industry_code) && hasDraftPreference(draft)
}

export function draftToRequest(draft: RecommendationDraft): RecommendationRequest {
  if (!draft.industry_code) throw new Error('업종이 선택되지 않았습니다.')
  return { ...draft, industry_code: draft.industry_code }
}

export function toggleDraftValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]
}

export function restoreSession(raw: string | null): AgentSession {
  if (!raw) return initialSession
  try {
    const parsed = JSON.parse(raw) as Partial<AgentSession>
    if (!Array.isArray(parsed.history) || !parsed.draft || !parsed.phase) return initialSession
    return {
      history: parsed.history.slice(-20),
      draft: { ...emptyDraft, ...parsed.draft },
      phase: parsed.phase,
      items: Array.isArray(parsed.items) ? parsed.items : [],
      comparison: Array.isArray(parsed.comparison) ? parsed.comparison : [],
      activeRequest: parsed.activeRequest || null,
    }
  } catch {
    return initialSession
  }
}
