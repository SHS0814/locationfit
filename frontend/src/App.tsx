import { useEffect, useState } from 'react'
import { api } from './api/client'
import { RecommendationMap } from './components/map/RecommendationMap'
import { AgentPanel } from './features/agent/AgentPanel'
import {
  AGENT_LEGACY_SESSION_KEY,
  AGENT_SESSION_KEY,
  AGENT_V2_SESSION_KEY,
  draftToRequest,
  isDraftReady,
  restoreSession,
  type AgentSession,
} from './features/agent/model'
import { RecommendationResults } from './features/recommendation/RecommendationResults'
import { RecommendationReportView } from './features/recommendation/RecommendationReport'
import type { AgentAssumption, AgentTurnRequest, MetadataResponse, RecommendationDraft, RecommendationItem, RelaxationOption } from './types/api'

export default function App() {
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null)
  const [session, setSession] = useState<AgentSession>(() => restoreSession(
    sessionStorage.getItem(AGENT_SESSION_KEY)
      || sessionStorage.getItem(AGENT_V2_SESSION_KEY)
      || sessionStorage.getItem(AGENT_LEGACY_SESSION_KEY),
  ))
  const [selected, setSelected] = useState<RecommendationItem | null>(() => session.items[0] || null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastTurn, setLastTurn] = useState<AgentTurnRequest | null>(null)

  useEffect(() => {
    api.metadata().then(setMetadata).catch((reason: Error) => setError(reason.message))
  }, [])

  useEffect(() => {
    sessionStorage.setItem(AGENT_SESSION_KEY, JSON.stringify(session))
  }, [session])

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
      const keepActiveResults = response.phase === 'results'
      const items = response.recommendations.length
        ? response.recommendations
        : keepActiveResults ? session.items : []
      const activeRequest = response.recommendations.length
        ? draftToRequest(response.draft)
        : keepActiveResults ? session.activeRequest : null
      const nextSession: AgentSession = {
        schemaVersion: 3,
        history: [...visibleHistory, { role: 'assistant' as const, content: response.assistant_message }].slice(-20),
        draft: response.draft,
        phase: response.phase,
        context: response.context,
        assumptions: response.assumptions,
        explorationSummary: response.exploration_summary,
        scenarios: response.scenarios.length ? response.scenarios : keepActiveResults ? session.scenarios : [],
        tradeoffs: response.tradeoffs.length ? response.tradeoffs : keepActiveResults ? session.tradeoffs : [],
        relaxationOptions: response.relaxation_options.length ? response.relaxation_options : keepActiveResults ? session.relaxationOptions : [],
        dataGaps: response.data_gaps,
        selectedScenarioId: response.selected_scenario_id,
        analysisRevision: response.analysis_revision,
        items,
        comparison: response.comparison.length
          ? response.comparison
          : keepActiveResults ? session.comparison : [],
        recommendationReport: response.recommendation_report
          || (keepActiveResults ? session.recommendationReport : null),
        activeRequest,
      }
      setSession(nextSession)
      if (response.recommendations.length) setSelected(response.recommendations[0] || null)
      else if (!keepActiveResults) setSelected(null)
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
        relaxationOptions: [], selectedScenarioId: null, items: [], comparison: [], recommendationReport: null, activeRequest: null,
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
            loading={loading}
            onSend={sendMessage}
            onConfirm={confirm}
            onSelectScenario={selectScenario}
            onApplyRelaxation={applyRelaxation}
            onAssumptionStatus={updateAssumption}
            onDraftChange={editDraft}
          />
          <div className="output-area">
            {error && <div className="error-banner" role="alert">{error} {lastTurn && <button type="button" onClick={() => executeTurn(lastTurn, false)}>다시 시도</button>}</div>}
            {session.items.length ? (
              <>
                <RecommendationMap items={session.items} selected={selected} onSelect={setSelected} />
                <RecommendationResults items={session.items} selectedCode={selected?.area_code || null} onSelect={setSelected} />
                {session.recommendationReport && <RecommendationReportView report={session.recommendationReport} />}
              </>
            ) : (
              <div className="empty-state">
                <div className="compass">⌖</div>
                <h2>AI와 조건을 정리하면 추천 지도가 열립니다</h2>
                <p>왼쪽 대화창에 업종과 원하는 입지를 편하게 설명해보세요.</p>
              </div>
            )}
          </div>
        </section>
      </main>
      <footer>KB AI Challenge · 서울 열린데이터광장 기반 분석 · 미래 매출을 보장하지 않습니다.</footer>
    </div>
  )
}
