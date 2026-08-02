import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { AiAccessGate } from './AiAccessGate'

vi.mock('../../api/client', () => ({
  api: { createAiSession: vi.fn() },
}))

describe('AiAccessGate', () => {
  it('shows a minimal password-only entry screen for the protected demo', () => {
    const html = renderToStaticMarkup(<AiAccessGate onAuthenticated={() => undefined} />)

    expect(html).not.toContain('심사위원 전용 데모')
    expect(html).not.toContain('로케이션핏 데모 접속')
    expect(html).not.toContain('운영자가 전달한 비밀번호')
    expect(html).toContain('type="password"')
    expect(html).toContain('비밀번호는 브라우저 저장소에 보관되지 않으며')
  })
})
