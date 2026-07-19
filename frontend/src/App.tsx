import { useEffect, useState } from 'react'
import { api } from './api/client'
import { RecommendationMap } from './components/map/RecommendationMap'
import { AgentPanel } from './features/agent/AgentPanel'
import {
  AGENT_SESSION_KEY,
  draftToRequest,
  isDraftReady,
  restoreSession,
  type AgentSession,
} from './features/agent/model'
import { RecommendationResults } from './features/recommendation/RecommendationResults'
import type { AgentTurnRequest, MetadataResponse, RecommendationDraft, RecommendationItem } from './types/api'

export default function App() {
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null)
  const [session, setSession] = useState<AgentSession>(() => restoreSession(sessionStorage.getItem(AGENT_SESSION_KEY)))
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
        history: [...visibleHistory, { role: 'assistant' as const, content: response.assistant_message }].slice(-20),
        draft: response.draft,
        phase: response.phase,
        items,
        comparison: response.comparison.length
          ? response.comparison
          : keepActiveResults ? session.comparison : [],
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
    active_recommendation_request: session.activeRequest,
  }, true)

  const confirm = () => {
    if (!isDraftReady(session.draft)) return setError('업종과 희망 조건을 먼저 알려주세요.')
    return executeTurn({
      action: 'confirm_recommendation',
      message: '조건 카드를 확인했습니다. 이 조건으로 추천을 실행해주세요.',
      history: session.history.slice(-20),
      draft: session.draft,
      active_recommendation_request: null,
    }, false)
  }

  const editDraft = (draft: RecommendationDraft) => {
    setError(null)
    setSelected(null)
    setSession((current) => ({
      ...current,
      draft,
      phase: isDraftReady(draft) ? 'ready_for_confirmation' : 'gathering',
      items: [],
      comparison: [],
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
            comparison={session.comparison}
            loading={loading}
            onSend={sendMessage}
            onConfirm={confirm}
            onDraftChange={editDraft}
          />
          <div className="output-area">
            {error && <div className="error-banner" role="alert">{error} {lastTurn && <button type="button" onClick={() => executeTurn(lastTurn, false)}>다시 시도</button>}</div>}
            {session.items.length ? (
              <>
                <RecommendationMap items={session.items} selected={selected} onSelect={setSelected} />
                <RecommendationResults items={session.items} selectedCode={selected?.area_code || null} onSelect={setSelected} />
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
