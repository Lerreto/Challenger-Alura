from __future__ import annotations

from .domain import ChatResult, RetrievedChunk, Source
from .errors import LLMUnavailableError
from .ingestion import VectorIndex
from .providers import LLMProvider


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
    ) -> None:
        self.vector_index = vector_index
        self.llm = llm
        self.min_relevance = min_relevance
        self.retrieval_candidates = retrieval_candidates
        self.answer_sources = answer_sources

    def _eligible(self, search_query: str) -> list[RetrievedChunk]:
        candidates = self.vector_index.search(search_query, self.retrieval_candidates)
        return [item for item in candidates if item.score >= self.min_relevance][
            : self.answer_sources
        ]

    def answer(
        self, question: str, recent_exchange: tuple[str, str] | None = None
    ) -> ChatResult:
        # Follow-ups ("dame la información dentro de ese .md") don't repeat the
        # topic in their own text, so the previous turn is folded into the
        # retrieval query. The LLM still only cites newly retrieved chunks.
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
        generated = self.llm.generate(
            question, "\n\n".join(context_parts), recent_exchange=recent_exchange
        )
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
