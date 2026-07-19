from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.documents import Document

from nebula_rag.config import Settings
from nebula_rag.domain import Chunk
from nebula_rag.vector_store import ChromaVectorIndex


class FakeStore:
    def __init__(self, name: str, *, fail_after: int | None = None) -> None:
        self.name = name
        self.documents: dict[str, tuple[str, dict]] = {}
        self.fail_after = fail_after

    def add_documents(self, documents, ids):
        for index, (document, chunk_id) in enumerate(zip(documents, ids, strict=True)):
            self.documents[chunk_id] = (document.page_content, document.metadata)
            if self.fail_after is not None and index + 1 >= self.fail_after:
                raise RuntimeError("partial staging failure")

    def similarity_search_with_relevance_scores(self, query, k):
        return []


def chunk(chunk_id: str) -> Chunk:
    return Chunk(
        chunk_id,
        f"texto {chunk_id}",
        {"document_id": "d1", "chunk_id": chunk_id},
    )


def test_build_collection_is_immutable_and_does_not_activate_before_commit(
    tmp_path: Path, monkeypatch
) -> None:
    index = ChromaVectorIndex(Settings(data_dir=tmp_path, documents_dir=tmp_path / "docs"))
    index.activate_collection("collection-old")
    stores: dict[str, FakeStore] = {}
    monkeypatch.setattr(
        index, "_new_store", lambda name: stores.setdefault(name, FakeStore(name))
    )
    monkeypatch.setattr(
        index, "_collection_ids", lambda name: set(stores[name].documents)
    )

    staged = index.build_collection([chunk("new-1"), chunk("new-2")])

    assert staged != "collection-old"
    assert index.active_collection == "collection-old"
    assert set(stores[staged].documents) == {"new-1", "new-2"}


def test_partial_build_never_contaminates_active_and_preserves_original_error(
    tmp_path: Path, monkeypatch
) -> None:
    index = ChromaVectorIndex(Settings(data_dir=tmp_path, documents_dir=tmp_path / "docs"))
    index.activate_collection("collection-old")
    staging = FakeStore("staging", fail_after=1)
    monkeypatch.setattr(index, "_new_store", lambda name: staging)
    monkeypatch.setattr(
        index,
        "_delete_collection",
        lambda name: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )

    with pytest.raises(RuntimeError, match="partial staging failure"):
        index.build_collection([chunk("new-1"), chunk("new-2")])

    assert index.active_collection == "collection-old"
    assert "new-1" in staging.documents


def test_is_usable_checks_exact_ids_even_for_empty_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    index = ChromaVectorIndex(Settings(data_dir=tmp_path, documents_dir=tmp_path / "docs"))
    collections = {"empty": set(), "orphan": {"unexpected"}}
    monkeypatch.setattr(index, "_collection_ids", lambda name: collections[name])

    assert index.is_usable(set()) is False
    index.activate_collection("empty")
    assert index.is_usable(set()) is True
    assert index.is_usable({"expected"}) is False
    index.activate_collection("missing")
    assert index.is_usable(set()) is False


def test_cleanup_is_conservative_when_active_collection_does_not_validate(
    tmp_path: Path, monkeypatch
) -> None:
    settings = Settings(data_dir=tmp_path, documents_dir=tmp_path / "docs")
    index = ChromaVectorIndex(settings)
    index.activate_collection("nebula_documents_v_active")
    deleted: list[str] = []
    monkeypatch.setattr(
        index,
        "_list_collections",
        lambda: [
            "nebula_documents_v_active",
            "nebula_documents_v_orphan",
            "unrelated",
        ],
    )
    monkeypatch.setattr(index, "_delete_collection", deleted.append)
    monkeypatch.setattr(index, "_collection_ids", lambda name: {"wrong"})

    assert index.cleanup_inactive({"expected"}) is False
    assert deleted == []

    monkeypatch.setattr(index, "_collection_ids", lambda name: {"expected"})
    assert index.cleanup_inactive({"expected"}) is True
    assert deleted == ["nebula_documents_v_orphan"]


def test_activate_switches_search_reference_without_deleting_backup(
    tmp_path: Path, monkeypatch
) -> None:
    index = ChromaVectorIndex(Settings(data_dir=tmp_path, documents_dir=tmp_path / "docs"))
    stores = {"old": FakeStore("old"), "new": FakeStore("new")}
    monkeypatch.setattr(index, "_new_store", lambda name: stores[name])
    index.activate_collection("old")
    assert index._get_store() is stores["old"]

    index.activate_collection("new")

    assert index.active_collection == "new"
    assert index._get_store() is stores["new"]


def test_search_maps_metadata_ids_and_clamps_relevance_scores(
    tmp_path: Path, monkeypatch
) -> None:
    index = ChromaVectorIndex(Settings(data_dir=tmp_path, documents_dir=tmp_path / "docs"))
    store = FakeStore("active")
    store.similarity_search_with_relevance_scores = lambda query, k: [
        (
            Document(
                page_content="evidencia",
                metadata={"chunk_id": "chunk-1", "document_id": "doc-1"},
            ),
            1.4,
        ),
        (Document(page_content="otra", metadata={"document_id": "doc-2"}), -0.2),
    ]
    monkeypatch.setattr(index, "_new_store", lambda name: store)
    index.activate_collection("active")

    results = index.search("pregunta", 2)

    assert [(item.id, item.score) for item in results] == [
        ("chunk-1", 1.0),
        ("result-1", 0.0),
    ]
    assert results[0].metadata["document_id"] == "doc-1"


def test_search_requires_an_activated_collection(tmp_path: Path) -> None:
    index = ChromaVectorIndex(Settings(data_dir=tmp_path, documents_dir=tmp_path / "docs"))

    with pytest.raises(RuntimeError, match="active_collection_not_configured"):
        index.search("pregunta", 1)
