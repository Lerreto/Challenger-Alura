from __future__ import annotations

from dataclasses import dataclass, field

from nebula_rag.domain import Chunk, GeneratedAnswer, RetrievedChunk


@dataclass
class FakeVectorIndex:
    results: list[RetrievedChunk] = field(default_factory=list)
    collections: dict[str, dict[str, Chunk]] = field(default_factory=dict)
    active_collection: str | None = None
    partial_build_failure: bool = False
    build_failure: bool = False
    activation_failure: bool = False
    cleanup_failure: bool = False
    build_count: int = 0
    cleanup_calls: int = 0
    last_query: str = ""

    @property
    def active_chunks(self) -> dict[str, Chunk]:
        if self.active_collection is None:
            return {}
        return self.collections.get(self.active_collection, {})

    def build_collection(self, chunks: list[Chunk]) -> str:
        self.build_count += 1
        name = f"collection-v{self.build_count}"
        staged: dict[str, Chunk] = {}
        self.collections[name] = staged
        if self.partial_build_failure and chunks:
            staged[chunks[0].id] = chunks[0]
            raise RuntimeError("partial staging failure")
        if self.build_failure:
            raise RuntimeError("staging collection failed")
        staged.update({chunk.id: chunk for chunk in chunks})
        return name

    def activate_collection(self, collection_name: str) -> None:
        if self.activation_failure:
            raise RuntimeError("activation interrupted")
        self.active_collection = collection_name

    def validate_collection(
        self, collection_name: str | None, expected_ids: set[str]
    ) -> bool:
        return (
            collection_name is not None
            and collection_name in self.collections
            and set(self.collections[collection_name]) == expected_ids
        )

    def cleanup_inactive(self, expected_ids: set[str]) -> bool:
        self.cleanup_calls += 1
        if not self.validate_collection(self.active_collection, expected_ids):
            return False
        if self.cleanup_failure:
            raise RuntimeError("cleanup failed")
        self.collections = {
            name: chunks
            for name, chunks in self.collections.items()
            if name == self.active_collection
        }
        return True

    def search(self, query: str, limit: int) -> list[RetrievedChunk]:
        self.last_query = query
        return self.results[:limit]

    def is_usable(self, expected_ids: set[str]) -> bool:
        return self.validate_collection(self.active_collection, expected_ids)


@dataclass
class FakeLLM:
    configured: bool = True
    answer: str = "Respuesta basada en los documentos."
    calls: int = 0
    last_context: str = ""
    last_recent_exchange: tuple[str, str] | None = None
    cited_chunk_ids: list[str] = field(default_factory=lambda: ["chunk-1"])
    error: Exception | None = None

    def is_configured(self) -> bool:
        return self.configured

    def generate(
        self,
        question: str,
        context: str,
        recent_exchange: tuple[str, str] | None = None,
    ) -> GeneratedAnswer:
        self.calls += 1
        self.last_context = context
        self.last_recent_exchange = recent_exchange
        if self.error:
            raise self.error
        return GeneratedAnswer(self.answer, self.cited_chunk_ids)
