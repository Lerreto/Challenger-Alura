from __future__ import annotations

import hashlib
import os
import re
import threading
import unicodedata
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Protocol

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .catalog import Catalog
from .config import Settings
from .domain import Chunk, DocumentRecord, RetrievedChunk
from .errors import (
    DocumentConflictError,
    DocumentNotFoundError,
    DocumentProcessingError,
    DocumentValidationError,
    NebulaError,
)
from .loaders import SUPPORTED_EXTENSIONS, extract_sections, read_frontmatter


class VectorIndex(Protocol):
    active_collection: str | None

    def build_collection(self, chunks: list[Chunk]) -> str: ...
    def activate_collection(self, collection_name: str) -> None: ...
    def validate_collection(
        self, collection_name: str | None, expected_ids: set[str]
    ) -> bool: ...
    def cleanup_inactive(self, expected_ids: set[str]) -> bool: ...
    def search(self, query: str, limit: int) -> list[RetrievedChunk]: ...
    def is_usable(self, expected_ids: set[str]) -> bool: ...


MIME_TYPES_BY_EXTENSION = {
    ".md": {"text/markdown", "text/plain"},
    ".txt": {"text/plain"},
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".csv": {"text/csv", "application/csv", "text/plain"},
    ".json": {"application/json", "text/json", "text/plain"},
    ".html": {"text/html"},
    ".htm": {"text/html"},
}


def _validate_mime(extension: str, content_type: str | None) -> None:
    if not content_type:
        return
    normalized = content_type.split(";", 1)[0].strip().lower()
    if normalized in {"application/octet-stream", "binary/octet-stream"}:
        return
    if normalized not in MIME_TYPES_BY_EXTENSION[extension]:
        raise DocumentValidationError("mime_extension_mismatch")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def deterministic_chunk_id(document_id: str, index: int, text: str) -> str:
    material = f"{document_id}:{index}:{text}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def chunk_context_header(title: str, location: str) -> str:
    if not location or location == "Documento":
        return f"[{title}]"
    if location.startswith(title):
        return f"[{location}]"
    return f"[{title} — {location}]"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(filename: str) -> str:
    if not filename or filename != PurePath(filename).name:
        raise DocumentValidationError("unsafe_filename")
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise DocumentValidationError("unsafe_filename")
    normalized = unicodedata.normalize("NFKD", filename)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(normalized).stem).strip(".-_")
    extension = Path(normalized).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentValidationError("unsupported_extension")
    if not stem:
        stem = "documento"
    return f"{stem[:100]}{extension}"


class IngestionService:
    def __init__(
        self, settings: Settings, catalog: Catalog, vector_index: VectorIndex
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.vector_index = vector_index
        self._mutation_lock = threading.RLock()
        self.settings.ensure_directories()

    def list_documents(self) -> list[DocumentRecord]:
        return self.catalog.list()

    def _build_chunks(
        self, path: Path, record: DocumentRecord, metadata: dict[str, object]
    ) -> list[Chunk]:
        sections = extract_sections(
            path,
            max_extracted_bytes=self.settings.max_extracted_bytes,
            max_archive_members=self.settings.max_archive_members,
            max_json_depth=self.settings.max_json_depth,
            max_json_nodes=self.settings.max_json_nodes,
        )
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )
        chunks: list[Chunk] = []
        index = 0
        base_metadata: dict[str, str | int | float] = {
            "document_id": record.id,
            "sha256": record.sha256,
            "title": record.title,
            "category": record.category,
            "version": record.version,
            "owner": record.owner,
            "language": record.language,
            "original_filename": record.original_filename,
            "uploaded_at": record.uploaded_at,
        }
        if metadata.get("document_id"):
            base_metadata["source_document_id"] = str(metadata["document_id"])
        for section in sections:
            # Context header so broad queries ("¿qué cubre la FAQ?") also reach
            # content chunks whose text never repeats the document topic.
            header = chunk_context_header(record.title, section.location)
            for text in splitter.split_text(section.text):
                enriched = f"{header}\n{text}"
                chunk_metadata = {
                    **base_metadata,
                    **section.metadata,
                    "location": section.location,
                    "chunk_index": index,
                }
                chunk_id = deterministic_chunk_id(record.id, index, enriched)
                chunk_metadata["chunk_id"] = chunk_id
                chunks.append(Chunk(chunk_id, enriched, chunk_metadata))
                index += 1
        if not chunks:
            raise DocumentProcessingError("empty_document")
        return chunks

    def _build_snapshot(
        self,
        records: list[DocumentRecord],
        path_overrides: dict[str, Path] | None = None,
    ) -> tuple[list[DocumentRecord], list[Chunk]]:
        overrides = path_overrides or {}
        updated_records: list[DocumentRecord] = []
        all_chunks: list[Chunk] = []
        for record in records:
            path = overrides.get(
                record.id, self.settings.documents_dir / record.stored_filename
            )
            if not path.exists():
                raise DocumentProcessingError(
                    f"missing_original:{record.original_filename}"
                )
            metadata = read_frontmatter(path)
            chunks = self._build_chunks(path, record, metadata)
            updated_records.append(
                replace(record, status="ready", chunk_count=len(chunks), error=None)
            )
            all_chunks.extend(chunks)
        return updated_records, all_chunks

    @staticmethod
    def _write_fsynced(path: Path, content: bytes) -> None:
        with path.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _publish_snapshot(
        self, records: list[DocumentRecord], chunks: list[Chunk]
    ) -> str:
        collection_name = self.vector_index.build_collection(chunks)
        self.catalog.commit_snapshot(records, chunks, collection_name)
        self.vector_index.activate_collection(collection_name)
        return collection_name

    def ingest_bytes(
        self, filename: str, content: bytes, content_type: str | None = None
    ) -> DocumentRecord:
        safe_name = _safe_filename(filename)
        _validate_mime(Path(safe_name).suffix.lower(), content_type)
        if len(content) > self.settings.max_upload_bytes:
            raise DocumentValidationError("file_too_large")
        if not content:
            raise DocumentValidationError("empty_file")
        digest = sha256_bytes(content)
        document_id = digest[:24]

        with self._mutation_lock:
            if self.catalog.find_by_sha(digest):
                raise DocumentConflictError("duplicate_document")
            stored_filename = f"{document_id}_{safe_name}"
            final_path = self.settings.documents_dir / stored_filename
            temporary = (
                self.settings.documents_dir
                / f".{document_id}.uploading{Path(safe_name).suffix}"
            )
            moved = False
            committed = False
            self._write_fsynced(temporary, content)
            try:
                metadata = read_frontmatter(temporary)
                title = str(
                    metadata.get("title")
                    or Path(safe_name).stem.replace("-", " ")
                    .replace("_", " ")
                    .title()
                )
                record = DocumentRecord(
                    id=document_id,
                    title=title,
                    category=str(metadata.get("category") or "Sin categoría"),
                    version=str(metadata.get("version") or "1.0"),
                    owner=str(metadata.get("owner") or "Sin responsable asignado"),
                    language=str(metadata.get("language") or "es"),
                    original_filename=safe_name,
                    stored_filename=stored_filename,
                    sha256=digest,
                    status="ready",
                    chunk_count=0,
                    uploaded_at=_utcnow(),
                )
                desired = [*self.catalog.list(), record]
                records, chunks = self._build_snapshot(
                    desired, path_overrides={record.id: temporary}
                )
                collection_name = self.vector_index.build_collection(chunks)
                os.replace(temporary, final_path)
                moved = True
                self._fsync_directory(self.settings.documents_dir)
                self.catalog.commit_snapshot(records, chunks, collection_name)
                committed = True
                self.vector_index.activate_collection(collection_name)
                return next(item for item in records if item.id == record.id)
            except Exception:
                temporary.unlink(missing_ok=True)
                if moved and not committed:
                    final_path.unlink(missing_ok=True)
                    self._fsync_directory(self.settings.documents_dir)
                raise

    def bootstrap_seed(self) -> list[DocumentRecord]:
        created: list[DocumentRecord] = []
        if not self.settings.seed_dir.exists():
            return created
        for source in sorted(self.settings.seed_dir.iterdir()):
            if not source.is_file() or source.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if self.catalog.find_by_original_filename(source.name):
                continue
            try:
                created.append(self.ingest_bytes(source.name, source.read_bytes()))
            except DocumentConflictError:
                continue
        return created

    def sync_seed_directory(self) -> dict[str, int]:
        """Reconcile the mounted seed directory with the catalog: pick up new
        files automatically and replace a document whose on-disk content
        changed under the same filename. Meant to run on a schedule so the
        agent stays current without a manual reindex.

        Deletions stay a deliberate, audited action via the delete endpoint —
        a background scan never removes a document just because its seed
        file disappeared. Every file is handled independently, so one
        unparseable "update" can never destroy a document that was working.
        """
        counts = {"created": 0, "updated": 0, "unchanged": 0, "failed": 0}
        with self._mutation_lock:
            if not self.settings.seed_dir.exists():
                return counts
            for source in sorted(self.settings.seed_dir.iterdir()):
                if not source.is_file() or source.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                content = source.read_bytes()
                digest = sha256_bytes(content)
                existing = self.catalog.find_by_original_filename(source.name)
                if existing is not None and existing.sha256 == digest:
                    counts["unchanged"] += 1
                    continue
                try:
                    # Commit the new version first; only a successful ingest
                    # retires the old record, so a bad replacement never
                    # leaves the document catalog worse off than before.
                    self.ingest_bytes(source.name, content)
                except DocumentConflictError:
                    counts["unchanged"] += 1
                    continue
                except NebulaError:
                    counts["failed"] += 1
                    continue
                if existing is not None:
                    self.delete(existing.id)
                    counts["updated"] += 1
                else:
                    counts["created"] += 1
        return counts

    def delete(self, document_id: str) -> None:
        with self._mutation_lock:
            record = self.catalog.get(document_id)
            if not record:
                raise DocumentNotFoundError("document_not_found")
            desired = [item for item in self.catalog.list() if item.id != document_id]
            records, chunks = self._build_snapshot(desired)
            collection_name = self.vector_index.build_collection(chunks)
            self.catalog.commit_snapshot(records, chunks, collection_name)
            self.vector_index.activate_collection(collection_name)
            try:
                (self.settings.documents_dir / record.stored_filename).unlink(
                    missing_ok=True
                )
                self._fsync_directory(self.settings.documents_dir)
            except OSError:
                # The durable catalog/index already excludes it; startup cleans the orphan.
                pass

    def reindex(self) -> int:
        with self._mutation_lock:
            desired = self.catalog.list()
            records, chunks = self._build_snapshot(desired)
            self._publish_snapshot(records, chunks)
            return len(records)

    def _cleanup_untracked_files(self) -> None:
        referenced = {record.stored_filename for record in self.catalog.list()}
        generated = re.compile(r"^[0-9a-f]{24}_.+\.[A-Za-z0-9]+$")
        for path in self.settings.documents_dir.iterdir():
            if not path.is_file() or path.name in referenced:
                continue
            if (path.name.startswith(".") and ".uploading" in path.name) or generated.match(
                path.name
            ):
                path.unlink(missing_ok=True)

    def recover_startup(self) -> None:
        """Restore a usable snapshot conservatively, then clean safe orphans."""
        with self._mutation_lock:
            self._cleanup_untracked_files()
            active = self.catalog.get_active_collection()
            expected_ids = set(self.catalog.list_chunk_ids())
            if self.vector_index.validate_collection(active, expected_ids):
                assert active is not None
                self.vector_index.activate_collection(active)
                try:
                    self.vector_index.cleanup_inactive(expected_ids)
                except Exception:
                    pass
                return

            # Pointer absent/corrupt/missing: preserve every collection until a full
            # replacement has been built and committed successfully.
            records, chunks = self._build_snapshot(self.catalog.list())
            self._publish_snapshot(records, chunks)
            new_ids = {chunk.id for chunk in chunks}
            try:
                self.vector_index.cleanup_inactive(new_ids)
            except Exception:
                pass
