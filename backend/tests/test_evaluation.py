from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_retrieval import choose_threshold, load_dataset


def test_retrieval_dataset_contains_balanced_in_domain_and_ood_questions() -> None:
    dataset = load_dataset(Path(__file__).parents[1] / "evaluation" / "retrieval_dataset.json")
    labels = [item["in_domain"] for item in dataset]
    assert len(dataset) >= 20
    assert labels.count(True) >= 10
    assert labels.count(False) >= 10


def test_threshold_selection_reports_margin_and_balanced_accuracy() -> None:
    result = choose_threshold(
        [
            {"question": "in 1", "in_domain": True, "score": 0.82},
            {"question": "in 2", "in_domain": True, "score": 0.73},
            {"question": "out 1", "in_domain": False, "score": 0.28},
            {"question": "out 2", "in_domain": False, "score": 0.35},
        ]
    )
    assert 0.35 < result["recommended_threshold"] < 0.73
    assert result["balanced_accuracy"] == 1.0
    assert result["separation_margin"] == 0.38
