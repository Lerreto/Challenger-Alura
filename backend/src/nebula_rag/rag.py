from __future__ import annotations

import logging

from .domain import ChatResult, RetrievedChunk, Source
from .errors import LLMUnavailableError
from .ingestion import VectorIndex
from .providers import LLMProvider
from .reranker import Reranker

logger = logging.getLogger(__name__)


FALLBACK_ANSWER = (
    "No encontré información suficiente en los documentos disponibles para responder esa pregunta."
)


class RagService:
    def __init__(
        self,
        vector_index: VectorIndex,
        llm: LLMProvider,
        min_relevance: float,
        retrieval_candidates: int = 6,
        answer_sources: int = 4,
        reranker: Reranker | None = None,
    ) -> None:
        self.vector_index = vector_index
        self.llm = llm
        self.min_relevance = min_relevance
        self.retrieval_candidates = retrieval_candidates
        self.answer_sources = answer_sources
        self.reranker = reranker

    def _eligible(self, search_query: str) -> list[RetrievedChunk]:
        # Stage 1 (recall): broad cosine-similarity search, gated by the
        # calibrated min_relevance threshold — this is what decides whether
        # there is evidence at all (abstention), so it stays on the raw
        # bi-encoder score regardless of reranking.
        candidates = self.vector_index.search(search_query, self.retrieval_candidates)
        passing = [item for item in candidates if item.score >= self.min_relevance]
        # Stage 2 (precision): reorder the passing set with a cross-encoder
        # before truncating to the few sources actually sent to the LLM.
        # Reranking is a quality layer, not a hard dependency: a model
        # load/inference failure degrades to the bi-encoder order instead of
        # breaking chat entirely.
        if self.reranker and len(passing) > 1:
            try:
                passing = self.reranker.rerank(search_query, passing)
            except Exception:
                logger.warning("reranker_failed_falling_back_to_cosine_order", exc_info=True)
        return passing[: self.answer_sources]

    def answer(
        self, question: str, recent_exchange: tuple[str, str] | None = None
    ) -> ChatResult:
        # Follow-ups ("dame la información dentro de ese .md") don't repeat the
        # topic in their own text, so the previous turn is folded into the
        # retrieval query only — this is what actually finds the right
        # document for a bare follow-up. recent_exchange is deliberately
        # NEVER shown to the LLM during generation: a small model given the
        # unverified prior answer as "context to resolve references" will
        # still echo facts from it into the new answer despite explicit
        # instructions not to, contaminating an otherwise fully-grounded
        # response. Anchoring retrieval on it is enough — the freshly
        # retrieved evidence is already about the right topic.
        search_query = (
            f"{recent_exchange[0]}\n{recent_exchange[1]}\n{question}"
            if recent_exchange
            else question
        )
        evidence = self._eligible(search_query)
        if not evidence:
            return ChatResult("insufficient_context", FALLBACK_ANSWER, [])
        if not self.llm.is_configured():
            raise LLMUnavailableError(
                "Hay evidencia documental, pero el proveedor de lenguaje no está configurado."
            )

        context_parts = []
        evidence_by_id = {item.id: item for item in evidence}
        for item in evidence:
            title = str(item.metadata.get("title") or "Documento")
            location = str(item.metadata.get("location") or "Sin ubicación")
            context_parts.append(
                f"[chunk_id={item.id}]\n"
                f"[title={title} | location={location}]\n{item.text}"
            )
        generated = self.llm.generate(question, "\n\n".join(context_parts))
        cited_ids = list(dict.fromkeys(generated.cited_chunk_ids))
        if (
            not generated.answer.strip()
            or not cited_ids
            or any(chunk_id not in evidence_by_id for chunk_id in cited_ids)
        ):
            return ChatResult("insufficient_context", FALLBACK_ANSWER, [])

        sources = []
        for chunk_id in cited_ids:
            item = evidence_by_id[chunk_id]
            sources.append(
                Source(
                    chunk_id=chunk_id,
                    document_id=str(item.metadata.get("document_id") or ""),
                    title=str(item.metadata.get("title") or "Documento"),
                    location=str(item.metadata.get("location") or "Sin ubicación"),
                    excerpt=item.text[:360].strip(),
                    score=round(item.score, 4),
                )
            )
        return ChatResult("answered", generated.answer.strip(), sources)
