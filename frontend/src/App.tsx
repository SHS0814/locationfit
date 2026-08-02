import { useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import { RecommendationMap } from './components/map/RecommendationMap'
import { AgentPanel } from './features/agent/AgentPanel'
import { AgentAnalysisPanels } from './features/agent/AgentAnalysisPanels'
import { AiAccessGate } from './features/agent/AiAccessGate'
import { AgentCommandCenter } from './features/agent/AgentCommandCenter'
import { LatestRequestGuard } from './features/agent/asyncRequest'
import { MarketLookupCard } from './features/agent/MarketLookupCard'
import { MarketLookupMap } from './features/agent/MarketLookupMap'
import { isMappableLookup, marketLookupEntityKey } from './features/agent/marketLookupMapModel'
import { OutputPager, type OutputPage } from './features/agent/OutputPager'
import { WorkspaceAgentPanel } from './features/agent/WorkspaceAgentPanel'
import {
  AGENT_LEGACY_SESSION_KEY,
  AGENT_SESSION_KEY,
  AGENT_V9_SESSION_KEY,
  AGENT_V8_SESSION_KEY,
  AGENT_V7_SESSION_KEY,
  AGENT_V6_SESSION_KEY,
  AGENT_V5_SESSION_KEY,
  AGENT_V4_SESSION_KEY,
  AGENT_V2_SESSION_KEY,
  AGENT_V3_SESSION_KEY,
  createDemoLeaseCandidate,
  createDemoLeaseFinanceState,
  createInitialWorkspaceChats,
  draftToRequest,
  createHongdaeCafeDemoSession,
  initialSession,
  hasAreaBoundary,
  isDraftReady,
  marketLookupToQuery,
  restoreSession,
  shouldRunDemoFlow,
  type AgentSession,
} from './features/agent/model'
import { RecommendationResults } from './features/recommendation/RecommendationResults'
import { RecommendationReportView } from './features/recommendation/RecommendationReport'
import { LeasePlanCard } from './features/recommendation/LeasePlanCard'
import { AreaStoreExplorer } from './features/stores/AreaStoreExplorer'
import { LeaseCandidateEditor } from './features/finance/LeaseCandidateEditor'
import { LeaseCandidateWorkspace } from './features/finance/LeaseCandidateWorkspace'
import { emptyFinanceState, leaseSelectionForArea, type LeaseCandidateFinanceState, type LeaseCandidateRecord } from './features/finance/model'
import type { AgentAssumption, AgentTurnRequest, MetadataResponse, RecommendationDraft, RecommendationItem, RelaxationOption, StoreRelation, WorkspaceAgentScope, WorkspaceAgentState, WorkspaceToolOutput } from './types/api'

type RecommendationPage = 'analysis' | WorkspaceAgentScope

const recommendationPageOrder: RecommendationPage[] = ['analysis', 'stores', 'finance']
const recommendationPageLabels: Record<RecommendationPage, string> = {
  analysis: '상권분석',
  stores: '상권내 점포분석',
  finance: '자금계획',
}

export default function App() {
  const [accessState, setAccessState] = useState<'checking' | 'granted' | 'required' | 'error'>('checking')
  const [accessRequired, setAccessRequired] = useState(true)
  const [accessError, setAccessError] = useState<string | null>(null)

  useEffect(() => {
    api.aiSessionStatus()
      .then((status) => {
        setAccessRequired(status.required)
        setAccessState(status.authenticated ? 'granted' : 'required')
      })
      .catch((reason: Error) => {
        setAccessError(reason.message)
        setAccessState('error')
      })
  }, [])

  useEffect(() => {
    const expireSession = () => setAccessState('required')
    window.addEventListener('locationfit:ai-session-expired', expireSession)
    return () => window.removeEventListener('locationfit:ai-session-expired', expireSession)
  }, [])

  if (accessState === 'checking') {
    return <main className="ai-access-shell"><p>보안 세션을 확인하고 있습니다…</p></main>
  }
  if (accessState === 'error') {
    return <main className="ai-access-shell"><section className="ai-access-card"><h1>접근 보안 설정 오류</h1><p role="alert">{accessError}</p></section></main>
  }
  if (accessState === 'required') {
    return <AiAccessGate onAuthenticated={() => setAccessState('granted')} />
  }
  return (
    <ProtectedApp
      showSessionExit={accessRequired}
      onSessionEnded={() => setAccessState('required')}
    />
  )
}

interface ProtectedAppProps {
  showSessionExit: boolean
  onSessionEnded: () => void
}

function ProtectedApp({ showSessionExit, onSessionEnded }: ProtectedAppProps) {
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null)
  const [session, setSession] = useState<AgentSession>(() => restoreSession(
    sessionStorage.getItem(AGENT_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V9_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V8_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V7_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V6_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V5_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V4_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V3_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V2_SESSION_KEY)
      || sessionStorage.getItem(AGENT_LEGACY_SESSION_KEY),
  ))
  const [selected, setSelected] = useState<RecommendationItem | null>(() => session.items[0] || null)
  const [lookupSelectedKey, setLookupSelectedKey] = useState<string | null>(() => {
    const lookup = session.marketLookup
    return lookup?.rows.length ? marketLookupEntityKey(lookup, lookup.rows[0]) : null
  })
  const [outputPage, setOutputPage] = useState<OutputPage>(() => {
    if (session.items.length > 0 || session.storeAreaCode || session.financeAreaCode) return 'recommendation'
    if (session.marketLookup) return 'lookup'
    return 'strategy'
  })
  const [recommendationPage, setRecommendationPage] = useState<RecommendationPage>(() => {
    if (session.financeAreaCode) return 'finance'
    if (session.storeAreaCode) return 'stores'
    return 'analysis'
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastTurn, setLastTurn] = useState<AgentTurnRequest | null>(null)
  const [storeLoading, setStoreLoading] = useState(false)
  const [storeError, setStoreError] = useState<string | null>(null)
  const [researchLoadingKey, setResearchLoadingKey] = useState<string | null>(null)
  const [leaseEditorAreaCode, setLeaseEditorAreaCode] = useState<string | null>(null)
  const [editingLeaseCandidateId, setEditingLeaseCandidateId] = useState<string | null>(null)
  const [workspaceLoading, setWorkspaceLoading] = useState<WorkspaceAgentScope | null>(null)
  const [workspaceError, setWorkspaceError] = useState<Record<WorkspaceAgentScope, string | null>>({ stores: null, finance: null })
  const [workspaceToolOutputs, setWorkspaceToolOutputs] = useState<Record<string, WorkspaceToolOutput[]>>({})
  const demoStarted = useRef(false)
  const storeRequestGuard = useRef(new LatestRequestGuard())
  const workspaceRequestGuards = useRef<Record<WorkspaceAgentScope, LatestRequestGuard>>({
    stores: new LatestRequestGuard(),
    finance: new LatestRequestGuard(),
  })
  const recommendationItemsReady = session.items.length > 0 && session.items.every(hasAreaBoundary)

  const endDemoSession = async () => {
    try {
      await api.deleteAiSession()
      onSessionEnded()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '접속을 종료하지 못했습니다.')
    }
  }

  const activateWorkspaceRequestContext = (workspace: WorkspaceAgentScope, contextKey: string) => {
    if (!workspaceRequestGuards.current[workspace].activate(contextKey)) return
    setWorkspaceLoading((current) => current === workspace ? null : current)
    setWorkspaceError((current) => current[workspace] == null ? current : { ...current, [workspace]: null })
  }

  useEffect(() => {
    api.metadata().then(setMetadata).catch((reason: Error) => setError(reason.message))
  }, [])

  useEffect(() => {
    sessionStorage.setItem(AGENT_SESSION_KEY, JSON.stringify(session))
  }, [session])

  useEffect(() => {
    if (!metadata || demoStarted.current || !shouldRunDemoFlow(window.location.search)) return
    demoStarted.current = true
    runHongdaeCafeDemo()
  }, [metadata])

  useEffect(() => {
    if (!metadata || session.phase !== 'results' || recommendationItemsReady || !session.activeRequest) return
    let cancelled = false
    setLoading(true)
    setError(null)
    api.recommend(session.activeRequest)
      .then((response) => {
        if (cancelled) return
        if (!response.recommendations.every(hasAreaBoundary)) {
          throw new Error('상권 경계 데이터를 받지 못했습니다. API 서버를 재시작해주세요.')
        }
        setSession((current) => ({ ...current, items: response.recommendations, workspaceChats: createInitialWorkspaceChats() }))
        setSelected(response.recommendations[0] || null)
        setOutputPage('recommendation')
        setRecommendationPage('analysis')
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [metadata, recommendationItemsReady, session.activeRequest, session.phase])

  const executeTurn = async (payload: AgentTurnRequest, showUserMessage: boolean) => {
    const visibleHistory = showUserMessage
      ? [...session.history, { role: 'user' as const, content: payload.message }].slice(-20)
      : session.history
    if (showUserMessage) setSession((current) => ({ ...current, history: visibleHistory }))
    setLoading(true)
    setError(null)
    setLastTurn(payload)
    try {
      const response = await api.agentTurn(payload)
      if (response.recommendations.length && !response.recommendations.every(hasAreaBoundary)) {
        throw new Error('상권 경계 데이터를 받지 못했습니다. API 서버를 재시작해주세요.')
      }
      const keepActiveResults = response.phase === 'results'
      const isMarketLookup = Boolean(response.market_lookup)
      const preserveAnalysis = keepActiveResults || isMarketLookup
      const items = response.recommendations.length
        ? response.recommendations
        : preserveAnalysis ? session.items : []
      const activeRequest = response.recommendations.length
        ? draftToRequest(response.draft)
        : preserveAnalysis ? session.activeRequest : null
      const marketLookupHistory = response.market_lookup
        ? [...session.marketLookupHistory, response.market_lookup].slice(-20)
        : session.marketLookupHistory
      const nextSession: AgentSession = {
        schemaVersion: 9,
        history: [...visibleHistory, { role: 'assistant' as const, content: response.assistant_message }].slice(-20),
        draft: response.draft,
        phase: isMarketLookup ? session.phase : response.phase,
        context: response.context,
        assumptions: response.assumptions,
        explorationSummary: isMarketLookup ? session.explorationSummary : response.exploration_summary,
        scenarios: response.scenarios.length ? response.scenarios : preserveAnalysis ? session.scenarios : [],
        tradeoffs: response.tradeoffs.length ? response.tradeoffs : preserveAnalysis ? session.tradeoffs : [],
        relaxationOptions: response.relaxation_options.length ? response.relaxation_options : preserveAnalysis ? session.relaxationOptions : [],
        dataGaps: response.data_gaps,
        selectedScenarioId: isMarketLookup ? session.selectedScenarioId : response.selected_scenario_id,
        analysisRevision: isMarketLookup ? session.analysisRevision : response.analysis_revision,
        items,
        comparison: response.comparison.length
          ? response.comparison
          : preserveAnalysis ? session.comparison : [],
        recommendationReport: response.recommendation_report
          || (preserveAnalysis ? session.recommendationReport : null),
        activeRequest,
        marketLookup: response.market_lookup || session.marketLookup,
        marketLookupHistory,
        marketLookupIndex: response.market_lookup ? marketLookupHistory.length - 1 : session.marketLookupIndex,
        storeAreaCode: isMarketLookup
          ? null
          : preserveAnalysis && !response.recommendations.length ? session.storeAreaCode : null,
        storeAnalysis: preserveAnalysis && !response.recommendations.length ? session.storeAnalysis : null,
        selectedStoreId: isMarketLookup
          ? null
          : preserveAnalysis && !response.recommendations.length ? session.selectedStoreId : null,
        storeRelations: preserveAnalysis && !response.recommendations.length
          ? session.storeRelations
          : ['competitor', 'complementary', 'daily_life', 'other'],
        storeSearch: preserveAnalysis && !response.recommendations.length ? session.storeSearch : '',
        webResearch: preserveAnalysis && !response.recommendations.length ? session.webResearch : [],
        leaseCandidates: preserveAnalysis && !response.recommendations.length ? session.leaseCandidates : [],
        leaseFinanceById: preserveAnalysis && !response.recommendations.length ? session.leaseFinanceById : {},
        selectedLeaseCandidateId: preserveAnalysis && !response.recommendations.length ? session.selectedLeaseCandidateId : null,
        financeAreaCode: isMarketLookup
          ? null
          : preserveAnalysis && !response.recommendations.length ? session.financeAreaCode : null,
        workspaceChats: response.recommendations.length ? createInitialWorkspaceChats() : session.workspaceChats,
      }
      setSession(nextSession)
      if (response.recommendations.length) {
        setSelected(response.recommendations[0] || null)
        setOutputPage('recommendation')
        setRecommendationPage('analysis')
      } else if (response.market_lookup) {
        setLookupSelectedKey(
          response.market_lookup.rows.length
            ? marketLookupEntityKey(response.market_lookup, response.market_lookup.rows[0])
            : null,
        )
        setOutputPage('lookup')
      } else if (!preserveAnalysis) {
        setSelected(null)
        setOutputPage('strategy')
      } else if (response.phase === 'results') {
        setOutputPage('recommendation')
        setRecommendationPage('analysis')
      } else {
        setOutputPage('strategy')
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'AI 상담 요청에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const runHongdaeCafeDemo = async () => {
    const baseSession = createHongdaeCafeDemoSession()
    setSession(baseSession)
    setSelected(null)
    setOutputPage('strategy')
    setRecommendationPage('analysis')
    setLoading(true)
    setError(null)
    setLastTurn(null)
    setStoreError(null)
    setLeaseEditorAreaCode(null)
    setEditingLeaseCandidateId(null)
    try {
      const scenarioResponse = await api.agentTurn({
        action: 'select_scenario',
        message: '성장 기회형 시나리오를 선택합니다.',
        history: baseSession.history.slice(-20),
        draft: baseSession.draft,
        context: baseSession.context,
        assumptions: baseSession.assumptions,
        scenario_id: 'growth',
        selected_scenario_id: 'growth',
        analysis_revision: baseSession.analysisRevision,
        active_recommendation_request: null,
      })
      const scenarioSession: AgentSession = {
        ...baseSession,
        history: [
          ...baseSession.history,
          { role: 'assistant' as const, content: scenarioResponse.assistant_message },
        ].slice(-20),
        draft: scenarioResponse.draft,
        phase: scenarioResponse.phase,
        context: scenarioResponse.context,
        assumptions: scenarioResponse.assumptions,
        explorationSummary: scenarioResponse.exploration_summary,
        scenarios: scenarioResponse.scenarios,
        tradeoffs: scenarioResponse.tradeoffs,
        relaxationOptions: scenarioResponse.relaxation_options,
        dataGaps: scenarioResponse.data_gaps,
        selectedScenarioId: scenarioResponse.selected_scenario_id,
        analysisRevision: scenarioResponse.analysis_revision,
      }
      setSession(scenarioSession)

      const confirmResponse = await api.agentTurn({
        action: 'confirm_recommendation',
        message: '조건 카드를 확인했습니다. 이 조건으로 추천을 실행해주세요.',
        history: scenarioSession.history.slice(-20),
        draft: scenarioResponse.draft,
        context: scenarioResponse.context,
        assumptions: scenarioResponse.assumptions,
        scenario_id: null,
        selected_scenario_id: scenarioResponse.selected_scenario_id,
        analysis_revision: scenarioResponse.analysis_revision,
        active_recommendation_request: null,
      })
      if (!confirmResponse.recommendations.every(hasAreaBoundary)) {
        throw new Error('상권 경계 데이터를 받지 못했습니다. API 서버를 재시작해주세요.')
      }
      const demoArea = confirmResponse.recommendations[0] || null
      const demoLeaseCandidate = demoArea ? createDemoLeaseCandidate(demoArea) : null
      const nextSession: AgentSession = {
        ...scenarioSession,
        history: [
          ...scenarioSession.history,
          { role: 'assistant' as const, content: confirmResponse.assistant_message },
        ].slice(-20),
        draft: confirmResponse.draft,
        phase: confirmResponse.phase,
        context: confirmResponse.context,
        assumptions: confirmResponse.assumptions,
        dataGaps: confirmResponse.data_gaps,
        selectedScenarioId: confirmResponse.selected_scenario_id,
        analysisRevision: confirmResponse.analysis_revision,
        items: confirmResponse.recommendations,
        comparison: confirmResponse.comparison,
        recommendationReport: confirmResponse.recommendation_report,
        activeRequest: draftToRequest(confirmResponse.draft),
        marketLookup: null,
        marketLookupHistory: [],
        marketLookupIndex: -1,
        storeAreaCode: null,
        storeAnalysis: null,
        selectedStoreId: null,
        storeRelations: ['competitor', 'complementary', 'daily_life', 'other'],
        storeSearch: '',
        webResearch: [],
        leaseCandidates: demoLeaseCandidate ? [demoLeaseCandidate] : [],
        leaseFinanceById: demoLeaseCandidate ? {
          [demoLeaseCandidate.id]: createDemoLeaseFinanceState(),
        } : {},
        selectedLeaseCandidateId: demoLeaseCandidate?.id || null,
        financeAreaCode: demoArea?.area_code || null,
      }
      setSession(nextSession)
      setSelected(confirmResponse.recommendations[0] || null)
      setOutputPage('recommendation')
      setRecommendationPage(demoArea ? 'finance' : 'analysis')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '데모 흐름을 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const sendMessage = (message: string) => executeTurn({
    action: 'message',
    message,
    history: session.history.slice(-20),
    draft: session.draft,
    context: session.context,
    assumptions: session.assumptions,
    scenario_id: null,
    selected_scenario_id: session.selectedScenarioId,
    analysis_revision: session.analysisRevision,
    active_recommendation_request: session.activeRequest,
    active_market_lookup_query: marketLookupToQuery(session.marketLookup),
  }, true)

  const selectScenario = (scenarioId: 'condition_fit' | 'growth' | 'stability') => executeTurn({
    action: 'select_scenario',
    message: `${scenarioId} 시나리오를 선택합니다.`,
    history: session.history.slice(-20),
    draft: session.draft,
    context: session.context,
    assumptions: session.assumptions,
    scenario_id: scenarioId,
    selected_scenario_id: scenarioId,
    analysis_revision: session.analysisRevision,
    active_recommendation_request: null,
  }, false)

  const applyRelaxation = (option: RelaxationOption) => executeTurn({
    action: 'message',
    message: `${option.label} 조건을 탐색 조건에 반영해주세요.`,
    history: session.history.slice(-20),
    draft: { ...option.request, industry_code: option.request.industry_code },
    context: session.context,
    assumptions: session.assumptions,
    scenario_id: null,
    selected_scenario_id: null,
    analysis_revision: session.analysisRevision,
    active_recommendation_request: null,
  }, true)

  const updateAssumption = (id: string, status: AgentAssumption['status']) => {
    setSession((current) => {
      const target = current.assumptions.find((item) => item.id === id)
      const assumptions = current.assumptions.map((item) => item.id === id ? { ...item, status } : item)
      if (status !== 'rejected' || !target) return { ...current, assumptions }
      const draft = target.source_field === 'min_data_reliability'
        ? { ...current.draft, min_data_reliability: 0 }
        : current.draft
      const context = target.source_field === 'location_flexibility'
        ? { ...current.context, location_flexibility: null }
        : target.source_field === 'risk_tolerance'
          ? { ...current.context, risk_tolerance: null }
          : current.context
      return {
        ...current, assumptions, draft, context, phase: 'discovering', scenarios: [], tradeoffs: [],
        relaxationOptions: [], selectedScenarioId: null, items: [], comparison: [], recommendationReport: null, activeRequest: null,
        storeAreaCode: null, storeAnalysis: null, selectedStoreId: null,
        storeRelations: ['competitor', 'complementary', 'daily_life', 'other'], storeSearch: '', webResearch: [],
        leaseCandidates: [], leaseFinanceById: {}, selectedLeaseCandidateId: null, financeAreaCode: null,
        workspaceChats: createInitialWorkspaceChats(),
      }
    })
  }

  const confirm = () => {
    if (!isDraftReady(session.draft)) return setError('업종과 희망 조건을 먼저 알려주세요.')
    if (!session.selectedScenarioId && session.draft.performance_group_weights == null) {
      return setError('세 가지 전략 중 하나를 먼저 선택해주세요.')
    }
    return executeTurn({
      action: 'confirm_recommendation',
      message: '조건 카드를 확인했습니다. 이 조건으로 추천을 실행해주세요.',
      history: session.history.slice(-20),
      draft: session.draft,
      context: session.context,
      assumptions: session.assumptions,
      scenario_id: null,
      selected_scenario_id: session.selectedScenarioId,
      analysis_revision: session.analysisRevision,
      active_recommendation_request: null,
    }, false)
  }

  const editDraft = (draft: RecommendationDraft) => {
    setError(null)
    setSelected(null)
    setOutputPage('strategy')
    setRecommendationPage('analysis')
    setSession((current) => ({
      ...current,
      draft,
      phase: 'discovering',
      scenarios: [],
      tradeoffs: [],
      relaxationOptions: [],
      selectedScenarioId: null,
      items: [],
      comparison: [],
      recommendationReport: null,
      activeRequest: null,
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
      workspaceChats: createInitialWorkspaceChats(),
    }))
  }

  const resetConversationAndAnalysis = () => {
    if (!window.confirm('대화와 모든 분석 결과를 초기화할까요?')) return
    sessionStorage.removeItem(AGENT_SESSION_KEY)
    sessionStorage.removeItem(AGENT_V9_SESSION_KEY)
    sessionStorage.removeItem(AGENT_V8_SESSION_KEY)
    sessionStorage.removeItem(AGENT_V7_SESSION_KEY)
    sessionStorage.removeItem(AGENT_V6_SESSION_KEY)
    sessionStorage.removeItem(AGENT_V5_SESSION_KEY)
    sessionStorage.removeItem(AGENT_V4_SESSION_KEY)
    sessionStorage.removeItem(AGENT_V3_SESSION_KEY)
    sessionStorage.removeItem(AGENT_V2_SESSION_KEY)
    sessionStorage.removeItem(AGENT_LEGACY_SESSION_KEY)
    setSession({
      ...initialSession,
      history: [...initialSession.history],
      draft: { ...initialSession.draft },
      context: { ...initialSession.context },
      workspaceChats: createInitialWorkspaceChats(),
    })
    setSelected(null)
    setLookupSelectedKey(null)
    setOutputPage('strategy')
    setRecommendationPage('analysis')
    setError(null)
    setLastTurn(null)
    setStoreError(null)
    setWorkspaceError({ stores: null, finance: null })
    setLeaseEditorAreaCode(null)
    setEditingLeaseCandidateId(null)
  }

  const showMarketLookup = (index: number) => {
    const result = session.marketLookupHistory[index]
    if (!result) return
    setLookupSelectedKey(result.rows.length ? marketLookupEntityKey(result, result.rows[0]) : null)
    setOutputPage('lookup')
    setSession((current) => {
      if (index < 0 || index >= current.marketLookupHistory.length) return current
      return {
        ...current,
        marketLookup: current.marketLookupHistory[index],
        marketLookupIndex: index,
      }
    })
  }

  const openStoreExplorer = async (item: RecommendationItem) => {
    const requestContextKey = `stores:${item.area_code}:${item.industry_code}`
    const requestToken = storeRequestGuard.current.begin(requestContextKey)
    activateWorkspaceRequestContext('stores', `${requestContextKey}:none`)
    setOutputPage('recommendation')
    setRecommendationPage('stores')
    setSelected(item)
    setStoreError(null)
    setSession((current) => ({
      ...current,
      storeAreaCode: item.area_code,
      selectedStoreId: null,
      financeAreaCode: null,
      selectedLeaseCandidateId: leaseSelectionForArea(
        current.leaseCandidates, current.selectedLeaseCandidateId, item.area_code,
      ),
      workspaceChats: current.storeAreaCode === item.area_code
        ? current.workspaceChats
        : { ...current.workspaceChats, stores: createInitialWorkspaceChats().stores },
    }))
    if (session.storeAnalysis?.area_code === item.area_code && session.storeAnalysis.industry_code === item.industry_code) {
      setStoreLoading(false)
      return
    }
    setStoreLoading(true)
    try {
      const analysis = await api.areaStores(item.area_code, item.industry_code)
      if (!storeRequestGuard.current.isCurrent(requestToken)) return
      setSession((current) => current.storeAreaCode === item.area_code
        ? { ...current, storeAnalysis: analysis, selectedStoreId: null, storeSearch: '', storeRelations: ['competitor', 'complementary', 'daily_life', 'other'], webResearch: [] }
        : current)
    } catch (reason) {
      if (!storeRequestGuard.current.isCurrent(requestToken)) return
      setStoreError(reason instanceof Error ? reason.message : '상가업소 정보를 불러오지 못했습니다.')
      setSession((current) => current.storeAreaCode === item.area_code
        ? { ...current, storeAreaCode: null }
        : current)
    } finally {
      if (storeRequestGuard.current.isLatest(requestToken)) setStoreLoading(false)
    }
  }

  const runWebResearch = async (scope: 'area' | 'store', storeId?: string) => {
    if (!session.storeAreaCode || !session.storeAnalysis || !session.activeRequest) return
    const loadingKey = scope === 'area' ? 'area' : storeId || 'store'
    setResearchLoadingKey(loadingKey)
    setStoreError(null)
    try {
      const result = await api.webResearch({
        scope,
        area_code: session.storeAreaCode,
        industry_code: session.storeAnalysis.industry_code,
        store_id: storeId || null,
        active_recommendation_request: session.activeRequest,
        context: session.context,
      })
      setSession((current) => ({
        ...current,
        webResearch: [
          ...current.webResearch.filter((item) => !(item.scope === result.scope && item.area_code === result.area_code && item.store_id === result.store_id)),
          result,
        ],
      }))
    } catch (reason) {
      setStoreError(reason instanceof Error ? reason.message : '웹 리서치에 실패했습니다.')
    } finally {
      setResearchLoadingKey(null)
    }
  }

  const activeStoreArea = session.storeAreaCode
    ? session.items.find((item) => item.area_code === session.storeAreaCode) || null
    : null
  const activeStoreRequestContextKey = activeStoreArea
    ? `stores:${activeStoreArea.area_code}:${activeStoreArea.industry_code}`
    : ''
  storeRequestGuard.current.activate(activeStoreRequestContextKey)
  const activeFinanceArea = session.financeAreaCode
    ? session.items.find((item) => item.area_code === session.financeAreaCode) || null
    : null
  const leaseEditorArea = leaseEditorAreaCode
    ? session.items.find((item) => item.area_code === leaseEditorAreaCode) || null
    : null
  const editingLeaseCandidate = editingLeaseCandidateId
    ? session.leaseCandidates.find((item) => (
      item.id === editingLeaseCandidateId && item.areaCode === leaseEditorAreaCode
    )) || null
    : null
  const activeMappableLookup = session.marketLookup && isMappableLookup(session.marketLookup)
    ? session.marketLookup
    : null
  const hasStrategyContent = Boolean(
    session.context.business_description
    || session.context.target_customer
    || session.context.operating_pattern
    || session.assumptions.length
    || session.scenarios.length
    || session.tradeoffs.length
    || session.relaxationOptions.length,
  )
  const recommendationTargetArea = selected || session.items[0] || null
  const recommendationPageIndex = recommendationPageOrder.indexOf(recommendationPage)
  const previousRecommendationPage = recommendationPageOrder[recommendationPageIndex - 1] || null
  const nextRecommendationPage = recommendationPageOrder[recommendationPageIndex + 1] || null

  const changeRecommendationPage = (page: RecommendationPage) => {
    setOutputPage('recommendation')
    setRecommendationPage(page)
    if (page !== 'finance' || !recommendationTargetArea) return
    const selectedCandidateId = leaseSelectionForArea(
      session.leaseCandidates, session.selectedLeaseCandidateId, recommendationTargetArea.area_code,
    )
    activateWorkspaceRequestContext(
      'finance', `finance:${recommendationTargetArea.area_code}:${selectedCandidateId || 'none'}`,
    )
    setSession((current) => ({
      ...current,
      financeAreaCode: recommendationTargetArea.area_code,
      selectedLeaseCandidateId: leaseSelectionForArea(
        current.leaseCandidates, current.selectedLeaseCandidateId, recommendationTargetArea.area_code,
      ),
      workspaceChats: current.financeAreaCode === recommendationTargetArea.area_code
        ? current.workspaceChats
        : { ...current.workspaceChats, finance: createInitialWorkspaceChats().finance },
    }))
  }

  const openLeaseEditor = (areaCode: string, candidateId: string | null = null) => {
    const selectedCandidateId = leaseSelectionForArea(
      session.leaseCandidates, session.selectedLeaseCandidateId, areaCode,
    )
    activateWorkspaceRequestContext('finance', `finance:${areaCode}:${selectedCandidateId || 'none'}`)
    setOutputPage('recommendation')
    setRecommendationPage('finance')
    setSession((current) => ({
      ...current,
      financeAreaCode: areaCode,
      selectedLeaseCandidateId: leaseSelectionForArea(
        current.leaseCandidates, current.selectedLeaseCandidateId, areaCode,
      ),
      workspaceChats: current.financeAreaCode === areaCode
        ? current.workspaceChats
        : { ...current.workspaceChats, finance: createInitialWorkspaceChats().finance },
    }))
    setLeaseEditorAreaCode(areaCode)
    setEditingLeaseCandidateId(candidateId)
  }

  const closeLeaseEditor = () => {
    setLeaseEditorAreaCode(null)
    setEditingLeaseCandidateId(null)
  }

  const saveLeaseCandidate = (candidate: LeaseCandidateRecord): string | null => {
    setSession((current) => {
      const exists = current.leaseCandidates.some((item) => item.id === candidate.id)
      return {
        ...current,
        leaseCandidates: exists
          ? current.leaseCandidates.map((item) => item.id === candidate.id ? candidate : item)
          : [...current.leaseCandidates, candidate],
        leaseFinanceById: {
          ...current.leaseFinanceById,
          [candidate.id]: exists
            ? { ...(current.leaseFinanceById[candidate.id] || emptyFinanceState()), plan: null }
            : current.leaseFinanceById[candidate.id] || emptyFinanceState(),
        },
      }
    })
    setWorkspaceToolOutputs((current) => Object.fromEntries(
      Object.entries(current).filter(([key]) => !key.startsWith(`finance:${candidate.areaCode}:`)),
    ))
    return null
  }

  const deleteLeaseCandidate = (candidateId: string) => {
    if (!window.confirm('이 임대매물과 연결된 자금계획을 삭제할까요?')) return
    setSession((current) => {
      const leaseFinanceById = { ...current.leaseFinanceById }
      delete leaseFinanceById[candidateId]
      return {
        ...current,
        leaseCandidates: current.leaseCandidates.filter((item) => item.id !== candidateId),
        leaseFinanceById,
        selectedLeaseCandidateId: current.selectedLeaseCandidateId === candidateId ? null : current.selectedLeaseCandidateId,
      }
    })
    setWorkspaceToolOutputs((current) => Object.fromEntries(
      Object.entries(current).filter(([key]) => !(key.startsWith('finance:') && key.endsWith(`:${candidateId}`))),
    ))
  }

  const updateLeaseFinance = (candidateId: string, finance: LeaseCandidateFinanceState) => {
    setSession((current) => ({
      ...current,
      leaseFinanceById: { ...current.leaseFinanceById, [candidateId]: finance },
    }))
    setWorkspaceToolOutputs((current) => Object.fromEntries(
      Object.entries(current).filter(([key]) => !(key.startsWith('finance:') && key.endsWith(`:${candidateId}`))),
    ))
  }

  const activeFinanceCandidates = activeFinanceArea
    ? session.leaseCandidates.filter((item) => item.areaCode === activeFinanceArea.area_code)
    : []
  const activeSelectedLeaseCandidateId = leaseSelectionForArea(
    activeFinanceCandidates,
    session.selectedLeaseCandidateId,
    activeFinanceArea?.area_code || null,
  )
  const workspaceFinanceCandidates = activeSelectedLeaseCandidateId
    ? [
        ...activeFinanceCandidates.filter((item) => item.id === activeSelectedLeaseCandidateId),
        ...activeFinanceCandidates.filter((item) => item.id !== activeSelectedLeaseCandidateId),
      ].slice(0, 10)
    : activeFinanceCandidates.slice(0, 10)
  const workspaceSelectedLeaseCandidateId = leaseSelectionForArea(
    workspaceFinanceCandidates,
    activeSelectedLeaseCandidateId,
    activeFinanceArea?.area_code || null,
  )

  const workspaceEvidenceKey = (workspace: WorkspaceAgentScope) => (
    workspace === 'stores'
      ? `stores:${session.storeAreaCode || 'none'}:${activeStoreArea?.industry_code || 'none'}:${session.selectedStoreId || 'none'}`
      : `finance:${session.financeAreaCode || 'none'}:${workspaceSelectedLeaseCandidateId || 'none'}`
  )
  const storeWorkspaceContextKey = workspaceEvidenceKey('stores')
  const financeWorkspaceContextKey = workspaceEvidenceKey('finance')
  workspaceRequestGuards.current.stores.activate(storeWorkspaceContextKey)
  workspaceRequestGuards.current.finance.activate(financeWorkspaceContextKey)

  useEffect(() => {
    setWorkspaceLoading((current) => current === 'stores' ? null : current)
    setWorkspaceError((current) => current.stores == null ? current : { ...current, stores: null })
  }, [storeWorkspaceContextKey])

  useEffect(() => {
    setWorkspaceLoading((current) => current === 'finance' ? null : current)
    setWorkspaceError((current) => current.finance == null ? current : { ...current, finance: null })
  }, [financeWorkspaceContextKey])

  const workspaceState = (workspace: WorkspaceAgentScope): WorkspaceAgentState | null => {
    if (workspace === 'stores') {
      if (!activeStoreArea || !session.activeRequest) return null
      return {
        kind: 'stores',
        area_code: activeStoreArea.area_code,
        industry_code: activeStoreArea.industry_code,
        selected_store_id: session.selectedStoreId,
        active_recommendation_request: session.activeRequest,
        founder_context: session.context,
      }
    }
    if (!activeFinanceArea) return null
    return {
      kind: 'finance',
      area_code: activeFinanceArea.area_code,
      selected_candidate_id: workspaceSelectedLeaseCandidateId,
      candidates: workspaceFinanceCandidates.map((candidate) => {
        const finance = session.leaseFinanceById[candidate.id] || emptyFinanceState()
        return {
          id: candidate.id,
          area_code: candidate.areaCode,
          source_url: candidate.sourceUrl,
          listing_title: candidate.title || null,
          address: candidate.address || null,
          deposit_krw: candidate.depositKrw,
          monthly_rent_krw: candidate.monthlyRentKrw,
          management_fee_krw: candidate.managementFeeKrw,
          key_money_krw: candidate.keyMoneyKrw,
          rentable_area_sqm: candidate.rentableAreaSqm,
          floor: candidate.floor,
          additional_costs: finance.additionalCosts,
          eligibility: finance.eligibility,
        }
      }),
    }
  }

  const selectStoreForWorkspace = (selectedStoreId: string | null) => {
    activateWorkspaceRequestContext(
      'stores',
      `stores:${session.storeAreaCode || 'none'}:${activeStoreArea?.industry_code || 'none'}:${selectedStoreId || 'none'}`,
    )
    setSession((current) => ({ ...current, selectedStoreId }))
  }

  const selectLeaseCandidateForWorkspace = (selectedLeaseCandidateId: string) => {
    activateWorkspaceRequestContext(
      'finance', `finance:${session.financeAreaCode || 'none'}:${selectedLeaseCandidateId}`,
    )
    setSession((current) => ({ ...current, selectedLeaseCandidateId }))
  }

  const sendWorkspaceMessage = async (workspace: WorkspaceAgentScope, message: string) => {
    const history = session.workspaceChats[workspace]
    const state = workspaceState(workspace)
    if (!state) {
      setWorkspaceError((current) => ({ ...current, [workspace]: '먼저 분석할 상권을 선택해주세요.' }))
      return
    }
    const evidenceKey = workspaceEvidenceKey(workspace)
    const requestGuard = workspaceRequestGuards.current[workspace]
    const requestToken = requestGuard.begin(evidenceKey)
    const requestIsCurrent = () => requestGuard.isCurrent(requestToken)
    setWorkspaceLoading(workspace)
    setWorkspaceError((current) => ({ ...current, [workspace]: null }))
    setSession((current) => ({
      ...current,
      workspaceChats: {
        ...current.workspaceChats,
        [workspace]: [...current.workspaceChats[workspace], { role: 'user' as const, content: message }].slice(-20),
      },
    }))
    try {
      const response = await api.workspaceAgentTurn({
        workspace,
        message,
        history: history.slice(-20),
        state,
      })
      if (!requestIsCurrent()) return
      setWorkspaceToolOutputs((current) => requestIsCurrent()
        ? { ...current, [evidenceKey]: response.tool_outputs }
        : current)
      setSession((current) => requestIsCurrent()
        ? {
            ...current,
            workspaceChats: {
              ...current.workspaceChats,
              [workspace]: [...current.workspaceChats[workspace], { role: 'assistant' as const, content: response.assistant_message }].slice(-20),
            },
          }
        : current)
    } catch (reason) {
      if (!requestIsCurrent()) return
      setWorkspaceError((current) => requestIsCurrent()
        ? {
            ...current,
            [workspace]: reason instanceof Error ? reason.message : '페이지 전용 AI 요청에 실패했습니다.',
          }
        : current)
    } finally {
      if (requestIsCurrent()) {
        setWorkspaceLoading((current) => current === workspace ? null : current)
      }
    }
  }

  const clearWorkspaceChat = (workspace: WorkspaceAgentScope) => {
    workspaceRequestGuards.current[workspace].invalidate()
    setWorkspaceLoading((current) => current === workspace ? null : current)
    setWorkspaceError((current) => ({ ...current, [workspace]: null }))
    const evidenceKey = workspaceEvidenceKey(workspace)
    setWorkspaceToolOutputs((current) => ({ ...current, [evidenceKey]: [] }))
    setSession((current) => ({
      ...current,
      workspaceChats: {
        ...current.workspaceChats,
        [workspace]: createInitialWorkspaceChats()[workspace],
      },
    }))
  }

  if (!metadata) {
    return <main className="boot-screen"><div className="loader" /><p>{error || '상권 데이터를 불러오는 중입니다.'}</p></main>
  }

  return (
    <div className="app-shell">
      <AgentCommandCenter session={session} loading={loading} />
      <main id="top">
        <section className="workspace">
          {outputPage === 'recommendation' && recommendationPage !== 'analysis' ? (
            <WorkspaceAgentPanel
              key={recommendationPage}
              workspace={recommendationPage}
              history={session.workspaceChats[recommendationPage]}
              loading={workspaceLoading === recommendationPage}
              error={workspaceError[recommendationPage]}
              toolOutputs={workspaceToolOutputs[workspaceEvidenceKey(recommendationPage)] || []}
              onSend={(message) => sendWorkspaceMessage(recommendationPage, message)}
              onClear={() => clearWorkspaceChat(recommendationPage)}
            />
          ) : (
            <AgentPanel
              metadata={metadata}
              history={session.history}
              draft={session.draft}
              phase={session.phase}
              dataGaps={session.dataGaps}
              selectedScenarioId={session.selectedScenarioId}
              comparison={session.comparison}
              loading={loading}
              onSend={sendMessage}
              onConfirm={confirm}
              onDraftChange={editDraft}
              onReset={resetConversationAndAnalysis}
              onRunDemo={runHongdaeCafeDemo}
            />
          )}
          <div className="output-area">
            {error && <div className="error-banner" role="alert">{error} {lastTurn && <button type="button" onClick={() => executeTurn(lastTurn, false)}>다시 시도</button>}</div>}
            {storeError && <div className="error-banner" role="alert">{storeError}</div>}
            {(outputPage !== 'recommendation' || recommendationPage === 'analysis') && (
              <OutputPager
                page={outputPage}
                lookupCount={session.marketLookupHistory.length}
                scenarioCount={session.scenarios.length}
                recommendationCount={session.items.length}
                onChange={setOutputPage}
              />
            )}
            <section className="output-page" aria-live="polite">
            {outputPage === 'lookup' ? (
              session.marketLookup ? (
                <>
                  <MarketLookupCard
                    result={session.marketLookup}
                    position={session.marketLookupIndex}
                    total={session.marketLookupHistory.length}
                    onPrevious={() => showMarketLookup(session.marketLookupIndex - 1)}
                    onNext={() => showMarketLookup(session.marketLookupIndex + 1)}
                    selectedKey={lookupSelectedKey}
                    onSelect={setLookupSelectedKey}
                  />
                  {activeMappableLookup && (
                    <MarketLookupMap
                      result={activeMappableLookup}
                      selectedKey={lookupSelectedKey}
                      onSelect={setLookupSelectedKey}
                    />
                  )}
                </>
              ) : (
                <div className="page-empty-state">
                  <strong>아직 일반조회 결과가 없습니다</strong>
                  <p>대화창에서 “매출 높은 상권 5곳”처럼 바로 물어보세요.</p>
                </div>
              )
            ) : outputPage === 'strategy' ? (
              <>
                <AgentAnalysisPanels
                  context={session.context}
                  assumptions={session.assumptions}
                  explorationSummary={session.explorationSummary}
                  scenarios={session.scenarios}
                  tradeoffs={session.tradeoffs}
                  relaxationOptions={session.relaxationOptions}
                  selectedScenarioId={session.selectedScenarioId}
                  loading={loading}
                  onSelectScenario={selectScenario}
                  onApplyRelaxation={applyRelaxation}
                  onAssumptionStatus={updateAssumption}
                />
                {!hasStrategyContent && (
                  <div className="page-empty-state">
                    <strong>창업 맥락과 전략 가설을 준비합니다</strong>
                    <p>왼쪽 대화창에 준비 중인 업종을 알려주면 조건과 전략을 정리합니다.</p>
                  </div>
                )}
              </>
            ) : (
              <>
                <nav className="recommendation-page-arrows" aria-label="입지분석 페이지 이동">
                  {previousRecommendationPage && (
                    <button
                      type="button"
                      className="previous"
                      aria-label={`이전 페이지: ${recommendationPageLabels[previousRecommendationPage]}`}
                      onClick={() => changeRecommendationPage(previousRecommendationPage)}
                    >
                      <b aria-hidden="true">←</b>
                      <span><small>이전</small><strong>{recommendationPageLabels[previousRecommendationPage]}</strong></span>
                    </button>
                  )}
                  {nextRecommendationPage && (
                    <button
                      type="button"
                      className="next"
                      aria-label={`다음 페이지: ${recommendationPageLabels[nextRecommendationPage]}`}
                      onClick={() => changeRecommendationPage(nextRecommendationPage)}
                    >
                      <span><small>다음</small><strong>{recommendationPageLabels[nextRecommendationPage]}</strong></span>
                      <b aria-hidden="true">→</b>
                    </button>
                  )}
                </nav>
                <section className="recommendation-page">
                  {recommendationPage === 'analysis' ? (
                    recommendationItemsReady ? (
                      <>
                        <RecommendationMap items={session.items} selected={selected} onSelect={setSelected} onExplore={openStoreExplorer} />
                        <RecommendationResults items={session.items} selectedCode={selected?.area_code || null} onSelect={setSelected} />
                        {selected?.rental_estimate && (
                          <LeasePlanCard
                            item={selected}
                            totalStartupBudgetKrw={session.draft.total_startup_budget_krw}
                          />
                        )}
                        {session.recommendationReport && <RecommendationReportView report={session.recommendationReport} />}
                      </>
                    ) : (
                      <div className="empty-state">
                        <div className="compass">⌖</div>
                        <h2>{loading && session.phase === 'results' ? '상권 경계를 불러오는 중입니다' : 'AI와 조건을 정리하면 추천 지도가 열립니다'}</h2>
                        <p>{loading && session.phase === 'results' ? '기존 추천 결과에 실제 면적 데이터를 연결하고 있습니다.' : '왼쪽 대화창에 업종과 원하는 입지를 편하게 설명해보세요.'}</p>
                      </div>
                    )
                  ) : recommendationPage === 'stores' ? (
                    storeLoading ? (
                      <div className="empty-state"><div className="loader" /><h2>상권 내부 영업 업소를 불러오는 중입니다</h2><p>상권 경계와 공공 API 데이터를 연결하고 있습니다.</p></div>
                    ) : activeStoreArea && session.storeAnalysis?.area_code === activeStoreArea.area_code ? (
                      <AreaStoreExplorer
                        area={activeStoreArea}
                        analysis={session.storeAnalysis}
                        relations={session.storeRelations}
                        search={session.storeSearch}
                        selectedStoreId={session.selectedStoreId}
                        research={session.webResearch}
                        researchLoadingKey={researchLoadingKey}
                        leaseCandidateCount={session.leaseCandidates.filter((item) => item.areaCode === activeStoreArea.area_code).length}
                        onRelationsChange={(storeRelations: StoreRelation[]) => setSession((current) => ({ ...current, storeRelations }))}
                        onSearchChange={(storeSearch: string) => setSession((current) => ({ ...current, storeSearch }))}
                        onSelectStore={selectStoreForWorkspace}
                        onResearch={runWebResearch}
                        onAddLeaseCandidate={() => openLeaseEditor(activeStoreArea.area_code)}
                        onOpenLeaseCandidates={() => {
                          const selectedCandidateId = leaseSelectionForArea(
                            session.leaseCandidates, session.selectedLeaseCandidateId, activeStoreArea.area_code,
                          )
                          activateWorkspaceRequestContext(
                            'finance', `finance:${activeStoreArea.area_code}:${selectedCandidateId || 'none'}`,
                          )
                          setSession((current) => ({
                            ...current,
                            financeAreaCode: activeStoreArea.area_code,
                            selectedLeaseCandidateId: leaseSelectionForArea(
                              current.leaseCandidates, current.selectedLeaseCandidateId, activeStoreArea.area_code,
                            ),
                            workspaceChats: current.financeAreaCode === activeStoreArea.area_code
                              ? current.workspaceChats
                              : { ...current.workspaceChats, finance: createInitialWorkspaceChats().finance },
                          }))
                          setRecommendationPage('finance')
                        }}
                      />
                    ) : recommendationTargetArea ? (
                      <div className="page-empty-state">
                        <strong>{recommendationTargetArea.area_name} 상권의 점포를 분석할까요?</strong>
                        <p>현재 영업 중인 점포를 경쟁점·보완업종·생활시설로 나눠 지도에서 살펴봅니다.</p>
                        <button type="button" onClick={() => openStoreExplorer(recommendationTargetArea)}>점포 분석 시작</button>
                      </div>
                    ) : (
                      <div className="page-empty-state"><strong>먼저 분석할 상권이 필요합니다</strong><p>상권분석에서 추천 결과를 만든 뒤 점포 분석을 시작할 수 있습니다.</p></div>
                    )
                  ) : activeFinanceArea ? (
                    <LeaseCandidateWorkspace
                      area={activeFinanceArea}
                      candidates={activeFinanceCandidates}
                      selectedId={activeSelectedLeaseCandidateId}
                      financeById={session.leaseFinanceById}
                      onBack={() => setRecommendationPage(activeStoreArea ? 'stores' : 'analysis')}
                      onAdd={() => openLeaseEditor(activeFinanceArea.area_code)}
                      onEdit={(id) => openLeaseEditor(activeFinanceArea.area_code, id)}
                      onDelete={deleteLeaseCandidate}
                      onSelect={selectLeaseCandidateForWorkspace}
                      onFinanceChange={updateLeaseFinance}
                    />
                  ) : (
                    <div className="page-empty-state"><strong>먼저 자금계획을 세울 상권이 필요합니다</strong><p>상권분석에서 추천 결과를 만든 뒤 임대매물과 창업비를 계산할 수 있습니다.</p></div>
                  )}
                </section>
              </>
            )}
            </section>
          </div>
        </section>
      </main>
      {leaseEditorArea && <LeaseCandidateEditor area={leaseEditorArea} existing={editingLeaseCandidate} onClose={closeLeaseEditor} onSave={saveLeaseCandidate} />}
      <footer className="app-footer">
        <p>로케이션핏 · 서울 열린데이터광장·소상공인시장진흥공단 기반 분석 · 미래 매출을 보장하지 않습니다.</p>
        {showSessionExit && (
          <button className="demo-session-exit" type="button" onClick={() => void endDemoSession()}>
            접속 종료
          </button>
        )}
      </footer>
    </div>
  )
}
