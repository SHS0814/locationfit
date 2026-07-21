import { useEffect, useState } from 'react'
import { api } from './api/client'
import { RecommendationMap } from './components/map/RecommendationMap'
import { AgentPanel } from './features/agent/AgentPanel'
import {
  AGENT_LEGACY_SESSION_KEY,
  AGENT_SESSION_KEY,
  AGENT_V7_SESSION_KEY,
  AGENT_V6_SESSION_KEY,
  AGENT_V5_SESSION_KEY,
  AGENT_V4_SESSION_KEY,
  AGENT_V2_SESSION_KEY,
  AGENT_V3_SESSION_KEY,
  draftToRequest,
  initialSession,
  hasAreaBoundary,
  isDraftReady,
  restoreSession,
  type AgentSession,
} from './features/agent/model'
import { RecommendationResults } from './features/recommendation/RecommendationResults'
import { RecommendationReportView } from './features/recommendation/RecommendationReport'
import { LeasePlanCard } from './features/recommendation/LeasePlanCard'
import { AreaStoreExplorer } from './features/stores/AreaStoreExplorer'
import { LeaseCandidateEditor } from './features/finance/LeaseCandidateEditor'
import { LeaseCandidateWorkspace } from './features/finance/LeaseCandidateWorkspace'
import { emptyFinanceState, hasDuplicateSourceUrl, type LeaseCandidateFinanceState, type LeaseCandidateRecord } from './features/finance/model'
import type { AgentAssumption, AgentTurnRequest, MetadataResponse, RecommendationDraft, RecommendationItem, RelaxationOption, StoreRelation } from './types/api'

export default function App() {
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null)
  const [session, setSession] = useState<AgentSession>(() => restoreSession(
    sessionStorage.getItem(AGENT_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V7_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V6_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V5_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V4_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V3_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V2_SESSION_KEY)
      || sessionStorage.getItem(AGENT_LEGACY_SESSION_KEY),
  ))
  const [selected, setSelected] = useState<RecommendationItem | null>(() => session.items[0] || null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastTurn, setLastTurn] = useState<AgentTurnRequest | null>(null)
  const [storeLoading, setStoreLoading] = useState(false)
  const [storeError, setStoreError] = useState<string | null>(null)
  const [researchLoadingKey, setResearchLoadingKey] = useState<string | null>(null)
  const [leaseEditorAreaCode, setLeaseEditorAreaCode] = useState<string | null>(null)
  const [editingLeaseCandidateId, setEditingLeaseCandidateId] = useState<string | null>(null)
  const recommendationItemsReady = session.items.length > 0 && session.items.every(hasAreaBoundary)

  useEffect(() => {
    api.metadata().then(setMetadata).catch((reason: Error) => setError(reason.message))
  }, [])

  useEffect(() => {
    sessionStorage.setItem(AGENT_SESSION_KEY, JSON.stringify(session))
  }, [session])

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
        setSession((current) => ({ ...current, items: response.recommendations }))
        setSelected(response.recommendations[0] || null)
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
      const nextSession: AgentSession = {
        schemaVersion: 8,
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
        marketLookup: response.market_lookup || null,
        storeAreaCode: preserveAnalysis && !response.recommendations.length ? session.storeAreaCode : null,
        storeAnalysis: preserveAnalysis && !response.recommendations.length ? session.storeAnalysis : null,
        selectedStoreId: preserveAnalysis && !response.recommendations.length ? session.selectedStoreId : null,
        storeRelations: preserveAnalysis && !response.recommendations.length
          ? session.storeRelations
          : ['competitor', 'complementary', 'daily_life', 'other'],
        storeSearch: preserveAnalysis && !response.recommendations.length ? session.storeSearch : '',
        webResearch: preserveAnalysis && !response.recommendations.length ? session.webResearch : [],
        leaseCandidates: preserveAnalysis && !response.recommendations.length ? session.leaseCandidates : [],
        leaseFinanceById: preserveAnalysis && !response.recommendations.length ? session.leaseFinanceById : {},
        selectedLeaseCandidateId: preserveAnalysis && !response.recommendations.length ? session.selectedLeaseCandidateId : null,
        financeAreaCode: preserveAnalysis && !response.recommendations.length ? session.financeAreaCode : null,
      }
      setSession(nextSession)
      if (response.recommendations.length) setSelected(response.recommendations[0] || null)
      else if (!preserveAnalysis) setSelected(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'AI 상담 요청에 실패했습니다.')
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
        relaxationOptions: [], selectedScenarioId: null, items: [], comparison: [], recommendationReport: null, activeRequest: null, marketLookup: null,
        storeAreaCode: null, storeAnalysis: null, selectedStoreId: null,
        storeRelations: ['competitor', 'complementary', 'daily_life', 'other'], storeSearch: '', webResearch: [],
        leaseCandidates: [], leaseFinanceById: {}, selectedLeaseCandidateId: null, financeAreaCode: null,
      }
    })
  }

  const confirm = () => {
    if (!isDraftReady(session.draft)) return setError('업종과 희망 조건을 먼저 알려주세요.')
    if (!session.selectedScenarioId) return setError('세 가지 전략 중 하나를 먼저 선택해주세요.')
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
    }))
  }

  const resetConversationAndAnalysis = () => {
    if (!window.confirm('대화와 모든 분석 결과를 초기화할까요?')) return
    sessionStorage.removeItem(AGENT_SESSION_KEY)
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
    })
    setSelected(null)
    setError(null)
    setLastTurn(null)
    setStoreError(null)
    setLeaseEditorAreaCode(null)
    setEditingLeaseCandidateId(null)
  }

  const openStoreExplorer = async (item: RecommendationItem) => {
    setStoreError(null)
    setSession((current) => ({ ...current, storeAreaCode: item.area_code, selectedStoreId: null, financeAreaCode: null }))
    if (session.storeAnalysis?.area_code === item.area_code && session.storeAnalysis.industry_code === item.industry_code) return
    setStoreLoading(true)
    try {
      const analysis = await api.areaStores(item.area_code, item.industry_code)
      setSession((current) => current.storeAreaCode === item.area_code
        ? { ...current, storeAnalysis: analysis, selectedStoreId: null, storeSearch: '', storeRelations: ['competitor', 'complementary', 'daily_life', 'other'], webResearch: [] }
        : current)
    } catch (reason) {
      setStoreError(reason instanceof Error ? reason.message : '상가업소 정보를 불러오지 못했습니다.')
      setSession((current) => ({ ...current, storeAreaCode: null }))
    } finally {
      setStoreLoading(false)
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
  const activeFinanceArea = session.financeAreaCode
    ? session.items.find((item) => item.area_code === session.financeAreaCode) || null
    : null
  const leaseEditorArea = leaseEditorAreaCode
    ? session.items.find((item) => item.area_code === leaseEditorAreaCode) || null
    : null
  const editingLeaseCandidate = editingLeaseCandidateId
    ? session.leaseCandidates.find((item) => item.id === editingLeaseCandidateId) || null
    : null

  const openLeaseEditor = (areaCode: string, candidateId: string | null = null) => {
    setLeaseEditorAreaCode(areaCode)
    setEditingLeaseCandidateId(candidateId)
  }

  const closeLeaseEditor = () => {
    setLeaseEditorAreaCode(null)
    setEditingLeaseCandidateId(null)
  }

  const saveLeaseCandidate = (candidate: LeaseCandidateRecord): string | null => {
    if (hasDuplicateSourceUrl(session.leaseCandidates, candidate)) {
      return '같은 원본 URL의 매물이 이미 후보함에 있습니다. 기존 후보를 편집해주세요.'
    }
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
  }

  const updateLeaseFinance = (candidateId: string, finance: LeaseCandidateFinanceState) => {
    setSession((current) => ({
      ...current,
      leaseFinanceById: { ...current.leaseFinanceById, [candidateId]: finance },
    }))
  }

  if (!metadata) {
    return <main className="boot-screen"><div className="loader" /><p>{error || '상권 데이터를 불러오는 중입니다.'}</p></main>
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top"><span>KB</span> 상권 나침반</a>
        <div className="data-badge"><i /> 데이터 {metadata.data_period.profile || '2025Q4'} · {metadata.artifact_version}</div>
      </header>
      <main id="top">
        <section className="hero">
          <div>
            <span className="hero-kicker">SEOUL COMMERCIAL AREA RECOMMENDER</span>
            <h1>감이 아닌 데이터로,<br /><em>내 가게의 자리</em>를 찾다</h1>
            <p>서울 1,650개 상권의 유동인구와 경쟁 환경, 과거 업종 성과를 분석합니다.</p>
          </div>
          <div className="hero-stat"><strong>1,650</strong><span>분석 상권</span><strong>63</strong><span>지원 업종</span></div>
        </section>

        <section className="workspace">
          <AgentPanel
            metadata={metadata}
            history={session.history}
            draft={session.draft}
            phase={session.phase}
            context={session.context}
            assumptions={session.assumptions}
            explorationSummary={session.explorationSummary}
            scenarios={session.scenarios}
            tradeoffs={session.tradeoffs}
            relaxationOptions={session.relaxationOptions}
            dataGaps={session.dataGaps}
            selectedScenarioId={session.selectedScenarioId}
            comparison={session.comparison}
            marketLookup={session.marketLookup}
            loading={loading}
            onSend={sendMessage}
            onConfirm={confirm}
            onSelectScenario={selectScenario}
            onApplyRelaxation={applyRelaxation}
            onAssumptionStatus={updateAssumption}
            onDraftChange={editDraft}
            onReset={resetConversationAndAnalysis}
          />
          <div className="output-area">
            {error && <div className="error-banner" role="alert">{error} {lastTurn && <button type="button" onClick={() => executeTurn(lastTurn, false)}>다시 시도</button>}</div>}
            {storeError && <div className="error-banner" role="alert">{storeError}</div>}
            {activeFinanceArea ? (
              <LeaseCandidateWorkspace
                area={activeFinanceArea}
                candidates={session.leaseCandidates.filter((item) => item.areaCode === activeFinanceArea.area_code)}
                selectedId={session.selectedLeaseCandidateId}
                financeById={session.leaseFinanceById}
                onBack={() => setSession((current) => ({ ...current, financeAreaCode: null }))}
                onAdd={() => openLeaseEditor(activeFinanceArea.area_code)}
                onEdit={(id) => openLeaseEditor(activeFinanceArea.area_code, id)}
                onDelete={deleteLeaseCandidate}
                onSelect={(selectedLeaseCandidateId) => setSession((current) => ({ ...current, selectedLeaseCandidateId }))}
                onFinanceChange={updateLeaseFinance}
              />
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
                onBack={() => setSession((current) => ({ ...current, storeAreaCode: null, selectedStoreId: null }))}
                onRelationsChange={(storeRelations: StoreRelation[]) => setSession((current) => ({ ...current, storeRelations }))}
                onSearchChange={(storeSearch: string) => setSession((current) => ({ ...current, storeSearch }))}
                onSelectStore={(selectedStoreId: string | null) => setSession((current) => ({ ...current, selectedStoreId }))}
                onResearch={runWebResearch}
                onAddLeaseCandidate={() => openLeaseEditor(activeStoreArea.area_code)}
                onOpenLeaseCandidates={() => setSession((current) => ({ ...current, financeAreaCode: activeStoreArea.area_code }))}
              />
            ) : storeLoading ? (
              <div className="empty-state"><div className="loader" /><h2>상권 내부 영업 업소를 불러오는 중입니다</h2><p>상권 경계와 공공 API 데이터를 연결하고 있습니다.</p></div>
            ) : recommendationItemsReady ? (
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
            )}
          </div>
        </section>
      </main>
      {leaseEditorArea && <LeaseCandidateEditor area={leaseEditorArea} existing={editingLeaseCandidate} onClose={closeLeaseEditor} onSave={saveLeaseCandidate} />}
      <footer>KB AI Challenge · 서울 열린데이터광장·소상공인시장진흥공단 기반 분석 · 미래 매출을 보장하지 않습니다.</footer>
    </div>
  )
}
