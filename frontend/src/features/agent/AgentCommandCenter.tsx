import type { AgentSession } from './model'
import { deriveAgentCommandStages } from './model'

interface Props {
  session: AgentSession
  loading: boolean
}

export function AgentCommandCenter({ session, loading }: Props) {
  const stages = deriveAgentCommandStages(session, loading)
  const completedCount = stages.filter((stage) => stage.status === 'complete').length

  return (
    <header className="agent-flow-header">
      <ol className="agent-stage-list" aria-label={`AI 업무 진행 단계, ${stages.length}단계 중 ${completedCount}단계 완료`}>
        {stages.map((stage, index) => (
          <li key={stage.id} className={stage.status} aria-current={stage.status === 'active' ? 'step' : undefined}>
            <span className="stage-index" aria-hidden="true">{stage.status === 'complete' ? '✓' : index + 1}</span>
            <span className="stage-copy"><strong>{stage.label}</strong><small>{stage.detail}</small></span>
          </li>
        ))}
      </ol>
    </header>
  )
}
