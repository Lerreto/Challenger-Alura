from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from nebula_rag.ingestion import chunk_context_header
from nebula_rag.loaders import SUPPORTED_EXTENSIONS, extract_sections, read_frontmatter


def load_dataset(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("question"), str)
        and isinstance(item.get("in_domain"), bool)
        for item in payload
    ):
        raise ValueError("invalid_retrieval_dataset")
    return payload


def _balanced_accuracy(rows: list[dict[str, Any]], threshold: float) -> float:
    positives = [row for row in rows if row["in_domain"]]
    negatives = [row for row in rows if not row["in_domain"]]
    sensitivity = sum(row["score"] >= threshold for row in positives) / len(positives)
    specificity = sum(row["score"] < threshold for row in negatives) / len(negatives)
    return (sensitivity + specificity) / 2


def choose_threshold(rows: list[dict[str, Any]]) -> dict[str, float]:
    positives = [float(row["score"]) for row in rows if row["in_domain"]]
    negatives = [float(row["score"]) for row in rows if not row["in_domain"]]
    if not positives or not negatives:
        raise ValueError("both_classes_are_required")
    unique_scores = sorted(set(positives + negatives))
    candidates = [
        (left + right) / 2 for left, right in zip(unique_scores, unique_scores[1:])
    ]
    candidates.extend([unique_scores[0] - 1e-6, unique_scores[-1] + 1e-6])
    threshold = max(
        candidates,
        key=lambda value: (_balanced_accuracy(rows, value), -abs(value - 0.5)),
    )
    return {
        "recommended_threshold": round(threshold, 6),
        "balanced_accuracy": round(_balanced_accuracy(rows, threshold), 6),
        "separation_margin": round(min(positives) - max(negatives), 6),
        "min_in_domain_score": round(min(positives), 6),
        "max_out_of_domain_score": round(max(negatives), 6),
    }


def _load_corpus(documents_dir: Path) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=140,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks: list[str] = []
    for path in sorted(documents_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            title = str(
                read_frontmatter(path).get("title")
                or path.stem.replace("-", " ").replace("_", " ").title()
            )
            for section in extract_sections(path):
                header = chunk_context_header(title, section.location)
                chunks.extend(
                    f"{header}\n{text}" for text in splitter.split_text(section.text)
                )
    if not chunks:
        raise ValueError("empty_document_corpus")
    return chunks


def evaluate(
    dataset_path: Path, documents_dir: Path, embedding_model: str
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    corpus = _load_corpus(documents_dir)
    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        encode_kwargs={"normalize_embeddings": True},
        query_encode_kwargs={"normalize_embeddings": True},
    )
    document_vectors = embeddings.embed_documents(corpus)
    question_vectors = embeddings.embed_query
    scored: list[dict[str, Any]] = []
    for item in dataset:
        query_vector = question_vectors(item["question"])
        score = max(
            sum(left * right for left, right in zip(query_vector, vector, strict=True))
            for vector in document_vectors
        )
        scored.append({**item, "score": round(float(score), 6)})
    calibration = choose_threshold(scored)
    return {
        "embedding_model": embedding_model,
        "documents_dir": str(documents_dir),
        "corpus_chunks": len(corpus),
        "questions": len(scored),
        **calibration,
        "results": scored,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate the retrieval threshold with the real embedding model."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluation/retrieval_dataset.json"),
    )
    parser.add_argument("--documents", type=Path, default=Path("../documents"))
    parser.add_argument(
        "--model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = evaluate(args.dataset, args.documents, args.model)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
