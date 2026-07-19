import type { AgentTurnRequest, AgentTurnResponse, ApiErrorBody, MetadataResponse, RecommendationRequest, RecommendationResponse } from '../types/api'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    const message = body.error?.message || body.detail?.[0]?.msg || '요청을 처리하지 못했습니다.'
    throw new ApiError(message, response.status, body.error?.code)
  }
  return response.json() as Promise<T>
}

export const api = {
  metadata: () => request<MetadataResponse>('/metadata'),
  recommend: (payload: RecommendationRequest) =>
    request<RecommendationResponse>('/recommendations', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  agentTurn: (payload: AgentTurnRequest) =>
    request<AgentTurnResponse>('/agent/turns', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
