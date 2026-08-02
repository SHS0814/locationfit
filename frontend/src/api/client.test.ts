import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'

describe('API client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('handles an empty 204 response when ending the demo session', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.deleteAiSession()).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/ai/session',
      expect.objectContaining({ method: 'DELETE', credentials: 'include' }),
    )
  })
})
