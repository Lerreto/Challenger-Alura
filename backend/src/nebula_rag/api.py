from __future__ import annotations

import asyncio
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from .catalog import Catalog
from .config import Settings
from .domain import ChatMessageRecord, ChatResult, ChatSessionRecord, DocumentRecord, Source
from .errors import (
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentProcessingError,
    DocumentValidationError,
    LLMServiceError,
    LLMUnavailableError,
)
from .ingestion import IngestionService
from .providers import create_llm_provider
from .rag import RagService
from .smalltalk import chat_meta_response, smalltalk_response
from .vector_store import ChromaVectorIndex


class DocumentResponse(BaseModel):
    id: str
    title: str
    category: str
    version: str
    owner: str
    language: str
    original_filename: str
    sha256: str
    status: str
    chunk_count: int
    uploaded_at: str
    error: str | None = None

    @classmethod
    def from_record(cls, record: DocumentRecord) -> "DocumentResponse":
        return cls(**{key: value for key, value in record.__dict__.items() if key != "stored_filename"})


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2_000)
    session_id: str | None = Field(
        default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$"
    )

    @field_validator("question")
    @classmethod
    def question_must_have_content(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("question_must_have_content")
        return stripped


class SourceResponse(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    location: str
    excerpt: str
    score: float

    @classmethod
    def from_source(cls, source: Source) -> "SourceResponse":
        return cls(**source.__dict__)


class ChatResponse(BaseModel):
    status: Literal["answered", "insufficient_context"]
    answer: str
    sources: list[SourceResponse]
    session_id: str
    message_id: str

    @classmethod
    def from_result(
        cls, result: ChatResult, session_id: str, message_id: str
    ) -> "ChatResponse":
        return cls(
            status=result.status,
            answer=result.answer,
            sources=[SourceResponse.from_source(source) for source in result.sources],
            session_id=session_id,
            message_id=message_id,
        )


class ChatMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    status: str | None = None
    sources: list[SourceResponse]
    created_at: str

    @classmethod
    def from_record(cls, record: ChatMessageRecord) -> "ChatMessageResponse":
        return cls(
            id=record.id,
            role=record.role,  # type: ignore[arg-type]
            content=record.content,
            status=record.status,
            sources=[SourceResponse.from_source(source) for source in record.sources],
            created_at=record.created_at,
        )


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessageResponse]


class ChatSessionResponse(BaseModel):
    session_id: str
    title: str
    message_count: int
    started_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: ChatSessionRecord) -> "ChatSessionResponse":
        return cls(**record.__dict__)


class FeedbackRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=100)
    rating: Literal["helpful", "not_helpful"]
    comment: str | None = Field(default=None, max_length=1_000)


class ReindexResponse(BaseModel):
    documents: int


@dataclass
class AppContainer:
    settings: Settings
    ingestion: IngestionService
    rag: RagService
    catalog: Catalog
    model_ready: bool
    initialization_error: str | None = None
    mutation_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    readiness_generation: int = 0


def build_container(settings: Settings | None = None) -> AppContainer:
    settings = settings or Settings()
    settings.ensure_directories()
    catalog = Catalog(settings.catalog_path)
    vector_index = ChromaVectorIndex(settings)
    provider = create_llm_provider(settings)
    ingestion = IngestionService(settings, catalog, vector_index)
    rag = RagService(
        vector_index,
        provider,
        settings.min_relevance,
        settings.retrieval_candidates,
        settings.answer_sources,
    )
    return AppContainer(settings, ingestion, rag, catalog, provider.is_configured())


def _detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _last_exchange(
    messages: list[ChatMessageRecord],
) -> tuple[str, str] | None:
    """The immediately preceding (question, answer) pair, used to resolve
    follow-up references like "ese .md" or "eso" in the new question.

    Only a genuinely document-grounded answer (status "answered" with real
    sources) qualifies — canned smalltalk/chat-meta replies and abstentions
    carry no document topic, so folding them in would only dilute retrieval.
    """
    if len(messages) < 2:
        return None
    last, previous = messages[-1], messages[-2]
    if (
        last.role == "assistant"
        and previous.role == "user"
        and last.status == "answered"
        and last.sources
    ):
        return (previous.content, last.content)
    return None


def _expected_chunk_ids(container: AppContainer) -> set[str]:
    return set(container.catalog.list_chunk_ids())


def _set_readiness_state(
    container: AppContainer, *, generation: int, usable: bool
) -> None:
    if generation < container.readiness_generation:
        return
    container.readiness_generation = generation
    container.initialization_error = None if usable else "index_unavailable"


def _refresh_index_state(container: AppContainer, generation: int) -> bool:
    usable = container.rag.vector_index.is_usable(_expected_chunk_ids(container))
    _set_readiness_state(container, generation=generation, usable=usable)
    return usable


async def _run_index_mutation(container: AppContainer, function, *args):
    """Serialize mutation and readiness publication as one ordered operation."""
    async with container.mutation_lock:
        result = await run_in_threadpool(function, *args)
        generation = container.readiness_generation + 1
        await run_in_threadpool(_refresh_index_state, container, generation)
        return result


def create_app(container: AppContainer | None = None) -> FastAPI:
    container = container or build_container()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container
        async with container.mutation_lock:
            try:
                await run_in_threadpool(container.ingestion.recover_startup)
                await run_in_threadpool(container.ingestion.bootstrap_seed)
                # Revalidate the durable pointer and clean only now-safe inactive versions.
                await run_in_threadpool(container.ingestion.recover_startup)
                generation = container.readiness_generation + 1
                await run_in_threadpool(_refresh_index_state, container, generation)
            except Exception as exc:  # liveness must survive index initialization issues
                generation = container.readiness_generation + 1
                container.readiness_generation = generation
                container.initialization_error = str(exc)
        yield

    app = FastAPI(
        title="Nébula RAG API",
        version="0.1.0",
        description="API documental con recuperación semántica y respuestas trazables.",
        lifespan=lifespan,
    )
    app.state.container = container

    @app.get("/api/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/api/health/ready")
    def ready() -> JSONResponse:
        records = container.ingestion.list_documents()
        payload = {
            "status": "degraded" if container.initialization_error else "ready",
            "index": "error" if container.initialization_error else "ready",
            "llm": "configured" if container.rag.llm.is_configured() else "not_configured",
            "provider": "groq",
            "model": container.settings.groq_model,
            "embedding_model": container.settings.embedding_model,
            "documents": len(records),
            "chunks": sum(record.chunk_count for record in records),
        }
        return JSONResponse(
            payload, status_code=503 if container.initialization_error else 200
        )

    @app.get("/api/documents", response_model=list[DocumentResponse])
    def list_documents() -> list[DocumentResponse]:
        return [
            DocumentResponse.from_record(record)
            for record in container.ingestion.list_documents()
        ]

    @app.post(
        "/api/documents",
        response_model=DocumentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_document(file: UploadFile = File(...)) -> DocumentResponse:
        filename = file.filename or ""
        content = await file.read(container.settings.max_upload_bytes + 1)
        content_type = file.content_type
        await file.close()
        try:
            record = await _run_index_mutation(
                container,
                container.ingestion.ingest_bytes,
                filename,
                content,
                content_type,
            )
            return DocumentResponse.from_record(record)
        except DocumentConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail=_detail("duplicate_document", "Este contenido ya está indexado."),
            ) from exc
        except DocumentValidationError as exc:
            code = str(exc)
            http_status = (
                415
                if code in {"unsupported_extension", "mime_extension_mismatch"}
                else 400
            )
            if code == "file_too_large":
                http_status = 413
            raise HTTPException(
                status_code=http_status,
                detail=_detail(code, "El archivo no cumple los requisitos de carga."),
            ) from exc
        except DocumentProcessingError as exc:
            code = str(exc).split(":", 1)[0]
            message = (
                "El PDF no contiene texto seleccionable. Aplicá OCR antes de cargarlo."
                if code == "ocr_required"
                else "No pudimos extraer contenido seguro del archivo."
            )
            raise HTTPException(status_code=422, detail=_detail(code, message)) from exc

    @app.delete("/api/documents/{document_id}", status_code=204)
    async def delete_document(document_id: str) -> Response:
        try:
            await _run_index_mutation(
                container, container.ingestion.delete, document_id
            )
        except DocumentNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail=_detail("document_not_found", "El documento ya no existe."),
            ) from exc
        return Response(status_code=204)

    @app.post("/api/documents/reindex", response_model=ReindexResponse)
    async def reindex_documents() -> ReindexResponse:
        try:
            documents = await _run_index_mutation(
                container, container.ingestion.reindex
            )
            return ReindexResponse(documents=documents)
        except DocumentProcessingError as exc:
            code = str(exc).split(":", 1)[0]
            raise HTTPException(
                status_code=422,
                detail=_detail(code, "No fue posible reconstruir el índice."),
            ) from exc

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(request: ChatRequest) -> ChatResponse:
        session_id = request.session_id or uuid.uuid4().hex
        history = container.catalog.list_chat_messages(session_id)
        previous_questions = [message.content for message in history if message.role == "user"]
        recent_exchange = _last_exchange(history)
        container.catalog.add_chat_message(
            ChatMessageRecord(
                id=uuid.uuid4().hex,
                session_id=session_id,
                role="user",
                content=request.question,
                status=None,
                sources=[],
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        try:
            canned = smalltalk_response(
                request.question,
                [record.title for record in container.ingestion.list_documents()],
            ) or chat_meta_response(request.question, previous_questions)
            result = (
                ChatResult("answered", canned, [])
                if canned is not None
                else container.rag.answer(request.question, recent_exchange)
            )
            message_id = uuid.uuid4().hex
            container.catalog.add_chat_message(
                ChatMessageRecord(
                    id=message_id,
                    session_id=session_id,
                    role="assistant",
                    content=result.answer,
                    status=result.status,
                    sources=result.sources,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            return ChatResponse.from_result(result, session_id, message_id)
        except LLMUnavailableError as exc:
            raise HTTPException(
                status_code=503,
                detail=_detail(
                    "llm_not_configured",
                    "Encontré evidencia, pero el modelo de respuesta no está configurado. Añadí GROQ_API_KEY en el backend.",
                ),
            ) from exc
        except LLMServiceError as exc:
            raise HTTPException(
                status_code=exc.http_status,
                detail=_detail(exc.code, str(exc)),
            ) from exc

    @app.get("/api/chat/sessions", response_model=list[ChatSessionResponse])
    def chat_sessions() -> list[ChatSessionResponse]:
        return [
            ChatSessionResponse.from_record(record)
            for record in container.catalog.list_chat_sessions()
        ]

    @app.get(
        "/api/chat/history/{session_id}", response_model=ChatHistoryResponse
    )
    def chat_history(session_id: str) -> ChatHistoryResponse:
        if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", session_id):
            raise HTTPException(
                status_code=422,
                detail=_detail("invalid_session_id", "El identificador de sesión no es válido."),
            )
        return ChatHistoryResponse(
            session_id=session_id,
            messages=[
                ChatMessageResponse.from_record(record)
                for record in container.catalog.list_chat_messages(session_id)
            ],
        )

    @app.delete("/api/chat/history/{session_id}", status_code=204)
    def clear_chat_history(session_id: str) -> Response:
        if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", session_id):
            raise HTTPException(
                status_code=422,
                detail=_detail("invalid_session_id", "El identificador de sesión no es válido."),
            )
        container.catalog.clear_chat_session(session_id)
        return Response(status_code=204)

    @app.post("/api/feedback", status_code=201)
    def feedback(request: FeedbackRequest) -> dict[str, str]:
        container.catalog.add_feedback(
            request.message_id,
            request.rating,
            request.comment,
            datetime.now(timezone.utc).isoformat(),
        )
        return {"status": "recorded"}

    return app
