import type { AgentSession } from './model'
import { createAgentBriefing, deriveAgentCommandStages } from './model'

interface Props {
  session: AgentSession
  loading: boolean
}

export function AgentCommandCenter({ session, loading }: Props) {
  const stages = deriveAgentCommandStages(session, loading)
  const briefing = createAgentBriefing(session, stages)
  const activeStage = stages.find((stage) => stage.status === 'active')
  const completedCount = stages.filter((stage) => stage.status === 'complete').length

  return (
    <section className="agent-command-center" aria-labelledby="agent-command-title">
      <header className="command-center-header">
        <div className="ai-orchestrator-mark" aria-hidden="true"><span>AI</span></div>
        <div>
          <span className="eyebrow">{briefing.eyebrow}</span>
          <h2 id="agent-command-title">{briefing.title}</h2>
          <p>{briefing.summary}</p>
        </div>
        <span className={loading ? 'command-status working' : 'command-status'}>
          <i aria-hidden="true" />
          {loading ? 'AI 작업 중' : activeStage ? `${activeStage.label} 대기` : '분석 완료'}
        </span>
      </header>

      {briefing.evidence.length > 0 && (
        <ul className="ai-brief-evidence" aria-label="AI 추천 핵심 근거">
          {briefing.evidence.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}

      <ol className="agent-stage-list" aria-label={`AI 업무 진행 단계, ${stages.length}단계 중 ${completedCount}단계 완료`}>
        {stages.map((stage, index) => (
          <li key={stage.id} className={stage.status} aria-current={stage.status === 'active' ? 'step' : undefined}>
            <span className="stage-index" aria-hidden="true">{stage.status === 'complete' ? '✓' : index + 1}</span>
            <span className="stage-copy"><strong>{stage.label}</strong><small>{stage.detail}</small></span>
          </li>
        ))}
      </ol>
    </section>
  )
}
