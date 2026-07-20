from __future__ import annotations

from nebula_rag.domain import RetrievedChunk
from nebula_rag.reranker import CrossEncoderReranker


class _FakeCrossEncoderModel:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.pairs: list[tuple[str, str]] = []

    def predict(self, pairs):
        self.pairs = list(pairs)
        return self.scores


def test_rerank_reorders_by_sigmoid_score_and_leaves_metadata_untouched() -> None:
    candidates = [
        RetrievedChunk(id="a", text="Texto A", score=0.4, metadata={"title": "Doc A"}),
        RetrievedChunk(id="b", text="Texto B", score=0.9, metadata={"title": "Doc B"}),
    ]
    fake_model = _FakeCrossEncoderModel(scores=[-4.0, 4.0])  # A worse, B better
    reranker = CrossEncoderReranker("fake/model")
    reranker._model = fake_model  # skip the real download for this unit test

    reordered = reranker.rerank("pregunta", candidates)

    assert [item.id for item in reordered] == ["b", "a"]
    assert fake_model.pairs == [("pregunta", "Texto A"), ("pregunta", "Texto B")]
    assert 0.0 < reordered[0].score < 1.0  # sigmoid-bounded, not the raw logit
    assert reordered[0].score > reordered[1].score
    assert reordered[0].metadata == {"title": "Doc B"}  # untouched by rerank


def test_rerank_is_a_noop_for_zero_or_one_candidates() -> None:
    reranker = CrossEncoderReranker("fake/model")
    assert reranker.rerank("pregunta", []) == []
    single = [RetrievedChunk(id="a", text="Texto", score=0.5, metadata={})]
    assert reranker.rerank("pregunta", single) == single
    # Neither call needed the model, so it was never lazily constructed.
    assert reranker._model is None


def test_warm_forces_model_load_and_a_throwaway_predict() -> None:
    fake_model = _FakeCrossEncoderModel(scores=[0.0])
    reranker = CrossEncoderReranker("fake/model")
    reranker._model = fake_model

    reranker.warm()

    assert fake_model.pairs == [("ping", "pong")]
