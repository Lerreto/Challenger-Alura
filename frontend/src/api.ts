export type DocumentRecord = {
  id: string
  title: string
  category: string
  version: string
  owner: string
  language: string
  original_filename: string
  sha256: string
  status: string
  chunk_count: number
  uploaded_at: string
  error: string | null
}

export type Health = {
  status: string
  index: string
  llm: string
  provider: string
  model: string
  embedding_model: string
  documents: number
  chunks: number
}

export type Source = {
  chunk_id: string
  document_id: string
  title: string
  location: string
  excerpt: string
  score: number
}

export type ChatResult = {
  status: 'answered' | 'insufficient_context'
  answer: string
  sources: Source[]
  session_id: string
  message_id: string
}

export type ChatHistoryMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  status: string | null
  sources: Source[]
  created_at: string
}

export type ChatHistory = {
  session_id: string
  messages: ChatHistoryMessage[]
}

export type ChatSession = {
  session_id: string
  title: string
  message_count: number
  started_at: string
  updated_at: string
}

export class ApiError extends Error {
  code: string
  status: number

  constructor(message: string, code = 'request_failed', status = 500) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let message = 'No pudimos completar la solicitud. Intentá nuevamente.'
    let code = 'request_failed'
    try {
      const body = await response.json()
      message = body.detail?.message ?? body.message ?? message
      code = body.detail?.code ?? body.code ?? code
    } catch {
      // Keep the safe fallback when a proxy returns a non-JSON error page.
    }
    throw new ApiError(message, code, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function getHealth(): Promise<Health> {
  const response = await fetch('/api/health/ready')
  if (response.ok) return response.json() as Promise<Health>

  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ApiError('No pudimos consultar el estado del servicio.', 'health_unavailable', response.status)
  }
  if (
    response.status === 503
    && typeof body === 'object'
    && body !== null
    && 'index' in body
    && 'llm' in body
  ) {
    return body as Health
  }
  const payload = body as { detail?: { code?: string; message?: string }; message?: string }
  throw new ApiError(
    payload.detail?.message ?? payload.message ?? 'No pudimos consultar el estado del servicio.',
    payload.detail?.code ?? 'health_unavailable',
    response.status,
  )
}

export const api = {
  health: getHealth,
  documents: () => request<DocumentRecord[]>('/api/documents'),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentRecord>('/api/documents', { method: 'POST', body: form })
  },
  deleteDocument: (id: string) =>
    request<void>(`/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  reindex: () => request<{ documents: number }>('/api/documents/reindex', { method: 'POST' }),
  chat: (question: string, sessionId: string | null) =>
    request<ChatResult>('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sessionId ? { question, session_id: sessionId } : { question }),
    }),
  chatSessions: () => request<ChatSession[]>('/api/chat/sessions'),
  chatHistory: (sessionId: string) =>
    request<ChatHistory>(`/api/chat/history/${encodeURIComponent(sessionId)}`),
  clearChatHistory: (sessionId: string) =>
    request<void>(`/api/chat/history/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
}
