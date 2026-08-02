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
      <section className="ai-access-card" aria-label="데모 접속">
        <form onSubmit={submit}>
          <label htmlFor="ai-access-code">비밀번호</label>
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
        <p className="ai-access-note">
          비밀번호는 브라우저 저장소에 보관되지 않으며, 세션이 만료될 때까지 다시 입력하지 않아도 됩니다.
        </p>
      </section>
    </main>
  )
}
