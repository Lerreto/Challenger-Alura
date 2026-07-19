import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const documentRecord = {
  id: 'doc-1',
  title: 'Política de reembolsos',
  category: 'Posventa',
  version: '1.0',
  owner: 'Soporte',
  language: 'es-CO',
  original_filename: 'reembolsos.md',
  sha256: 'abc',
  status: 'ready',
  chunk_count: 4,
  uploaded_at: '2026-07-18T10:00:00Z',
  error: null,
}

const health = {
  status: 'ready',
  index: 'ready',
  llm: 'configured',
  provider: 'groq',
  model: 'llama-3.1-8b-instant',
  embedding_model: 'multilingual-MiniLM',
  documents: 1,
  chunks: 4,
}

function response(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function mockApi(options?: {
  documents?: typeof documentRecord[]
  chat?: unknown
  uploadError?: boolean
  history?: unknown
  sessions?: unknown
}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    if (url.endsWith('/api/health/ready')) return response(health)
    if (url.endsWith('/api/documents') && (!init?.method || init.method === 'GET')) {
      return response(options?.documents ?? [documentRecord])
    }
    if (url.endsWith('/api/documents') && init?.method === 'POST') {
      return options?.uploadError
        ? response({ detail: { message: 'Formato no compatible.' } }, 415)
        : response(documentRecord, 201)
    }
    if (url.endsWith('/api/chat/sessions')) return response(options?.sessions ?? [])
    if (url.includes('/api/chat/history/')) {
      if (init?.method === 'DELETE') return response(null, 204)
      return response(options?.history ?? { session_id: 'session-123', messages: [] })
    }
    if (url.endsWith('/api/chat')) {
      return response(
        options?.chat ?? {
          status: 'answered',
          answer: 'El reembolso tarda hasta 10 días hábiles.',
          session_id: 'session-123',
          message_id: 'msg-1',
          sources: [
            {
              document_id: 'doc-1',
              chunk_id: 'chunk-1',
              title: 'Política de reembolsos',
              location: 'Sección 8',
              excerpt: 'Procesamos el reembolso dentro de 10 días hábiles.',
              score: 0.91,
            },
          ],
        },
      )
    }
    if (url.endsWith('/reindex')) return response({ documents: 1 })
    if (url.includes('/api/documents/')) return response(null, 204)
    return response({})
  })
}

describe('Nébula RAG workspace', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it('renders the document library, loading and empty state', async () => {
    let resolveDocuments: (value: Response) => void = () => undefined
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/api/health/ready')) return response(health)
      if (url.endsWith('/api/chat/sessions')) return response([])
      return new Promise<Response>((resolve) => {
        resolveDocuments = resolve
      })
    })
    render(<App />)
    expect(screen.getByText('Cargando documentos…')).toBeInTheDocument()
    resolveDocuments(await response([]))
    expect(await screen.findByText('Todavía no hay documentos')).toBeInTheDocument()
  })

  it('offers an accessible dropzone and reports upload success', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    const input = screen.getByLabelText('Seleccionar documentos para cargar')
    await user.upload(input, new File(['# Política'], 'politica.md', { type: 'text/markdown' }))
    expect(await screen.findByText('politica.md quedó indexado.')).toBeInTheDocument()
    expect(screen.getByText('Política de reembolsos')).toBeInTheDocument()
  })

  it('explains upload errors without losing the library', async () => {
    mockApi({ uploadError: true })
    const user = userEvent.setup()
    render(<App />)
    await user.upload(
      screen.getByLabelText('Seleccionar documentos para cargar'),
      new File(['PDF inválido'], 'archivo.pdf', { type: 'application/pdf' }),
    )
    expect(await screen.findByText('Formato no compatible.')).toHaveAttribute('role', 'alert')
  })

  it('submits chat, shows loading, answer and verified sources', async () => {
    let resolveChat: (value: Response) => void = () => undefined
    mockApi()
    vi.mocked(fetch).mockImplementation((input, init) => {
      const url = String(input)
      if (url.endsWith('/api/chat')) {
        return new Promise<Response>((resolve) => {
          resolveChat = resolve
        })
      }
      if (url.endsWith('/api/health/ready')) return response(health)
      if (url.endsWith('/api/documents')) return response([documentRecord])
      return response({})
    })
    const user = userEvent.setup()
    render(<App />)
    const composer = screen.getByLabelText('Escribí tu pregunta')
    await user.type(composer, '¿Cuánto tarda un reembolso?')
    await user.click(screen.getByRole('button', { name: 'Enviar pregunta' }))
    expect(screen.getByText('Buscando evidencia…')).toBeInTheDocument()
    resolveChat(
      await response({
        status: 'answered',
        answer: 'El reembolso tarda 10 días hábiles.',
        session_id: 'session-123',
        message_id: 'msg-1',
        sources: [
          {
            document_id: 'doc-1',
            chunk_id: 'chunk-1',
            title: 'Política de reembolsos',
            location: 'Sección 8',
            excerpt: 'Dentro de 10 días hábiles.',
            score: 0.91,
          },
        ],
      }),
    )
    expect(await screen.findByText('El reembolso tarda 10 días hábiles.')).toBeInTheDocument()
    const sources = screen.getByLabelText('Fuentes verificadas')
    await user.click(within(sources).getByText('Política de reembolsos'))
    expect(screen.getByText('Dentro de 10 días hábiles.')).toBeInTheDocument()
  })

  it('distinguishes deterministic fallback from errors', async () => {
    mockApi({
      chat: {
        status: 'insufficient_context',
        answer: 'No encontré información suficiente en los documentos disponibles para responder esa pregunta.',
        session_id: 'session-123',
        message_id: 'msg-2',
        sources: [],
      },
    })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByLabelText('Escribí tu pregunta'), '¿Cuál es el clima?')
    await user.click(screen.getByRole('button', { name: 'Enviar pregunta' }))
    expect((await screen.findByText(/No encontré información suficiente/)).closest('article')).toHaveAttribute(
      'data-status',
      'insufficient_context',
    )
  })

  it('uses Enter to send and Shift+Enter for a newline', async () => {
    const api = mockApi()
    const user = userEvent.setup()
    render(<App />)
    const composer = screen.getByLabelText('Escribí tu pregunta')
    await user.type(composer, 'Primera línea{shift>}{enter}{/shift}segunda línea')
    expect(composer).toHaveValue('Primera línea\nsegunda línea')
    expect(api.mock.calls.some(([url]) => String(url).endsWith('/api/chat'))).toBe(false)
    await user.type(composer, '{enter}')
    await waitFor(() => {
      expect(api.mock.calls.some(([url]) => String(url).endsWith('/api/chat'))).toBe(true)
    })
  })

  it('marks disconnected health as unknown instead of missing credentials', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      if (String(input).endsWith('/api/health/ready')) return Promise.reject(new Error('offline'))
      return response([])
    })
    render(<App />)

    expect(await screen.findByText('sin conexión')).toBeInTheDocument()
    expect(screen.queryByText('sin clave')).not.toBeInTheDocument()
  })

  it('preserves a valid degraded readiness payload returned with 503', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      if (String(input).endsWith('/api/health/ready')) {
        return response({ ...health, status: 'degraded', index: 'error' }, 503)
      }
      return response([])
    })
    render(<App />)

    expect(await screen.findByText('error')).toBeInTheDocument()
    expect(screen.getByText('activo')).toBeInTheDocument()
    expect(screen.queryByText('sin conexión')).not.toBeInTheDocument()
  })

  it('makes the closed mobile drawer inert and manages Escape focus restoration', async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('840px'),
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }))
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    const drawer = screen.getByTestId('library-drawer')
    const trigger = screen.getByRole('button', { name: 'Abrir documentos' })

    expect(drawer).toHaveAttribute('aria-hidden', 'true')
    expect(drawer).toHaveAttribute('inert')
    await user.click(trigger)
    expect(drawer).toHaveAttribute('aria-hidden', 'false')
    expect(screen.getByRole('button', { name: 'Cerrar documentos' })).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(drawer).toHaveAttribute('aria-hidden', 'true')
    expect(trigger).toHaveFocus()
  })

  it('resumes the persisted conversation and starts a new one without deleting it', async () => {
    window.localStorage.setItem('nebula-chat-session', 'session-123')
    const api = mockApi({
      history: {
        session_id: 'session-123',
        messages: [
          {
            id: 'msg-user-1',
            role: 'user',
            content: '¿Cuánto tarda un reembolso?',
            status: null,
            sources: [],
            created_at: '2026-07-18T10:00:00Z',
          },
          {
            id: 'msg-assistant-1',
            role: 'assistant',
            content: 'El reembolso tarda 10 días hábiles.',
            status: 'answered',
            sources: [],
            created_at: '2026-07-18T10:00:05Z',
          },
        ],
      },
      sessions: [
        {
          session_id: 'session-123',
          title: '¿Cuánto tarda un reembolso?',
          message_count: 2,
          started_at: '2026-07-18T10:00:00Z',
          updated_at: '2026-07-18T10:00:05Z',
        },
      ],
    })
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText('El reembolso tarda 10 días hábiles.')).toBeInTheDocument()
    expect(screen.getAllByText('¿Cuánto tarda un reembolso?').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Conversaciones guardadas')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Nueva conversación' }))
    await waitFor(() => {
      expect(screen.queryByText('El reembolso tarda 10 días hábiles.')).not.toBeInTheDocument()
    })
    expect(window.localStorage.getItem('nebula-chat-session')).toBeNull()
    expect(
      api.mock.calls.some(([, init]) => init?.method === 'DELETE'),
    ).toBe(false)
  })

  it('deletes the current conversation only from the explicit delete action', async () => {
    window.localStorage.setItem('nebula-chat-session', 'session-123')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const api = mockApi({
      history: {
        session_id: 'session-123',
        messages: [
          {
            id: 'msg-user-1',
            role: 'user',
            content: '¿Qué cubre la garantía extendida?',
            status: null,
            sources: [],
            created_at: '2026-07-18T10:00:00Z',
          },
        ],
      },
    })
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText('¿Qué cubre la garantía extendida?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Eliminar conversación' }))
    await waitFor(() => {
      expect(
        api.mock.calls.some(
          ([url, init]) => String(url).includes('/api/chat/history/session-123') && init?.method === 'DELETE',
        ),
      ).toBe(true)
    })
    expect(window.localStorage.getItem('nebula-chat-session')).toBeNull()
  })

  it('switches to a stored conversation from the session selector', async () => {
    const api = mockApi({
      sessions: [
        {
          session_id: 'session-999',
          title: 'Garantía de portátiles',
          message_count: 2,
          started_at: '2026-07-18T09:00:00Z',
          updated_at: '2026-07-18T09:00:05Z',
        },
      ],
      history: {
        session_id: 'session-999',
        messages: [
          {
            id: 'msg-user-9',
            role: 'user',
            content: '¿Qué cubre la garantía?',
            status: null,
            sources: [],
            created_at: '2026-07-18T09:00:00Z',
          },
          {
            id: 'msg-assistant-9',
            role: 'assistant',
            content: 'La garantía cubre 12 meses.',
            status: 'answered',
            sources: [],
            created_at: '2026-07-18T09:00:05Z',
          },
        ],
      },
    })
    const user = userEvent.setup()
    render(<App />)

    const selector = await screen.findByLabelText('Conversaciones guardadas')
    await user.selectOptions(selector, 'session-999')
    expect(await screen.findByText('La garantía cubre 12 meses.')).toBeInTheDocument()
    expect(window.localStorage.getItem('nebula-chat-session')).toBe('session-999')
    expect(
      api.mock.calls.some(([url]) => String(url).includes('/api/chat/history/session-999')),
    ).toBe(true)
  })

  it('shows stable provider errors returned by the backend', async () => {
    mockApi()
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/api/health/ready')) return response(health)
      if (url.endsWith('/api/documents')) return response([documentRecord])
      if (url.endsWith('/api/chat')) {
        return response(
          { detail: { code: 'llm_rate_limited', message: 'Groq está limitando solicitudes. Intentá más tarde.' } },
          503,
        )
      }
      return response({})
    })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByLabelText('Escribí tu pregunta'), '¿Cuál es la garantía?')
    await user.keyboard('{Enter}')
    expect(await screen.findByText('Groq está limitando solicitudes. Intentá más tarde.')).toBeInTheDocument()
  })
})
