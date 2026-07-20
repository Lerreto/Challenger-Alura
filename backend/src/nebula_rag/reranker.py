from __future__ import annotations

import math
import threading
from dataclasses import replace
from typing import Any, Protocol

from .domain import RetrievedChunk


class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class CrossEncoderReranker:
    """Precision pass over the bi-encoder's broad recall set.

    Vector similarity alone can rank a topically-adjacent chunk above the one
    that actually answers the question. A cross-encoder attends to the query
    and each candidate jointly, which is slower but substantially more
    accurate — so it only runs over the small set that already passed the
    cheap cosine-similarity gate, never over the full index.
    """

    def __init__(self, model_name: str, device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model: Any | None = None
        self._lock = threading.RLock()

    def _get_model(self) -> Any:
        with self._lock:
            if self._model is None:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(
                    self.model_name, max_length=512, device=self.device
                )
            return self._model

    def warm(self) -> None:
        """Force the (slow, one-time) model download/load eagerly at startup,
        including a throwaway prediction to pay any first-inference warm-up
        cost too, so the first real user question doesn't pay that latency."""
        model = self._get_model()
        model.predict([("ping", "pong")])

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if len(candidates) <= 1:
            return candidates
        pairs = [(query, item.text) for item in candidates]
        raw_scores = self._get_model().predict(pairs)
        # Cross-encoder logits -> a bounded 0..1 confidence, on the same
        # scale as the cosine relevance score it replaces for display/sorting.
        rescored = [
            replace(item, score=1.0 / (1.0 + math.exp(-float(score))))
            for item, score in zip(candidates, raw_scores)
        ]
        return sorted(rescored, key=lambda item: item.score, reverse=True)
