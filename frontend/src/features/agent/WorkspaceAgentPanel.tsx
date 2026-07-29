import { useState, type FormEvent } from 'react'
import { MarkdownContent } from '../../components/MarkdownContent'
import type { AgentMessage, WorkspaceAgentScope, WorkspaceToolOutput } from '../../types/api'

const record = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
)

const won = (value: unknown) => typeof value === 'number'
  ? `${Math.round(value).toLocaleString('ko-KR')}원`
  : '-'

function ToolEvidenceCard({ output }: { output: WorkspaceToolOutput }) {
  const payload = record(output.payload)
  const summary = record(payload.summary)
  const funding = record(payload.funding)
  const store = record(payload.store)
  const policy = record(payload.policy_candidate)
  const comparisons = Array.isArray(payload.comparisons) ? payload.comparisons.map(record) : []
  const sources = Array.isArray(payload.sources) ? payload.sources.map(record) : []

  return (
    <article className={`workspace-tool-card ${output.status}`}>
      <header><strong>{output.title}</strong><span>{output.status === 'succeeded' ? '도구 확인' : '확인 필요'}</span></header>
      {output.kind === 'store_summary' && <dl>
        <div><dt>전체 업소</dt><dd>{String(summary.total_count ?? '-')}개</dd></div>
        <div><dt>경쟁점</dt><dd>{String(summary.competitor_count ?? '-')}개</dd></div>
        <div><dt>경쟁점 밀도</dt><dd>{String(summary.competitor_density_per_sqkm ?? '-')}개/㎢</dd></div>
      </dl>}
      {output.kind === 'store_detail' && <p>{String(store.name ?? '업소')} · {String(store.industry_small_name ?? store.industry_middle_name ?? '업종 미확인')} · {String(store.road_address ?? store.lot_address ?? '주소 미확인')}</p>}
      {output.kind === 'finance_scenario' && <dl>
        <div><dt>첫해 필요자금</dt><dd>{won(funding.total_first_year_cash_need_krw)}</dd></div>
        <div><dt>부족자금</dt><dd>{won(funding.funding_gap_krw)}</dd></div>
        <div><dt>자기자본 비율</dt><dd>{typeof funding.own_capital_ratio === 'number' ? `${(funding.own_capital_ratio * 100).toFixed(1)}%` : '-'}</dd></div>
      </dl>}
      {output.kind === 'finance_comparison' && comparisons.map((item) => {
        const itemFunding = record(item.funding)
        return <p key={String(item.candidate_id)}><strong>{String(item.listing_title ?? item.candidate_id)}</strong> · 필요 {won(itemFunding.total_first_year_cash_need_krw)} · 부족 {won(itemFunding.funding_gap_krw)}</p>
      })}
      {output.kind === 'policy_detail' && <p><strong>{String(policy.name ?? '정책지원')}</strong> · {String(policy.provider ?? '기관 확인 필요')} · {String(policy.status ?? '')}</p>}
      {output.kind === 'web_research' && <>
        <p>{String(payload.summary ?? '')}</p>
        {sources.length > 0 && <div className="workspace-tool-sources">{sources.slice(0, 5).map((source) => <a key={String(source.url)} href={String(source.url)} target="_blank" rel="noreferrer">{String(source.title ?? source.url)}</a>)}</div>}
      </>}
      {output.as_of && <small>기준: {output.as_of}</small>}
      {output.assumptions.length > 0 && <p className="workspace-tool-assumptions">가정: {output.assumptions.join(' · ')}</p>}
      {output.warnings.map((warning) => <p key={warning} className="workspace-tool-warning">{warning}</p>)}
    </article>
  )
}

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
    description: '현재 상권의 점포 도구를 직접 조회하고, 요청하면 최신 외부 정보도 조사합니다.',
    placeholder: '경쟁점·보완업종·선택 업소를 물어보세요',
    prompts: ['경쟁점이 얼마나 밀집했어?', '보완업종 구성은 어때?', '선택한 업소 정보를 정리해줘'],
  },
  finance: {
    eyebrow: 'AI FUNDING ANALYST',
    title: '자금계획 AI',
    description: '임대매물의 필요자금·가정 시나리오·정책지원 후보를 도구로 계산합니다.',
    placeholder: '필요자금과 정책지원 후보를 물어보세요',
    prompts: ['첫해 필요자금을 계산해줘', '후보별 자금을 비교해줘', '인테리어비를 바꾼 가정도 계산해줘'],
  },
}

export function WorkspaceAgentPanel({
  workspace,
  history,
  loading,
  error,
  toolOutputs,
  onSend,
  onClear,
}: {
  workspace: WorkspaceAgentScope
  history: AgentMessage[]
  loading: boolean
  error: string | null
  toolOutputs: WorkspaceToolOutput[]
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
            <span>{item.role === 'assistant' ? 'AI' : '나'}</span>
            {item.role === 'assistant'
              ? <MarkdownContent content={item.content} />
              : <p>{item.content}</p>}
          </div>
        ))}
        {loading && <div className="chat-message assistant pending"><span>AI</span><p>이 페이지의 데이터만 확인하고 있어요…</p></div>}
      </div>

      {error && <div className="workspace-agent-error" role="alert">{error}</div>}
      {toolOutputs.length > 0 && <section className="workspace-tool-results" aria-label="AI 도구 실행 근거">
        <h3>도구 실행 근거</h3>
        {toolOutputs.map((output, index) => <ToolEvidenceCard key={`${output.kind}-${index}`} output={output} />)}
      </section>}
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
