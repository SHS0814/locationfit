import { useState, type FormEvent } from 'react'
import type { AgentMessage, WorkspaceAgentScope } from '../../types/api'

const workspaceCopy: Record<WorkspaceAgentScope, {
  eyebrow: string
  title: string
  description: string
  placeholder: string
  prompts: string[]
}> = {
  stores: {
    eyebrow: 'AI STORE ANALYST',
    title: '점포분석 AI',
    description: '현재 상권의 점포 구성과 선택 업소만 분석합니다.',
    placeholder: '경쟁점·보완업종·선택 업소를 물어보세요',
    prompts: ['경쟁점이 얼마나 밀집했어?', '보완업종 구성은 어때?', '선택한 업소 정보를 정리해줘'],
  },
  finance: {
    eyebrow: 'AI FUNDING ANALYST',
    title: '자금계획 AI',
    description: '임대매물 비용과 계산된 정책지원 후보만 설명합니다.',
    placeholder: '필요자금과 정책지원 후보를 물어보세요',
    prompts: ['첫해 필요자금을 설명해줘', '비용이 빠진 항목이 있어?', '정책지원 후보를 정리해줘'],
  },
}

export function WorkspaceAgentPanel({
  workspace,
  history,
  loading,
  error,
  onSend,
  onClear,
}: {
  workspace: WorkspaceAgentScope
  history: AgentMessage[]
  loading: boolean
  error: string | null
  onSend: (message: string) => void
  onClear: () => void
}) {
  const [message, setMessage] = useState('')
  const copy = workspaceCopy[workspace]
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = message.trim()
    if (!trimmed || loading) return
    setMessage('')
    onSend(trimmed)
  }

  return (
    <aside className="agent-panel workspace-agent-panel" aria-label={copy.title}>
      <div className="agent-heading">
        <div className="agent-heading-top">
          <span className="eyebrow">{copy.eyebrow}</span>
          <span className="agent-heading-actions"><button type="button" onClick={onClear} disabled={loading}>대화 초기화</button></span>
        </div>
        <h2>{copy.title}</h2>
        <p>{copy.description}</p>
      </div>

      <div className="chat-log" aria-live="polite">
        {history.map((item, index) => (
          <div key={`${item.role}-${index}`} className={`chat-message ${item.role}`}>
            <span>{item.role === 'assistant' ? 'AI' : '나'}</span><p>{item.content}</p>
          </div>
        ))}
        {loading && <div className="chat-message assistant pending"><span>AI</span><p>이 페이지의 데이터만 확인하고 있어요…</p></div>}
      </div>

      {error && <div className="workspace-agent-error" role="alert">{error}</div>}
      <form className="chat-composer" onSubmit={submit}>
        <label className="sr-only" htmlFor={`workspace-agent-message-${workspace}`}>{copy.title} 메시지</label>
        <textarea
          id={`workspace-agent-message-${workspace}`}
          rows={2}
          maxLength={2000}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={copy.placeholder}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !message.trim()}>보내기</button>
      </form>
      <div className="follow-up-prompts" aria-label={`${copy.title} 빠른 질문`}>
        {copy.prompts.map((prompt) => <button key={prompt} type="button" disabled={loading} onClick={() => onSend(prompt)}>{prompt}</button>)}
      </div>
      <small className="workspace-agent-scope">다른 단계의 질문은 해당 페이지의 AI에게 물어보세요.</small>
    </aside>
  )
}
