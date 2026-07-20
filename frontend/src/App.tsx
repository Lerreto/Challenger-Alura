import { useCallback, useEffect, useRef, useState } from 'react'

import {
  api,
  ApiError,
  type ChatResult,
  type ChatSession,
  type DocumentRecord,
  type FeedbackRating,
  type Health,
  type Source,
} from './api'
import {
  ChevronIcon,
  CloseIcon,
  DocumentIcon,
  FilesIcon,
  MenuIcon,
  RefreshIcon,
  SendIcon,
  ShieldIcon,
  SparkIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  TrashIcon,
  UploadIcon,
  WarningIcon,
} from './icons'
import './styles.css'

const SUPPORTED_FORMATS = '.md,.txt,.pdf,.docx,.xlsx,.pptx,.csv,.json,.html,.htm'
const SESSION_STORAGE_KEY = 'nebula-chat-session'

type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  status?: ChatResult['status'] | 'error'
  sources?: Source[]
  feedback?: FeedbackRating
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'No pudimos conectar con el servicio. Revisá la conexión e intentá nuevamente.'
}

function StatusDot({ state }: { state: 'ok' | 'warn' | 'error' }) {
  return <span className={`status-dot status-dot--${state}`} aria-hidden="true" />
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)

  useEffect(() => {
    const media = window.matchMedia(query)
    const update = () => setMatches(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [query])

  return matches
}

function SourceList({ sources }: { sources: Source[] }) {
  if (!sources.length) return null
  return (
    <div className="sources" aria-label="Fuentes verificadas">
      <p className="sources__label">Fuentes verificadas · {sources.length}</p>
      {sources.map((source) => (
        <details className="source" key={`${source.document_id}-${source.chunk_id}`}>
          <summary>
            <DocumentIcon className="icon" />
            <span className="source__identity">
              <strong>{source.title}</strong>
              <small>{source.location}</small>
            </span>
            <span className="source__score">{Math.round(source.score * 100)}%</span>
            <ChevronIcon className="source__chevron" />
          </summary>
          <p>{source.excerpt}</p>
        </details>
      ))}
    </div>
  )
}

function FeedbackButtons({
  given,
  onRate,
}: {
  given?: FeedbackRating
  onRate: (rating: FeedbackRating) => void
}) {
  if (given) {
    return (
      <p className="feedback feedback--done">
        {given === 'helpful' ? '¡Gracias por tu retroalimentación!' : 'Gracias, vamos a revisar esta respuesta.'}
      </p>
    )
  }
  return (
    <div className="feedback" role="group" aria-label="¿Te sirvió esta respuesta?">
      <span>¿Te sirvió esta respuesta?</span>
      <button className="icon-button" aria-label="Respuesta útil" title="Útil" onClick={() => onRate('helpful')}>
        <ThumbsUpIcon />
      </button>
      <button className="icon-button" aria-label="Respuesta no útil" title="No útil" onClick={() => onRate('not_helpful')}>
        <ThumbsDownIcon />
      </button>
    </div>
  )
}

function DocumentLibrary({
  documents,
  loading,
  uploading,
  notice,
  onUpload,
  onDelete,
  onRefresh,
  onReindex,
  reindexing,
  onClose,
  closeButtonRef,
  isCompact,
}: {
  documents: DocumentRecord[]
  loading: boolean
  uploading: boolean
  notice: { kind: 'success' | 'error'; text: string } | null
  onUpload: (files: FileList | File[]) => void
  onDelete: (document: DocumentRecord) => void
  onRefresh: () => void
  onReindex: () => void
  reindexing: boolean
  onClose: () => void
  closeButtonRef: React.RefObject<HTMLButtonElement | null>
  isCompact: boolean
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const drop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    if (event.dataTransfer.files.length) onUpload(event.dataTransfer.files)
  }

  return (
    <aside className="library" aria-label="Biblioteca documental">
      <header className="library__header">
        <div>
          <p className="section-label"><FilesIcon className="icon" /> Biblioteca</p>
          <h2>Documentos</h2>
        </div>
        <div className="library__actions">
          <button className="icon-button" onClick={onRefresh} aria-label="Actualizar documentos" title="Actualizar">
            <RefreshIcon />
          </button>
          {isCompact && (
            <button ref={closeButtonRef} className="icon-button" onClick={onClose} aria-label="Cerrar documentos">
              <CloseIcon />
            </button>
          )}
        </div>
      </header>

      <div
        className={`dropzone${dragging ? ' dropzone--active' : ''}`}
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            inputRef.current?.click()
          }
        }}
        onDragEnter={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        aria-describedby="upload-formats"
      >
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          multiple
          accept={SUPPORTED_FORMATS}
          aria-label="Seleccionar documentos para cargar"
          onChange={(event) => {
            if (event.target.files?.length) onUpload(event.target.files)
            event.target.value = ''
          }}
        />
        <span className="dropzone__icon"><UploadIcon /></span>
        <span><strong>{uploading ? 'Procesando documento…' : 'Arrastrá o elegí archivos'}</strong></span>
        <small id="upload-formats">PDF, Office, Markdown y datos estructurados · máximo 20 MB</small>
      </div>

      <div className="notice-region" aria-live="polite" aria-atomic="true">
        {notice && <p className={`notice notice--${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>{notice.text}</p>}
      </div>

      <div className="library__list-header">
        <span>{documents.length} {documents.length === 1 ? 'documento' : 'documentos'}</span>
        <button className="text-button" onClick={onReindex} disabled={reindexing || !documents.length}>
          <RefreshIcon className={reindexing ? 'is-spinning' : ''} />
          {reindexing ? 'Reindexando…' : 'Reindexar'}
        </button>
      </div>

      <div className="document-list" aria-busy={loading}>
        {loading ? (
          <div className="library-state"><span className="loader" /> <p>Cargando documentos…</p></div>
        ) : !documents.length ? (
          <div className="library-state library-state--empty">
            <DocumentIcon />
            <h3>Todavía no hay documentos</h3>
            <p>Cargá una política o manual para habilitar respuestas verificables.</p>
          </div>
        ) : (
          documents.map((document) => (
            <article className="document-row" key={document.id}>
              <span className="document-row__icon"><DocumentIcon /></span>
              <div className="document-row__content">
                <h3>{document.title}</h3>
                <p>{document.category}</p>
                <div className="document-row__meta">
                  <span><StatusDot state={document.status === 'ready' ? 'ok' : 'warn'} /> {document.status === 'ready' ? 'Indexado' : document.status}</span>
                  <span>{document.chunk_count} fragmentos</span>
                </div>
              </div>
              <button
                className="icon-button icon-button--danger"
                aria-label={`Eliminar ${document.title}`}
                title="Eliminar documento"
                onClick={() => onDelete(document)}
              >
                <TrashIcon />
              </button>
            </article>
          ))
        )}
      </div>
    </aside>
  )
}

export default function App() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [libraryLoading, setLibraryLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(SESSION_STORAGE_KEY)
    } catch {
      return null
    }
  })
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [drawerOpen, setDrawerOpen] = useState(false)
  const isCompact = useMediaQuery('(max-width: 840px)')
  const messagesEnd = useRef<HTMLDivElement>(null)
  const drawerRef = useRef<HTMLDivElement>(null)
  const drawerTriggerRef = useRef<HTMLButtonElement>(null)
  const drawerCloseRef = useRef<HTMLButtonElement>(null)

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false)
    queueMicrotask(() => drawerTriggerRef.current?.focus())
  }, [])

  const loadDocuments = useCallback(async () => {
    setLibraryLoading(true)
    try {
      setDocuments(await api.documents())
    } catch (error) {
      setNotice({ kind: 'error', text: errorMessage(error) })
    } finally {
      setLibraryLoading(false)
    }
  }, [])

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await api.health())
    } catch {
      setHealth(null)
    }
  }, [])

  useEffect(() => {
    void loadDocuments()
    void loadHealth()
  }, [loadDocuments, loadHealth])

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    void api
      .chatHistory(sessionId)
      .then((history) => {
        if (cancelled) return
        setMessages(
          history.messages.map((item) => ({
            id: item.id,
            role: item.role,
            content: item.content,
            status: item.role === 'assistant' ? (item.status as Message['status']) : undefined,
            sources: item.role === 'assistant' ? item.sources : undefined,
          })),
        )
      })
      .catch(() => {
        // A stale session must not block the chat; start a fresh one.
        if (cancelled) return
        setSessionId(null)
        try {
          window.localStorage.removeItem(SESSION_STORAGE_KEY)
        } catch {
          // Storage unavailable (private mode); history simply won't resume.
        }
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resume history only on first render
  }, [])

  const persistSession = useCallback((value: string) => {
    setSessionId(value)
    try {
      window.localStorage.setItem(SESSION_STORAGE_KEY, value)
    } catch {
      // Storage unavailable; the session lives only in memory.
    }
  }, [])

  const loadSessions = useCallback(async () => {
    try {
      const listed = await api.chatSessions()
      setSessions(Array.isArray(listed) ? listed : [])
    } catch {
      // The switcher is optional; the current conversation keeps working.
    }
  }, [])

  useEffect(() => {
    void loadSessions()
  }, [loadSessions])

  const resetToNewConversation = useCallback(() => {
    setMessages([])
    setSessionId(null)
    try {
      window.localStorage.removeItem(SESSION_STORAGE_KEY)
    } catch {
      // Storage unavailable; nothing else to clean.
    }
  }, [])

  const startNewConversation = useCallback(() => {
    if (chatLoading) return
    resetToNewConversation()
  }, [chatLoading, resetToNewConversation])

  const switchConversation = useCallback(
    async (target: string) => {
      if (chatLoading || target === sessionId) return
      try {
        const history = await api.chatHistory(target)
        persistSession(target)
        setMessages(
          history.messages.map((item) => ({
            id: item.id,
            role: item.role,
            content: item.content,
            status: item.role === 'assistant' ? (item.status as Message['status']) : undefined,
            sources: item.role === 'assistant' ? item.sources : undefined,
          })),
        )
      } catch (error) {
        setNotice({ kind: 'error', text: errorMessage(error) })
      }
    },
    [chatLoading, persistSession, sessionId],
  )

  const deleteConversation = useCallback(async () => {
    if (chatLoading || !sessionId) return
    if (!window.confirm('¿Eliminar esta conversación de forma permanente?')) return
    try {
      await api.clearChatHistory(sessionId)
    } catch {
      // Best effort: the local view resets anyway and the list refresh will tell.
    }
    resetToNewConversation()
    await loadSessions()
  }, [chatLoading, loadSessions, resetToNewConversation, sessionId])

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, chatLoading])

  useEffect(() => {
    if (!isCompact || !drawerOpen) return
    drawerCloseRef.current?.focus()

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeDrawer()
        return
      }
      if (event.key !== 'Tab' || !drawerRef.current) return
      const focusable = Array.from(
        drawerRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => !element.hasAttribute('hidden'))
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [closeDrawer, drawerOpen, isCompact])

  const uploadFiles = async (files: FileList | File[]) => {
    setUploading(true)
    setNotice(null)
    for (const file of Array.from(files)) {
      try {
        await api.upload(file)
        setNotice({ kind: 'success', text: `${file.name} quedó indexado.` })
      } catch (error) {
        setNotice({ kind: 'error', text: errorMessage(error) })
        break
      }
    }
    await Promise.all([loadDocuments(), loadHealth()])
    setUploading(false)
  }

  const deleteDocument = async (document: DocumentRecord) => {
    if (!window.confirm(`¿Eliminar “${document.title}”? Sus fragmentos dejarán de estar disponibles para el chat.`)) return
    try {
      await api.deleteDocument(document.id)
      setNotice({ kind: 'success', text: `${document.title} fue eliminado.` })
      await Promise.all([loadDocuments(), loadHealth()])
    } catch (error) {
      setNotice({ kind: 'error', text: errorMessage(error) })
    }
  }

  const reindex = async () => {
    setReindexing(true)
    setNotice(null)
    try {
      const result = await api.reindex()
      setNotice({ kind: 'success', text: `${result.documents} documentos quedaron reindexados.` })
      await Promise.all([loadDocuments(), loadHealth()])
    } catch (error) {
      setNotice({ kind: 'error', text: errorMessage(error) })
    } finally {
      setReindexing(false)
    }
  }

  const submitQuestion = async () => {
    const trimmed = question.trim()
    if (!trimmed || chatLoading) return
    const userMessage: Message = { id: crypto.randomUUID(), role: 'user', content: trimmed }
    setMessages((current) => [...current, userMessage])
    setQuestion('')
    setChatLoading(true)
    try {
      const result = await api.chat(trimmed, sessionId)
      persistSession(result.session_id)
      setMessages((current) => [
        ...current,
        {
          id: result.message_id,
          role: 'assistant',
          content: result.answer,
          status: result.status,
          sources: result.sources,
        },
      ])
      void loadSessions()
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: errorMessage(error),
          status: 'error',
        },
      ])
    } finally {
      setChatLoading(false)
    }
  }

  const submitFeedback = async (messageId: string, rating: FeedbackRating) => {
    setMessages((current) =>
      current.map((message) => (message.id === messageId ? { ...message, feedback: rating } : message)),
    )
    try {
      await api.feedback(messageId, rating)
    } catch {
      // Best effort: keep the confirmed UI state even if the write failed
      // silently server-side; nothing actionable for the user to do here.
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark"><SparkIcon /></span>
          <div><strong>Nébula</strong><span>Document intelligence</span></div>
        </div>
        <div className="system-status" aria-label="Estado del sistema">
          <span title={health?.embedding_model ?? 'Índice no disponible'}>
            <StatusDot state={health?.index === 'ready' ? 'ok' : 'error'} />
            Índice <strong>{!health ? '—' : health.index === 'ready' ? health.chunks : 'error'}</strong>
          </span>
          <span title={health?.model ?? 'Modelo no disponible'}>
            <StatusDot state={!health ? 'error' : health.llm === 'configured' ? 'ok' : 'warn'} />
            Groq <strong>{!health ? 'sin conexión' : health.llm === 'configured' ? 'activo' : 'sin clave'}</strong>
          </span>
        </div>
      </header>

      <div className="workspace">
        <div
          ref={drawerRef}
          data-testid="library-drawer"
          className={`library-drawer${drawerOpen ? ' library-drawer--open' : ''}`}
          inert={isCompact && !drawerOpen ? true : undefined}
          aria-hidden={isCompact ? !drawerOpen : undefined}
          role={isCompact ? 'dialog' : undefined}
          aria-modal={isCompact && drawerOpen ? true : undefined}
          aria-label={isCompact ? 'Biblioteca documental' : undefined}
        >
          <DocumentLibrary
            documents={documents}
            loading={libraryLoading}
            uploading={uploading}
            notice={notice}
            onUpload={(files) => void uploadFiles(files)}
            onDelete={(document) => void deleteDocument(document)}
            onRefresh={() => void loadDocuments()}
            onReindex={() => void reindex()}
            reindexing={reindexing}
            onClose={closeDrawer}
            closeButtonRef={drawerCloseRef}
            isCompact={isCompact}
          />
        </div>
        {drawerOpen && <button className="drawer-backdrop" aria-hidden="true" tabIndex={-1} onClick={closeDrawer} />}

        <main className="chat" aria-label="Chat documental">
          <header className="chat__header">
            {isCompact && (
              <button ref={drawerTriggerRef} className="icon-button" aria-label="Abrir documentos" onClick={() => setDrawerOpen(true)}>
                <MenuIcon />
              </button>
            )}
            <div>
              <h1>Consulta documental</h1>
              <p><ShieldIcon className="icon" /> Estás hablando con un asistente de IA, no con una persona · Respuestas limitadas a la biblioteca indexada</p>
            </div>
            <div className="chat__controls">
              {sessions.length > 0 && (
                <select
                  className="session-select"
                  aria-label="Conversaciones guardadas"
                  value={sessionId ?? ''}
                  disabled={chatLoading}
                  onChange={(event) => {
                    if (event.target.value) void switchConversation(event.target.value)
                  }}
                >
                  {(sessionId === null || !sessions.some((item) => item.session_id === sessionId)) && (
                    <option value="">{sessionId === null ? 'Conversación nueva…' : 'Conversación actual'}</option>
                  )}
                  {sessions.map((item) => (
                    <option key={item.session_id} value={item.session_id}>
                      {item.title.length > 46 ? `${item.title.slice(0, 46)}…` : item.title}
                    </option>
                  ))}
                </select>
              )}
              {messages.length > 0 && (
                <>
                  <button className="text-button" onClick={startNewConversation} disabled={chatLoading}>
                    Nueva conversación
                  </button>
                  <button
                    className="icon-button icon-button--danger"
                    aria-label="Eliminar conversación"
                    title="Eliminar conversación"
                    onClick={() => void deleteConversation()}
                    disabled={chatLoading}
                  >
                    <TrashIcon />
                  </button>
                </>
              )}
            </div>
          </header>

          <section className="conversation" aria-live="polite" aria-busy={chatLoading}>
            {!messages.length && (
              <div className="chat-empty">
                <span className="chat-empty__mark"><SparkIcon /></span>
                <h2>Una respuesta. Su evidencia.</h2>
                <p>Preguntá por envíos, privacidad, garantías o devoluciones. Si la respuesta no está en los documentos, el asistente no la inventa.</p>
                <div className="suggestions" aria-label="Preguntas sugeridas">
                  {['¿Cuánto tarda un reembolso?', '¿Qué cubre la garantía?', '¿Cómo protegen mis datos?'].map((suggestion) => (
                    <button key={suggestion} onClick={() => setQuestion(suggestion)}>{suggestion}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((message) => (
              <article className={`message message--${message.role}`} key={message.id} data-status={message.status}>
                <div className="message__avatar" aria-hidden="true">
                  {message.role === 'assistant' ? (message.status === 'error' ? <WarningIcon /> : <SparkIcon />) : 'TÚ'}
                </div>
                <div className="message__body">
                  <p className="message__author">
                    {message.role === 'assistant' ? (
                      <>
                        Nébula <span className="ai-badge">IA</span>
                      </>
                    ) : (
                      'Tu pregunta'
                    )}
                  </p>
                  <p>{message.content}</p>
                  {message.sources && <SourceList sources={message.sources} />}
                  {message.role === 'assistant' && message.status !== 'error' && (
                    <FeedbackButtons
                      given={message.feedback}
                      onRate={(rating) => void submitFeedback(message.id, rating)}
                    />
                  )}
                </div>
              </article>
            ))}
            {chatLoading && (
              <article className="message message--assistant message--loading">
                <div className="message__avatar"><SparkIcon /></div>
                <div className="message__body"><p className="message__author">Nébula</p><p><span className="typing"><i /><i /><i /></span> Buscando evidencia…</p></div>
              </article>
            )}
            <div ref={messagesEnd} />
          </section>

          <form
            className="composer"
            onSubmit={(event) => {
              event.preventDefault()
              void submitQuestion()
            }}
          >
            <label htmlFor="question" className="visually-hidden">Escribí tu pregunta</label>
            <textarea
              id="question"
              value={question}
              rows={1}
              maxLength={2000}
              placeholder="Preguntá sobre los documentos…"
              aria-label="Escribí tu pregunta"
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void submitQuestion()
                }
              }}
              disabled={chatLoading}
            />
            <button type="submit" className="send-button" disabled={!question.trim() || chatLoading} aria-label="Enviar pregunta">
              <SendIcon />
            </button>
            <p>Enter para enviar · Shift + Enter para una nueva línea</p>
          </form>
        </main>
      </div>
    </div>
  )
}
