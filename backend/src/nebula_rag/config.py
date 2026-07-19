from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="NEBULA_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Nébula RAG"
    documents_dir: Path = Path("storage/documents")
    data_dir: Path = Path("storage/data")
    seed_dir: Path = Path("../documents")
    chroma_dir: Path | None = None
    catalog_file: Path | None = None
    collection_name: str = "nebula_documents"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_device: str = "cpu"
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_model: str = "llama-3.1-8b-instant"
    llm_temperature: float = 0.1
    min_relevance: float = 0.36
    retrieval_candidates: int = 6
    answer_sources: int = 4
    max_upload_bytes: int = 20 * 1024 * 1024
    max_extracted_bytes: int = 4 * 1024 * 1024
    max_archive_members: int = 2_000
    max_json_depth: int = 32
    max_json_nodes: int = 100_000
    chunk_size: int = 900
    chunk_overlap: int = 140

    @property
    def catalog_path(self) -> Path:
        return self.catalog_file or self.data_dir / "catalog.sqlite3"

    @property
    def chroma_path(self) -> Path:
        return self.chroma_dir or self.data_dir / "chroma"

    def ensure_directories(self) -> None:
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
