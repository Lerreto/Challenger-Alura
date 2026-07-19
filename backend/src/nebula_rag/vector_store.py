from __future__ import annotations

import threading
import uuid
from typing import Any

from langchain_core.documents import Document

from .config import Settings
from .domain import Chunk, RetrievedChunk


class ChromaVectorIndex:
    """Immutable, versioned Chroma collections selected by the SQLite catalog."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.ensure_directories()
        self.active_collection: str | None = None
        self._store: Any | None = None
        self._embeddings: Any | None = None
        self._lock = threading.RLock()

    @property
    def _version_prefix(self) -> str:
        return f"{self.settings.collection_name}_v_"

    def _embedding_function(self):
        from langchain_huggingface import HuggingFaceEmbeddings

        with self._lock:
            if self._embeddings is None:
                self._embeddings = HuggingFaceEmbeddings(
                    model_name=self.settings.embedding_model,
                    model_kwargs={"device": self.settings.embedding_device},
                    encode_kwargs={"normalize_embeddings": True},
                    query_encode_kwargs={"normalize_embeddings": True},
                )
            return self._embeddings

    def _new_store(self, collection_name: str) -> Any:
        from langchain_chroma import Chroma

        return Chroma(
            collection_name=collection_name,
            embedding_function=self._embedding_function(),
            persist_directory=str(self.settings.chroma_path),
            collection_metadata={"hnsw:space": "cosine"},
        )

    def _client(self):
        import chromadb

        return chromadb.PersistentClient(path=str(self.settings.chroma_path))

    def _list_collections(self) -> list[str]:
        result = self._client().list_collections()
        return [item if isinstance(item, str) else str(item.name) for item in result]

    def _collection_ids(self, collection_name: str) -> list[str]:
        collection = self._client().get_collection(collection_name)
        payload = collection.get(include=[])
        return [str(chunk_id) for chunk_id in payload.get("ids", [])]

    def _delete_collection(self, collection_name: str) -> None:
        self._client().delete_collection(collection_name)

    @staticmethod
    def _documents(chunks: list[Chunk]) -> list[Document]:
        return [
            Document(page_content=chunk.text, metadata=chunk.metadata)
            for chunk in chunks
        ]

    def build_collection(self, chunks: list[Chunk]) -> str:
        """Create and verify a complete inactive version without changing reads."""
        collection_name = f"{self._version_prefix}{uuid.uuid4().hex}"
        expected_ids = {chunk.id for chunk in chunks}
        if len(expected_ids) != len(chunks):
            raise RuntimeError("duplicate_chunk_ids")
        try:
            store = self._new_store(collection_name)
            if chunks:
                store.add_documents(
                    documents=self._documents(chunks),
                    ids=[chunk.id for chunk in chunks],
                )
            actual_ids = self._collection_ids(collection_name)
            if len(actual_ids) != len(expected_ids) or set(actual_ids) != expected_ids:
                raise RuntimeError("incomplete_staging_collection")
            return collection_name
        except Exception:
            try:
                self._delete_collection(collection_name)
            except Exception:
                # An inactive orphan is safe and can be reconsidered after recovery.
                pass
            raise

    def activate_collection(self, collection_name: str) -> None:
        """Switch the in-memory read reference after SQLite commits the pointer."""
        with self._lock:
            self.active_collection = collection_name
            self._store = None

    def validate_collection(
        self, collection_name: str | None, expected_ids: set[str]
    ) -> bool:
        if not collection_name:
            return False
        try:
            actual_ids = self._collection_ids(collection_name)
            return len(actual_ids) == len(expected_ids) and set(actual_ids) == expected_ids
        except Exception:
            return False

    def is_usable(self, expected_ids: set[str]) -> bool:
        return self.validate_collection(self.active_collection, expected_ids)

    def cleanup_inactive(self, expected_ids: set[str]) -> bool:
        """Delete only versioned inactives after the active snapshot validates exactly."""
        with self._lock:
            if not self.is_usable(expected_ids):
                return False
            for name in self._list_collections():
                if name.startswith(self._version_prefix) and name != self.active_collection:
                    try:
                        self._delete_collection(name)
                    except Exception:
                        # Cleanup is non-critical; leave the orphan for a later startup.
                        continue
            return True

    def _get_store(self) -> Any:
        if not self.active_collection:
            raise RuntimeError("active_collection_not_configured")
        if self._store is None:
            self._store = self._new_store(self.active_collection)
        return self._store

    def search(self, query: str, limit: int) -> list[RetrievedChunk]:
        with self._lock:
            results = self._get_store().similarity_search_with_relevance_scores(
                query, k=limit
            )
        retrieved = []
        for index, (document, score) in enumerate(results):
            relevance = max(0.0, min(1.0, float(score)))
            chunk_id = str(document.metadata.get("chunk_id") or f"result-{index}")
            retrieved.append(
                RetrievedChunk(
                    id=chunk_id,
                    text=document.page_content,
                    score=relevance,
                    metadata=dict(document.metadata),
                )
            )
        return retrieved
