from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nebula_rag.catalog import Catalog
from nebula_rag.domain import Chunk, DocumentRecord


def record(document_id: str = "doc-1") -> DocumentRecord:
    return DocumentRecord(
        id=document_id,
        title="Documento",
        category="Legal",
        version="1.0",
        owner="Equipo",
        language="es-CO",
        original_filename=f"{document_id}.md",
        stored_filename=f"{document_id}_{document_id}.md",
        sha256=(document_id * 64)[:64],
        status="ready",
        chunk_count=1,
        uploaded_at="2026-07-18T00:00:00+00:00",
    )


def chunk(chunk_id: str, document_id: str = "doc-1") -> Chunk:
    return Chunk(
        id=chunk_id,
        text=f"contenido {chunk_id}",
        metadata={"document_id": document_id, "chunk_id": chunk_id},
    )


def test_snapshot_commits_documents_chunk_manifest_and_pointer_together(
    tmp_path: Path,
) -> None:
    catalog = Catalog(tmp_path / "catalog.sqlite3")

    catalog.commit_snapshot([record()], [chunk("chunk-1")], "collection-v1")

    assert [item.id for item in catalog.list()] == ["doc-1"]
    assert catalog.list_chunk_ids() == ["chunk-1"]
    assert catalog.get_active_collection() == "collection-v1"


def test_snapshot_transaction_rolls_back_all_state_on_manifest_failure(
    tmp_path: Path,
) -> None:
    catalog = Catalog(tmp_path / "catalog.sqlite3")
    catalog.commit_snapshot([record()], [chunk("chunk-1")], "collection-v1")

    with pytest.raises(sqlite3.IntegrityError):
        catalog.commit_snapshot(
            [record("doc-2")],
            [chunk("duplicate", "doc-2"), chunk("duplicate", "doc-2")],
            "collection-v2",
        )

    assert [item.id for item in catalog.list()] == ["doc-1"]
    assert catalog.list_chunk_ids() == ["chunk-1"]
    assert catalog.get_active_collection() == "collection-v1"


def test_active_collection_can_be_missing_without_inventing_a_default(
    tmp_path: Path,
) -> None:
    catalog = Catalog(tmp_path / "catalog.sqlite3")

    assert catalog.get_active_collection() is None
    assert catalog.list_chunk_ids() == []


def test_chat_messages_roundtrip_with_sources_and_isolated_sessions(
    tmp_path: Path,
) -> None:
    from nebula_rag.domain import ChatMessageRecord, Source

    catalog = Catalog(tmp_path / "catalog.sqlite3")
    source = Source(
        chunk_id="c1",
        document_id="d1",
        title="Garantía",
        location="Plazo",
        excerpt="12 meses",
        score=0.91,
    )
    catalog.add_chat_message(
        ChatMessageRecord(
            id="m1",
            session_id="session-a",
            role="user",
            content="¿Cuál es la garantía?",
            status=None,
            sources=[],
            created_at="2026-07-18T10:00:00+00:00",
        )
    )
    catalog.add_chat_message(
        ChatMessageRecord(
            id="m2",
            session_id="session-a",
            role="assistant",
            content="La garantía es de 12 meses.",
            status="answered",
            sources=[source],
            created_at="2026-07-18T10:00:05+00:00",
        )
    )
    catalog.add_chat_message(
        ChatMessageRecord(
            id="m3",
            session_id="session-b",
            role="user",
            content="Otra sesión",
            status=None,
            sources=[],
            created_at="2026-07-18T10:01:00+00:00",
        )
    )

    messages = catalog.list_chat_messages("session-a")
    assert [item.id for item in messages] == ["m1", "m2"]
    assert messages[1].sources == [source]
    assert catalog.list_chat_messages("session-b")[0].content == "Otra sesión"

    catalog.clear_chat_session("session-a")
    assert catalog.list_chat_messages("session-a") == []
    assert len(catalog.list_chat_messages("session-b")) == 1
