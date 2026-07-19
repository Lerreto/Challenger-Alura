from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractedSection:
    text: str
    location: str
    metadata: dict[str, str | int | float] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    metadata: dict[str, str | int | float]


@dataclass(frozen=True)
class RetrievedChunk:
    id: str
    text: str
    score: float
    metadata: dict[str, str | int | float]


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    title: str
    category: str
    version: str
    owner: str
    language: str
    original_filename: str
    stored_filename: str
    sha256: str
    status: str
    chunk_count: int
    uploaded_at: str
    error: str | None = None


@dataclass(frozen=True)
class Source:
    chunk_id: str
    document_id: str
    title: str
    location: str
    excerpt: str
    score: float


@dataclass(frozen=True)
class ChatResult:
    status: str
    answer: str
    sources: list[Source]


@dataclass(frozen=True)
class ChatSessionRecord:
    session_id: str
    title: str
    message_count: int
    started_at: str
    updated_at: str


@dataclass(frozen=True)
class ChatMessageRecord:
    id: str
    session_id: str
    role: str
    content: str
    status: str | None
    sources: list[Source]
    created_at: str


@dataclass(frozen=True)
class GeneratedAnswer:
    answer: str
    cited_chunk_ids: list[str]
