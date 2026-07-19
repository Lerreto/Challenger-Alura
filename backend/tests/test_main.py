from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

import nebula_rag.api as api_module
from nebula_rag.api import AppContainer
from nebula_rag.catalog import Catalog
from nebula_rag.config import Settings
from nebula_rag.ingestion import IngestionService
from nebula_rag.rag import RagService

from .fakes import FakeLLM, FakeVectorIndex


def test_real_main_app_routes_and_lifespan_start_without_groq_key(
    tmp_path: Path, monkeypatch
) -> None:
    settings = Settings(
        documents_dir=tmp_path / "documents",
        data_dir=tmp_path / "data",
        seed_dir=tmp_path / "seed",
        groq_api_key=None,
    )
    settings.seed_dir.mkdir(parents=True)
    catalog = Catalog(settings.catalog_path)
    vector = FakeVectorIndex()
    llm = FakeLLM(configured=False)
    ingestion = IngestionService(settings, catalog, vector)
    container = AppContainer(
        settings=settings,
        ingestion=ingestion,
        rag=RagService(vector, llm, settings.min_relevance),
        catalog=catalog,
        model_ready=False,
    )
    monkeypatch.setattr(api_module, "build_container", lambda settings=None: container)
    sys.modules.pop("nebula_rag.main", None)

    main_module = importlib.import_module("nebula_rag.main")
    with TestClient(main_module.app) as client:
        assert client.get("/api/health/live").json() == {"status": "live"}
        ready = client.get("/api/health/ready")
        assert ready.status_code == 200
        assert ready.json()["llm"] == "not_configured"
        assert client.get("/api/documents").json() == []
