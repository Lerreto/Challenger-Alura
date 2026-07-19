from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import nebula_rag.api as api_module
from nebula_rag.api import (
    AppContainer,
    _run_index_mutation,
    _set_readiness_state,
    create_app,
)
from nebula_rag.catalog import Catalog
from nebula_rag.config import Settings
from nebula_rag.domain import RetrievedChunk
from nebula_rag.ingestion import IngestionService
from nebula_rag.errors import LLMServiceError
from nebula_rag.rag import RagService

from .fakes import FakeLLM, FakeVectorIndex


def make_app(tmp_path: Path, *, configured: bool = True, fresh_dirs: bool = True):
    settings = Settings(
        documents_dir=tmp_path / "documents",
        data_dir=tmp_path / "data",
        seed_dir=tmp_path / "seed",
        max_upload_bytes=2048,
        min_relevance=0.5,
    )
    if fresh_dirs:
        settings.seed_dir.mkdir(parents=True)
    vector = FakeVectorIndex()
    llm = FakeLLM(configured=configured)
    ingestion = IngestionService(settings, Catalog(settings.catalog_path), vector)
    container = AppContainer(
        settings=settings,
        ingestion=ingestion,
        rag=RagService(vector, llm, settings.min_relevance),
        catalog=ingestion.catalog,
        model_ready=configured,
    )
    return create_app(container), llm


def test_live_health_starts_without_api_key(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path, configured=False)
    with TestClient(app) as client:
        response = client.get("/api/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "live"

        ready = client.get("/api/health/ready")
        assert ready.status_code == 200
        assert ready.json()["llm"] == "not_configured"


def test_document_and_feedback_api_contracts(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    with TestClient(app) as client:
        upload = client.post(
            "/api/documents",
            files={"file": ("policy.md", b"# Politica\nHay garantia de 12 meses.", "text/markdown")},
        )
        assert upload.status_code == 201
        body = upload.json()
        assert body["status"] == "ready"

        listed = client.get("/api/documents")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == body["id"]

        assert client.post("/api/documents/reindex").json()["documents"] == 1
        assert client.post(
            "/api/feedback",
            json={"message_id": "m-1", "rating": "helpful", "comment": "claro"},
        ).status_code == 201
        assert client.delete(f"/api/documents/{body['id']}").status_code == 204


def test_chat_contract_fallback_answer_and_controlled_503(tmp_path: Path) -> None:
    app, llm = make_app(tmp_path, configured=False)
    with TestClient(app) as client:
        fallback = client.post("/api/chat", json={"question": "Clima en Marte"})
        assert fallback.status_code == 200
        assert fallback.json()["status"] == "insufficient_context"
        assert llm.calls == 0

        client.app.state.container.rag.vector_index.results = [
            RetrievedChunk(
                id="c1",
                text="La garantia es de 12 meses.",
                score=0.9,
                metadata={"document_id": "d1", "title": "Garantia", "location": "Plazo"},
            )
        ]
        unavailable = client.post("/api/chat", json={"question": "Cual es la garantia?"})
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == "llm_not_configured"


def test_upload_api_rejects_duplicate_and_unsupported(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    with TestClient(app) as client:
        payload = b"# Documento\nContenido"
        assert client.post(
            "/api/documents", files={"file": ("one.md", payload, "text/markdown")}
        ).status_code == 201
        duplicate = client.post(
            "/api/documents", files={"file": ("two.md", payload, "text/markdown")}
        )
        assert duplicate.status_code == 409
        unsupported = client.post(
            "/api/documents", files={"file": ("bad.exe", b"MZ", "application/octet-stream")}
        )
        assert unsupported.status_code == 415


def test_ready_is_503_when_index_is_unusable_and_recovers_after_upload(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    with TestClient(app) as client:
        client.app.state.container.initialization_error = "index unavailable"
        failed = client.get("/api/health/ready")
        assert failed.status_code == 503
        assert failed.json()["index"] == "error"

        uploaded = client.post(
            "/api/documents",
            files={"file": ("recovery.md", b"# Recuperado\nContenido util.", "text/markdown")},
        )
        assert uploaded.status_code == 201
        assert client.get("/api/health/ready").status_code == 200


def test_upload_work_is_dispatched_to_threadpool(tmp_path: Path, monkeypatch) -> None:
    app, _ = make_app(tmp_path)
    dispatched: list[str] = []

    async def tracked(function, *args, **kwargs):
        dispatched.append(function.__name__)
        return function(*args, **kwargs)

    monkeypatch.setattr(api_module, "run_in_threadpool", tracked)
    with TestClient(app) as client:
        response = client.post(
            "/api/documents",
            files={"file": ("async.md", b"# Async\nNo bloquear.", "text/markdown")},
        )
        assert response.status_code == 201
        assert "ingest_bytes" in dispatched


def test_upload_validation_errors_are_stable_json(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    app.state.container.settings.max_upload_bytes = 2_000_000
    with TestClient(app) as client:
        mismatch = client.post(
            "/api/documents",
            files={"file": ("wrong.md", b"# texto", "application/pdf")},
        )
        assert mismatch.status_code == 415
        assert mismatch.json()["detail"]["code"] == "mime_extension_mismatch"

        invalid_utf8 = client.post(
            "/api/documents",
            files={"file": ("bad.txt", b"\xff\xfe", "text/plain")},
        )
        assert invalid_utf8.status_code == 422
        assert invalid_utf8.json()["detail"]["code"] == "invalid_text_encoding"

        invalid_yaml = client.post(
            "/api/documents",
            files={"file": ("bad.md", b"---\n- not\n- a mapping\n---\n# Title", "text/markdown")},
        )
        assert invalid_yaml.status_code == 422
        assert invalid_yaml.json()["detail"]["code"] == "invalid_frontmatter"

        deeply_nested = "\n".join(
            f"{'  ' * level}level-{level}:" for level in range(800)
        ).encode()
        recursion = client.post(
            "/api/documents",
            files={
                "file": (
                    "deep.md",
                    b"---\n" + deeply_nested + b"\n---\n# Title",
                    "text/markdown",
                )
            },
        )
        assert recursion.status_code == 422
        assert recursion.json()["detail"]["code"] == "invalid_frontmatter"


def test_chat_history_is_persisted_and_survives_restart(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path, configured=False)
    with TestClient(app) as client:
        first = client.post("/api/chat", json={"question": "Clima en Marte"})
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        assert first.json()["message_id"]

        second = client.post(
            "/api/chat", json={"question": "Otra pregunta", "session_id": session_id}
        )
        assert second.json()["session_id"] == session_id

        history = client.get(f"/api/chat/history/{session_id}")
        assert history.status_code == 200
        roles = [item["role"] for item in history.json()["messages"]]
        assert roles == ["user", "assistant", "user", "assistant"]
        assert history.json()["messages"][0]["content"] == "Clima en Marte"

    # A fresh app over the same SQLite catalog still serves the conversation.
    restarted, _ = make_app(tmp_path, configured=False, fresh_dirs=False)
    with TestClient(restarted) as client:
        history = client.get(f"/api/chat/history/{session_id}")
        assert len(history.json()["messages"]) == 4

        assert client.delete(f"/api/chat/history/{session_id}").status_code == 204
        assert client.get(f"/api/chat/history/{session_id}").json()["messages"] == []

        assert client.get("/api/chat/history/bad!id!").status_code == 422


def test_chat_persists_answer_sources_in_history(tmp_path: Path) -> None:
    app, llm = make_app(tmp_path)
    llm.cited_chunk_ids = ["chunk-1"]
    app.state.container.rag.vector_index.results = [
        RetrievedChunk(
            id="chunk-1",
            text="La garantia es de 12 meses.",
            score=0.9,
            metadata={"document_id": "d1", "title": "Garantia", "location": "Plazo"},
        )
    ]
    with TestClient(app) as client:
        answered = client.post("/api/chat", json={"question": "Cual es la garantia?"})
        assert answered.status_code == 200
        assert answered.json()["status"] == "answered"
        session_id = answered.json()["session_id"]

        history = client.get(f"/api/chat/history/{session_id}").json()
        assistant = history["messages"][-1]
        assert assistant["status"] == "answered"
        assert assistant["sources"][0]["chunk_id"] == "chunk-1"
        assert assistant["id"] == answered.json()["message_id"]


def test_chat_meta_question_lists_previous_questions_and_sessions_endpoint(
    tmp_path: Path,
) -> None:
    app, llm = make_app(tmp_path, configured=False)
    with TestClient(app) as client:
        first = client.post("/api/chat", json={"question": "Clima en Marte"})
        session_id = first.json()["session_id"]

        meta = client.post(
            "/api/chat",
            json={
                "question": "puedes revisar el historial de este chat?",
                "session_id": session_id,
            },
        )
        assert meta.status_code == 200
        assert meta.json()["status"] == "answered"
        assert "Clima en Marte" in meta.json()["answer"]
        assert llm.calls == 0

        sessions = client.get("/api/chat/sessions")
        assert sessions.status_code == 200
        listed = sessions.json()
        assert len(listed) == 1
        assert listed[0]["session_id"] == session_id
        assert listed[0]["title"] == "Clima en Marte"
        assert listed[0]["message_count"] == 4

        other = client.post("/api/chat", json={"question": "Otra conversación"})
        listed = client.get("/api/chat/sessions").json()
        assert len(listed) == 2
        assert listed[0]["session_id"] == other.json()["session_id"]


def test_followup_question_folds_the_previous_grounded_answer_into_retrieval(
    tmp_path: Path,
) -> None:
    app, llm = make_app(tmp_path)
    vector = app.state.container.rag.vector_index
    vector.results = [
        RetrievedChunk(
            id="chunk-1",
            text="Evidencia",
            score=0.9,
            metadata={"document_id": "d1", "title": "Doc", "location": "Uno"},
        )
    ]
    with TestClient(app) as client:
        first = client.post("/api/chat", json={"question": "dame los terminos y condiciones"})
        assert first.json()["status"] == "answered"
        session_id = first.json()["session_id"]

        client.post(
            "/api/chat",
            json={"question": "dame la informacion dentro de ese .md", "session_id": session_id},
        )
        assert "dame los terminos y condiciones" in vector.last_query
        assert llm.last_recent_exchange is not None
        assert llm.last_recent_exchange[0] == "dame los terminos y condiciones"


def test_followup_after_smalltalk_does_not_pollute_retrieval(tmp_path: Path) -> None:
    app, llm = make_app(tmp_path, configured=False)
    vector = app.state.container.rag.vector_index
    with TestClient(app) as client:
        greeting = client.post("/api/chat", json={"question": "hola"})
        session_id = greeting.json()["session_id"]

        client.post(
            "/api/chat",
            json={"question": "Clima en Marte", "session_id": session_id},
        )
        # A canned smalltalk reply has no sources, so it never becomes
        # recent_exchange: the second question hits retrieval bare.
        assert vector.last_query == "Clima en Marte"
        assert llm.calls == 0


def test_greeting_is_answered_without_llm_and_persisted(tmp_path: Path) -> None:
    app, llm = make_app(tmp_path, configured=False)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"question": "hola"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "answered"
        assert "Nébula" in body["answer"]
        assert body["sources"] == []
        assert llm.calls == 0

        history = client.get(f"/api/chat/history/{body['session_id']}").json()
        assert [item["role"] for item in history["messages"]] == ["user", "assistant"]


def test_whitespace_question_is_rejected(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"question": "   "})
        assert response.status_code == 422


def test_provider_failures_map_to_stable_gateway_contract(tmp_path: Path) -> None:
    app, llm = make_app(tmp_path)
    app.state.container.rag.vector_index.results = [
        RetrievedChunk(
            id="chunk-1",
            text="Evidencia",
            score=0.9,
            metadata={"document_id": "d1", "title": "Doc", "location": "Uno"},
        )
    ]
    with TestClient(app) as client:
        llm.error = LLMServiceError("llm_rate_limited", "Groq está limitando solicitudes.", 503)
        response = client.post("/api/chat", json={"question": "Pregunta válida"})
        assert response.status_code == 503
        assert response.json()["detail"] == {
            "code": "llm_rate_limited",
            "message": "Groq está limitando solicitudes.",
        }


def test_stale_slow_readiness_result_cannot_override_newer_generation(
    tmp_path: Path,
) -> None:
    app, _ = make_app(tmp_path)
    container = app.state.container

    _set_readiness_state(container, generation=2, usable=True)
    _set_readiness_state(container, generation=1, usable=False)

    assert container.readiness_generation == 2
    assert container.initialization_error is None


def test_slow_old_refresh_finishes_before_next_mutation_can_publish(
    tmp_path: Path, monkeypatch
) -> None:
    app, _ = make_app(tmp_path)
    container = app.state.container
    events: list[str] = []

    def first_mutation() -> str:
        events.append("first-mutation")
        return "first"

    def second_mutation() -> str:
        events.append("second-mutation")
        return "second"

    async def delayed_threadpool(function, *args, **kwargs):
        if function.__name__ == "_refresh_index_state":
            events.append("refresh-start")
            await asyncio.sleep(0.02)
            result = function(*args, **kwargs)
            events.append("refresh-end")
            return result
        return function(*args, **kwargs)

    monkeypatch.setattr(api_module, "run_in_threadpool", delayed_threadpool)

    async def scenario() -> list[str]:
        first = asyncio.create_task(
            _run_index_mutation(container, first_mutation)
        )
        await asyncio.sleep(0)
        second = asyncio.create_task(
            _run_index_mutation(container, second_mutation)
        )
        return await asyncio.gather(first, second)

    assert asyncio.run(scenario()) == ["first", "second"]
    assert events == [
        "first-mutation",
        "refresh-start",
        "refresh-end",
        "second-mutation",
        "refresh-start",
        "refresh-end",
    ]
