import { useState, type FormEvent } from 'react'
import { api } from '../../api/client'

interface AiAccessGateProps {
  onAuthenticated: () => void
}

export function AiAccessGate({ onAuthenticated }: AiAccessGateProps) {
  const [accessCode, setAccessCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!accessCode.trim() || loading) return
    setLoading(true)
    setError(null)
    try {
      const status = await api.createAiSession(accessCode)
      setAccessCode('')
      if (status.authenticated) onAuthenticated()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '접근 코드를 확인하지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="ai-access-shell">
      <section className="ai-access-card" aria-labelledby="ai-access-title">
        <p className="eyebrow">보호된 대회 데모</p>
        <h1 id="ai-access-title">로케이션핏 AI 접속</h1>
        <p>AI 상담과 웹 리서치 비용을 보호하기 위해 운영자가 전달한 접근 코드가 필요합니다.</p>
        <form onSubmit={submit}>
          <label htmlFor="ai-access-code">접근 코드</label>
          <input
            id="ai-access-code"
            type="password"
            value={accessCode}
            onChange={(event) => setAccessCode(event.target.value)}
            autoComplete="current-password"
            maxLength={256}
            autoFocus
          />
          {error && <p className="ai-access-error" role="alert">{error}</p>}
          <button type="submit" disabled={!accessCode.trim() || loading}>
            {loading ? '확인 중…' : '접속하기'}
          </button>
        </form>
        <p className="ai-access-note">접근 코드는 브라우저 저장소에 보관되지 않습니다.</p>
      </section>
    </main>
  )
}
