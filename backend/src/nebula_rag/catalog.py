from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from collections.abc import Iterator

from .domain import Chunk, ChatMessageRecord, ChatSessionRecord, DocumentRecord, Source


class Catalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    version TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    language TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL UNIQUE,
                    sha256 TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_documents_original
                    ON documents(original_filename);
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_document
                    ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    comment TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT,
                    sources TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                    ON chat_messages(session_id, created_at);
                """
            )

    @staticmethod
    def _insert_document(
        connection: sqlite3.Connection, record: DocumentRecord
    ) -> None:
        connection.execute(
            """
            INSERT INTO documents (
                id, title, category, version, owner, language,
                original_filename, stored_filename, sha256, status,
                chunk_count, uploaded_at, error
            ) VALUES (
                :id, :title, :category, :version, :owner, :language,
                :original_filename, :stored_filename, :sha256, :status,
                :chunk_count, :uploaded_at, :error
            )
            """,
            asdict(record),
        )

    def commit_snapshot(
        self,
        records: list[DocumentRecord],
        chunks: list[Chunk],
        active_collection: str,
    ) -> None:
        """Atomically publish the catalog, chunk manifest and vector pointer."""
        with self._lock, self._connection() as connection:
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM documents")
            for record in records:
                self._insert_document(connection, record)
            connection.executemany(
                "INSERT INTO chunks(id, document_id) VALUES (?, ?)",
                [
                    (chunk.id, str(chunk.metadata.get("document_id") or ""))
                    for chunk in chunks
                ],
            )
            connection.execute(
                """
                INSERT INTO settings(key, value) VALUES ('active_collection', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (active_collection,),
            )

    def get_active_collection(self) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = 'active_collection'"
            ).fetchone()
        return str(row["value"]) if row and row["value"] else None

    def list_chunk_ids(self) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute("SELECT id FROM chunks ORDER BY id").fetchall()
        return [str(row["id"]) for row in rows]

    def list(self) -> list[DocumentRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM documents ORDER BY uploaded_at DESC, title"
            ).fetchall()
        return [DocumentRecord(**dict(row)) for row in rows]

    def get(self, document_id: str) -> DocumentRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        return DocumentRecord(**dict(row)) if row else None

    def find_by_sha(self, digest: str) -> DocumentRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE sha256 = ?", (digest,)
            ).fetchone()
        return DocumentRecord(**dict(row)) if row else None

    def find_by_original_filename(self, filename: str) -> DocumentRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE original_filename = ?", (filename,)
            ).fetchone()
        return DocumentRecord(**dict(row)) if row else None

    def add_chat_message(self, message: ChatMessageRecord) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages(
                    id, session_id, role, content, status, sources, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.session_id,
                    message.role,
                    message.content,
                    message.status,
                    json.dumps(
                        [asdict(source) for source in message.sources],
                        ensure_ascii=False,
                    ),
                    message.created_at,
                ),
            )

    def list_chat_messages(self, session_id: str) -> list[ChatMessageRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at, rowid
                """,
                (session_id,),
            ).fetchall()
        messages = []
        for row in rows:
            try:
                sources = [Source(**item) for item in json.loads(row["sources"])]
            except (ValueError, TypeError):
                sources = []
            messages.append(
                ChatMessageRecord(
                    id=str(row["id"]),
                    session_id=str(row["session_id"]),
                    role=str(row["role"]),
                    content=str(row["content"]),
                    status=row["status"],
                    sources=sources,
                    created_at=str(row["created_at"]),
                )
            )
        return messages

    def list_chat_sessions(self) -> list[ChatSessionRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    session_id,
                    MIN(created_at) AS started_at,
                    MAX(created_at) AS updated_at,
                    COUNT(*) AS message_count,
                    (
                        SELECT content FROM chat_messages AS first_user
                        WHERE first_user.session_id = chat_messages.session_id
                          AND first_user.role = 'user'
                        ORDER BY first_user.created_at, first_user.rowid
                        LIMIT 1
                    ) AS title
                FROM chat_messages
                GROUP BY session_id
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [
            ChatSessionRecord(
                session_id=str(row["session_id"]),
                title=str(row["title"] or "Conversación"),
                message_count=int(row["message_count"]),
                started_at=str(row["started_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    def clear_chat_session(self, session_id: str) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE session_id = ?", (session_id,)
            )

    def add_feedback(
        self, message_id: str, rating: str, comment: str | None, created_at: str
    ) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO feedback(message_id, rating, comment, created_at) VALUES (?, ?, ?, ?)",
                (message_id, rating, comment, created_at),
            )
