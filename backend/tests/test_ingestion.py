from __future__ import annotations

from pathlib import Path

import pytest

from nebula_rag.catalog import Catalog
from nebula_rag.config import Settings
from nebula_rag.domain import Chunk, DocumentRecord
from nebula_rag.errors import DocumentConflictError, DocumentValidationError
from nebula_rag.ingestion import IngestionService, deterministic_chunk_id, sha256_bytes

from .fakes import FakeVectorIndex


@pytest.fixture
def service(tmp_path: Path) -> IngestionService:
    settings = Settings(
        documents_dir=tmp_path / "documents",
        data_dir=tmp_path / "data",
        seed_dir=tmp_path / "seed",
        max_upload_bytes=1024,
        max_extracted_bytes=100_000,
        chunk_size=120,
        chunk_overlap=20,
    )
    settings.seed_dir.mkdir(parents=True)
    return IngestionService(settings, Catalog(settings.catalog_path), FakeVectorIndex())


def test_hash_and_chunk_ids_are_deterministic() -> None:
    digest = sha256_bytes(b"same bytes")
    assert digest == sha256_bytes(b"same bytes")
    assert deterministic_chunk_id("doc", 3, "same text") == deterministic_chunk_id(
        "doc", 3, "same text"
    )
    assert deterministic_chunk_id("doc", 4, "same text") != deterministic_chunk_id(
        "doc", 3, "same text"
    )


def test_upload_reindex_and_delete_publish_complete_immutable_snapshots(
    service: IngestionService,
) -> None:
    content = b"""---
title: Politica de prueba
category: Legal
version: '1.0'
owner: Legal
language: es-CO
---
# Politica
Las devoluciones se aceptan durante quince dias calendario.
"""
    created = service.ingest_bytes("policy.md", content)
    vector = service.vector_index
    assert isinstance(vector, FakeVectorIndex)
    first_collection = vector.active_collection

    assert created.status == "ready"
    assert service.catalog.get_active_collection() == first_collection
    assert set(service.catalog.list_chunk_ids()) == set(vector.active_chunks)

    with pytest.raises(DocumentConflictError, match="duplicate"):
        service.ingest_bytes("copy.md", content)

    assert service.reindex() == 1
    assert vector.active_collection != first_collection
    assert first_collection in vector.collections

    service.delete(created.id)
    assert service.list_documents() == []
    assert vector.active_chunks == {}
    assert service.catalog.list_chunk_ids() == []
    assert not (service.settings.documents_dir / created.stored_filename).exists()


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("../escape.md", b"# no", "unsafe_filename"),
        ("malware.exe", b"MZ", "unsupported_extension"),
        ("too-big.txt", b"x" * 1025, "file_too_large"),
    ],
)
def test_upload_validation_failures(
    service: IngestionService, filename: str, content: bytes, message: str
) -> None:
    with pytest.raises(DocumentValidationError, match=message):
        service.ingest_bytes(filename, content)


def test_seed_copies_only_missing_files(service: IngestionService) -> None:
    seed = service.settings.seed_dir / "faq.md"
    seed.write_text("# FAQ\nContenido original", encoding="utf-8")
    service.bootstrap_seed()
    first = service.list_documents()[0]

    stored = service.settings.documents_dir / first.stored_filename
    stored.write_text("# FAQ\nContenido cargado", encoding="utf-8")
    service.bootstrap_seed()

    assert stored.read_text(encoding="utf-8") == "# FAQ\nContenido cargado"
    assert len(service.list_documents()) == 1


def test_sync_seed_directory_creates_updates_and_leaves_unchanged_alone(
    service: IngestionService,
) -> None:
    seed_a = service.settings.seed_dir / "a.md"
    seed_a.write_text("# A\nVersion inicial de A.", encoding="utf-8")
    seed_b = service.settings.seed_dir / "b.md"
    seed_b.write_text("# B\nContenido de B.", encoding="utf-8")

    counts = service.sync_seed_directory()
    assert counts == {"created": 2, "updated": 0, "unchanged": 0, "failed": 0}
    assert {record.original_filename for record in service.list_documents()} == {
        "a.md",
        "b.md",
    }
    original_a_id = service.catalog.find_by_original_filename("a.md").id

    # A second pass over unchanged files must not re-ingest anything.
    counts = service.sync_seed_directory()
    assert counts == {"created": 0, "updated": 0, "unchanged": 2, "failed": 0}

    # Editing a.md on disk under the same filename is a content update.
    seed_a.write_text("# A\nVersion actualizada de A con mas contenido.", encoding="utf-8")
    counts = service.sync_seed_directory()
    assert counts == {"created": 0, "updated": 1, "unchanged": 1, "failed": 0}

    updated_a = service.catalog.find_by_original_filename("a.md")
    assert updated_a is not None
    assert updated_a.id != original_a_id
    assert "actualizada" in (
        (service.settings.documents_dir / updated_a.stored_filename).read_text(
            encoding="utf-8"
        )
    )
    assert service.catalog.get(original_a_id) is None  # old version retired
    assert {record.original_filename for record in service.list_documents()} == {
        "a.md",
        "b.md",
    }


def test_sync_seed_directory_never_destroys_a_working_document_on_a_bad_update(
    service: IngestionService,
) -> None:
    seed = service.settings.seed_dir / "policy.md"
    seed.write_text("# Politica\nContenido valido.", encoding="utf-8")
    service.sync_seed_directory()
    working = service.catalog.find_by_original_filename("policy.md")
    assert working is not None

    # A subsequent on-disk edit that fails validation must not remove the
    # previously-working document; the sync only reports a failed count.
    seed.write_bytes(b"\xff\xfe")  # invalid encoding, same original filename
    counts = service.sync_seed_directory()
    assert counts == {"created": 0, "updated": 0, "unchanged": 0, "failed": 1}

    still_there = service.catalog.find_by_original_filename("policy.md")
    assert still_there is not None
    assert still_there.id == working.id


def test_initial_corpus_indexes_all_five_markdown_documents(tmp_path: Path) -> None:
    settings = Settings(
        documents_dir=tmp_path / "documents",
        data_dir=tmp_path / "data",
        seed_dir=Path(__file__).parents[2] / "documents",
    )
    ingestion = IngestionService(settings, Catalog(settings.catalog_path), FakeVectorIndex())

    created = ingestion.bootstrap_seed()

    assert len(created) == 5
    assert sum(record.chunk_count for record in created) >= 5
    assert set(ingestion.catalog.list_chunk_ids()) == set(
        ingestion.vector_index.active_chunks
    )


def test_partial_staging_failure_never_changes_catalog_active_or_files(
    service: IngestionService,
) -> None:
    vector = service.vector_index
    assert isinstance(vector, FakeVectorIndex)
    vector.partial_build_failure = True

    with pytest.raises(RuntimeError, match="partial staging failure"):
        service.ingest_bytes(
            "partial.md",
            b"# Uno\nTexto suficientemente largo para producir fragmentos.",
        )

    assert vector.active_collection is None
    assert service.catalog.get_active_collection() is None
    assert service.list_documents() == []
    assert list(service.settings.documents_dir.iterdir()) == []


def test_failed_reindex_and_delete_preserve_previous_snapshot(
    service: IngestionService,
) -> None:
    created = service.ingest_bytes("stable.md", b"# Estable\nGarantia de doce meses.")
    vector = service.vector_index
    assert isinstance(vector, FakeVectorIndex)
    previous_name = vector.active_collection
    previous_ids = set(vector.active_chunks)
    vector.build_failure = True

    with pytest.raises(RuntimeError, match="staging collection failed"):
        service.reindex()
    with pytest.raises(RuntimeError, match="staging collection failed"):
        service.delete(created.id)

    assert vector.active_collection == previous_name
    assert set(vector.active_chunks) == previous_ids
    assert service.catalog.get_active_collection() == previous_name
    assert service.catalog.get(created.id) is not None
    assert (service.settings.documents_dir / created.stored_filename).exists()


def test_transaction_failure_after_staging_keeps_old_pointer_and_file(
    service: IngestionService, monkeypatch
) -> None:
    created = service.ingest_bytes("old.md", b"# Viejo\nContenido vigente.")
    vector = service.vector_index
    assert isinstance(vector, FakeVectorIndex)
    previous_name = vector.active_collection
    monkeypatch.setattr(
        service.catalog,
        "commit_snapshot",
        lambda *args: (_ for _ in ()).throw(RuntimeError("sqlite commit failed")),
    )

    with pytest.raises(RuntimeError, match="sqlite commit failed"):
        service.ingest_bytes("new.md", b"# Nuevo\nNo debe publicarse.")

    assert vector.active_collection == previous_name
    assert service.catalog.get_active_collection() == previous_name
    assert [item.id for item in service.list_documents()] == [created.id]
    assert sorted(path.name for path in service.settings.documents_dir.iterdir()) == [
        created.stored_filename
    ]


def test_crash_after_transaction_leaves_new_pointer_durable_for_restart(
    service: IngestionService,
) -> None:
    vector = service.vector_index
    assert isinstance(vector, FakeVectorIndex)
    vector.activation_failure = True

    with pytest.raises(RuntimeError, match="activation interrupted"):
        service.ingest_bytes("durable.md", b"# Durable\nContenido confirmado.")

    durable_name = service.catalog.get_active_collection()
    assert durable_name is not None
    assert service.list_documents()[0].original_filename == "durable.md"
    assert any(service.settings.documents_dir.iterdir())

    vector.activation_failure = False
    service.recover_startup()
    assert vector.active_collection == durable_name
    assert vector.is_usable(set(service.catalog.list_chunk_ids()))


def _legacy_record(stored_filename: str) -> DocumentRecord:
    return DocumentRecord(
        id="legacy-doc",
        title="Legacy",
        category="Legal",
        version="1.0",
        owner="Equipo",
        language="es-CO",
        original_filename="legacy.md",
        stored_filename=stored_filename,
        sha256="a" * 64,
        status="ready",
        chunk_count=1,
        uploaded_at="2026-07-18T00:00:00+00:00",
    )


@pytest.mark.parametrize("pointer", [None, "missing-collection"])
def test_startup_rebuilds_when_sqlite_pointer_is_missing_or_invalid(
    tmp_path: Path, pointer: str | None
) -> None:
    settings = Settings(
        documents_dir=tmp_path / "documents",
        data_dir=tmp_path / "data",
        seed_dir=tmp_path / "seed",
    )
    catalog = Catalog(settings.catalog_path)
    vector = FakeVectorIndex()
    ingestion = IngestionService(settings, catalog, vector)
    stored = "legacy-doc_legacy.md"
    (settings.documents_dir / stored).write_text("# Legacy\nContenido.", encoding="utf-8")
    legacy = _legacy_record(stored)
    manifest = Chunk(
        "legacy-manifest-id",
        "legacy",
        {"document_id": legacy.id, "chunk_id": "legacy-manifest-id"},
    )
    catalog.commit_snapshot([legacy], [manifest], "old-missing-collection")
    with catalog._connection() as connection:
        if pointer is None:
            connection.execute("DELETE FROM settings WHERE key = 'active_collection'")
        else:
            connection.execute(
                "UPDATE settings SET value = ? WHERE key = 'active_collection'",
                (pointer,),
            )
    vector.collections["collection-v999"] = {}

    ingestion.recover_startup()

    active = catalog.get_active_collection()
    assert active is not None and active != pointer
    assert vector.validate_collection(active, set(catalog.list_chunk_ids()))
    assert "collection-v999" not in vector.collections


def test_startup_does_not_cleanup_any_collection_if_rebuild_fails(
    tmp_path: Path,
) -> None:
    settings = Settings(documents_dir=tmp_path / "documents", data_dir=tmp_path / "data")
    catalog = Catalog(settings.catalog_path)
    vector = FakeVectorIndex(build_failure=True)
    vector.collections = {"possible-backup": {}, "partial-orphan": {}}
    ingestion = IngestionService(settings, catalog, vector)

    with pytest.raises(RuntimeError, match="staging collection failed"):
        ingestion.recover_startup()

    assert set(vector.collections) == {"possible-backup", "partial-orphan", "collection-v1"}
    assert vector.cleanup_calls == 0


def test_startup_removes_only_recognizable_untracked_upload_files(
    service: IngestionService,
) -> None:
    orphan = service.settings.documents_dir / f"{'b' * 24}_orphan.md"
    temporary = service.settings.documents_dir / ".interrupted.uploading.md"
    unrelated = service.settings.documents_dir / "keep-me.txt"
    orphan.write_text("orphan", encoding="utf-8")
    temporary.write_text("temp", encoding="utf-8")
    unrelated.write_text("manual", encoding="utf-8")

    service.recover_startup()

    assert not orphan.exists()
    assert not temporary.exists()
    assert unrelated.exists()
