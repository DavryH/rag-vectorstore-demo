import argparse
import json
import logging
import math
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.io_utils import write_jsonl
from shared.paths import QUERY_EVAL_PATH, STEP5_DIR
from shared.retrieval_pipeline import Chunk, load_chunks_for_tenant, tokenize_for_bm25
from shared.step3_outputs import find_query_plan

SUMMARY_FILENAME = "05-sparse-keyword-retrieval-summary.md"
OUTPUT_FILENAME = "sparse-keyword-retrieval.jsonl"


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text_for_required_terms(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def required_term_in_document(document_text: str, required_term: str) -> bool:
    normalized_document = normalize_text_for_required_terms(document_text)
    normalized_term = normalize_text_for_required_terms(required_term)
    if not normalized_term:
        return True

    term_tokens = normalized_term.split(" ")
    if len(term_tokens) == 1:
        pattern = re.compile(rf"(?<!\w){re.escape(term_tokens[0])}(?!\w)")
    else:
        phrase_pattern = r"\s+".join(re.escape(token) for token in term_tokens)
        pattern = re.compile(rf"(?<!\w){phrase_pattern}(?!\w)")
    return pattern.search(normalized_document) is not None


def build_sparse_query_text(sparse_query: dict[str, object]) -> str:
    positive_fields = ["required_terms", "include_terms", "phrases"]
    positive_terms: list[str] = []
    for field in positive_fields:
        values = sparse_query.get(field, [])
        if isinstance(values, list):
            positive_terms.extend(str(value).strip() for value in values if isinstance(value, str) and value.strip())

    excluded_terms: set[str] = set()
    exclude_values = sparse_query.get("exclude_terms", [])
    if isinstance(exclude_values, list):
        excluded_terms = {str(value).strip().lower() for value in exclude_values if isinstance(value, str) and value.strip()}

    return " ".join(term for term in positive_terms if term.lower() not in excluded_terms)


def required_terms_from_sparse_query(sparse_query: dict[str, object]) -> list[str]:
    values = sparse_query.get("required_terms", [])
    if not isinstance(values, list):
        return []
    return [normalize_text_for_required_terms(str(value)) for value in values if isinstance(value, str) and value.strip()]


def parse_doc_date(metadata: dict[str, Any]) -> date:
    raw = str(metadata.get("date", "")).strip()
    if not raw:
        return date.max
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return date.max


def extract_query_role(query_plan: dict[str, object]) -> str:
    role = str(query_plan.get("role", "")).strip().lower()
    return role if role else "unknown"


def extract_chunk_sensitivity(chunk: Chunk) -> str:
    return str(chunk.metadata.get("sensitivity", "")).strip().lower()


def can_role_access_sensitivity(role: str, sensitivity: str) -> bool:
    normalized_role = role.strip().lower()
    normalized_sensitivity = sensitivity.strip().lower()
    if normalized_sensitivity == "confidential":
        return normalized_role == "partner"
    return True


def filter_chunks_by_access(chunks: Sequence[Chunk], role: str) -> tuple[list[Chunk], list[str]]:
    accessible_chunks: list[Chunk] = []
    excluded_doc_ids: list[str] = []
    for chunk in chunks:
        sensitivity = extract_chunk_sensitivity(chunk)
        if can_role_access_sensitivity(role=role, sensitivity=sensitivity):
            accessible_chunks.append(chunk)
            continue
        doc_id = chunk.doc_id.strip()
        if doc_id and doc_id not in excluded_doc_ids:
            excluded_doc_ids.append(doc_id)
    return accessible_chunks, excluded_doc_ids


def aggregate_documents(chunks: Sequence[Chunk]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        doc_id = chunk.doc_id.strip()
        if not doc_id:
            raise RuntimeError("Step 05 encountered a chunk with missing doc_id while aggregating documents.")
        grouped.setdefault(doc_id, []).append(chunk)

    documents: list[dict[str, Any]] = []
    for doc_id in sorted(grouped):
        doc_chunks = sorted(grouped[doc_id], key=lambda item: item.chunk_id)
        canonical_metadata = dict(doc_chunks[0].metadata)
        for candidate_chunk in doc_chunks[1:]:
            if dict(candidate_chunk.metadata) != canonical_metadata:
                raise RuntimeError(f"Step 05 found inconsistent metadata across chunks for doc_id={doc_id}.")
        document_text = "\n".join(chunk.text.strip() for chunk in doc_chunks if chunk.text.strip()).strip()
        if not document_text:
            raise RuntimeError(f"Step 05 aggregated empty document text for doc_id={doc_id}.")
        documents.append({"doc_id": doc_id, "document_text": document_text, "document_metadata": canonical_metadata})
    return documents


def score_sparse_documents_bm25(documents: Sequence[dict[str, Any]], query_text: str) -> list[dict[str, Any]]:
    tokenized_docs = [tokenize_for_bm25(str(doc.get("document_text", ""))) for doc in documents]
    query_terms = tokenize_for_bm25(query_text)

    avg_dl = sum(len(doc) for doc in tokenized_docs) / max(len(tokenized_docs), 1)
    k1 = 1.5
    b = 0.75

    doc_freq: dict[str, int] = {}
    for doc in tokenized_docs:
        for token in set(doc):
            doc_freq[token] = doc_freq.get(token, 0) + 1

    scores: list[float] = []
    n_docs = max(len(tokenized_docs), 1)
    for doc in tokenized_docs:
        tf: dict[str, int] = {}
        for token in doc:
            tf[token] = tf.get(token, 0) + 1

        score = 0.0
        doc_len = max(len(doc), 1)
        for term in query_terms:
            freq = tf.get(term, 0)
            if freq == 0:
                continue
            df = doc_freq.get(term, 0)
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
            numer = freq * (k1 + 1)
            denom = freq + k1 * (1 - b + b * (doc_len / max(avg_dl, 1e-9)))
            score += idf * (numer / denom)
        scores.append(score)

    ranked_indices = sorted(
        range(len(documents)),
        key=lambda i: (
            -scores[i],
            parse_doc_date(dict(documents[i].get("document_metadata", {}))),
            str(documents[i].get("doc_id", "")),
        ),
    )

    ranked: list[dict[str, Any]] = []
    for rank, index in enumerate(ranked_indices, start=1):
        doc = dict(documents[index])
        ranked.append({**doc, "sparse_rank": rank, "sparse_score": float(scores[index])})
    return ranked


def annotate_documents_with_required_terms(
    ranked_documents: Sequence[dict[str, Any]], required_terms: list[str]
) -> tuple[list[dict[str, Any]], bool]:
    if not required_terms:
        return [
            {
                **dict(item),
                "required_terms_match": True,
                "required_terms_missing": [],
            }
            for item in ranked_documents
        ], False

    annotated: list[dict[str, Any]] = []
    for item in ranked_documents:
        document_text = str(item.get("document_text", ""))
        missing_terms = [term for term in required_terms if not required_term_in_document(document_text, term)]
        annotated.append(
            {
                **dict(item),
                "required_terms_match": len(missing_terms) == 0,
                "required_terms_missing": missing_terms,
            }
        )
    return annotated, True


def rank_annotated_documents(documents: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked_indices = sorted(
        range(len(documents)),
        key=lambda i: (
            not bool(documents[i].get("required_terms_match", False)),
            -float(documents[i].get("sparse_score", 0.0)),
            parse_doc_date(dict(documents[i].get("document_metadata", {}))),
            str(documents[i].get("doc_id", "")),
        ),
    )
    ranked: list[dict[str, Any]] = []
    for rank, index in enumerate(ranked_indices, start=1):
        ranked.append(
            {
                **dict(documents[index]),
                "sparse_rank": rank,
            }
        )
    return ranked


def build_sparse_retrieval_payload(query_id: str, query_plan: dict[str, object]) -> dict[str, object]:
    sparse_query = query_plan.get("sparse_query")
    if not isinstance(sparse_query, dict):
        raise RuntimeError("Step 03 query plan is missing sparse_query for Step 05 retrieval.")

    tenant_id = str(query_plan.get("tenant_id", "unknown"))
    role = extract_query_role(query_plan)

    tenant_chunks = load_chunks_for_tenant(tenant_id)
    accessible_chunks, excluded_doc_ids = filter_chunks_by_access(tenant_chunks, role=role)
    tenant_documents = aggregate_documents(tenant_chunks)
    accessible_documents = aggregate_documents(accessible_chunks)

    query_text = build_sparse_query_text(sparse_query)
    sparse_document_candidates = (
        score_sparse_documents_bm25(accessible_documents, query_text=query_text)
        if accessible_documents
        else []
    )

    required_terms = required_terms_from_sparse_query(sparse_query)
    sparse_document_candidates, required_filter_applied = annotate_documents_with_required_terms(
        sparse_document_candidates,
        required_terms,
    )
    sparse_document_candidates = rank_annotated_documents(sparse_document_candidates)
    required_terms_match_count = sum(
        1 for item in sparse_document_candidates if bool(item.get("required_terms_match", False))
    )
    required_terms_non_match_count = len(sparse_document_candidates) - required_terms_match_count
    no_accessible_required_term_match = bool(required_terms) and required_terms_match_count == 0

    required_filter_status = "not_applied"
    if required_filter_applied and required_terms_match_count == 0:
        required_filter_status = "required_terms_annotation_zero_matches"
    elif required_filter_applied:
        required_filter_status = "required_terms_annotation_ranked"

    return {
        "query_id": query_id,
        "input_query_plan": query_plan,
        "sparse_query": sparse_query,
        "access_filter": {
            "role": role,
            "applied": True,
            "total_chunk_count": len(tenant_chunks),
            "accessible_chunk_count": len(accessible_chunks),
            "excluded_chunk_count": len(tenant_chunks) - len(accessible_chunks),
            "total_document_count": len(tenant_documents),
            "accessible_document_count": len(accessible_documents),
            "excluded_document_count": len(tenant_documents) - len(accessible_documents),
            "excluded_doc_ids": excluded_doc_ids,
        },
        "required_terms_filter": {
            "required_terms": required_terms,
            "applied": required_filter_applied,
            "status": required_filter_status,
            "required_terms_match_count": required_terms_match_count,
            "required_terms_non_match_count": required_terms_non_match_count,
            "required_terms_zero_match": required_terms_match_count == 0,
            "no_accessible_required_term_match": no_accessible_required_term_match,
        },
        "coverage": {
            "accessible_document_count": len(accessible_documents),
            "candidate_count": len(sparse_document_candidates),
            "required_terms_match_count": required_terms_match_count,
            "required_terms_non_match_count": required_terms_non_match_count,
            "required_terms_zero_match": required_terms_match_count == 0,
            "no_accessible_required_term_match": no_accessible_required_term_match,
        },
        "entity_grounding": {
            "required_terms_present": bool(required_terms),
            "access_filter_applied": True,
            "no_accessible_required_term_match": no_accessible_required_term_match,
            "entity_grounding_failed": no_accessible_required_term_match,
            "short_circuit_reason": (
                "required_terms_zero_match_after_access_filter"
                if no_accessible_required_term_match
                else ""
            ),
        },
        "candidates": sparse_document_candidates,
        "status": "ready_for_rerank",
    }


def load_query_ids(query_id: str | None) -> list[str]:
    if query_id:
        return [query_id]
    rows = json.loads(QUERY_EVAL_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("query_eval.json must be a JSON array.")
    return [str(row.get("id", "")).strip() for row in rows if isinstance(row, dict) and str(row.get("id", "")).strip()]


def summarize_document_text(text: object) -> str:
    value = str(text or "").strip()
    return value if value else "(missing document text)"


def build_summary_markdown(payloads: list[dict[str, object]]) -> str:
    lines = ["# Step 05 Summaries", ""]
    for payload in payloads:
        query_id = str(payload.get("query_id", "unknown"))
        query_plan = payload.get("input_query_plan", {})
        if not isinstance(query_plan, dict):
            query_plan = {}
        sparse_query = payload.get("sparse_query", {})
        if not isinstance(sparse_query, dict):
            sparse_query = {}
        sparse_document_candidates = payload.get("candidates", [])
        if not isinstance(sparse_document_candidates, list):
            sparse_document_candidates = []
        access_filter = payload.get("access_filter", {})
        if not isinstance(access_filter, dict):
            access_filter = {}
        required_filter = payload.get("required_terms_filter", {})
        if not isinstance(required_filter, dict):
            required_filter = {}
        coverage = payload.get("coverage", {})
        if not isinstance(coverage, dict):
            coverage = {}

        sparse_query_text = build_sparse_query_text(sparse_query)

        lines.extend(
            [
                f"## Query `{query_id}`",
                "",
                f"- source query: `{query_plan.get('original_query', '(missing)')}`",
                f"- query role: `{access_filter.get('role', '(missing)')}`",
                f"- access filter applied: `{access_filter.get('applied', False)}`",
                f"- accessible documents: `{access_filter.get('accessible_document_count', 0)}` / `{access_filter.get('total_document_count', 0)}`",
                f"- excluded documents: `{access_filter.get('excluded_document_count', 0)}`",
                f"- excluded doc ids: `{', '.join(access_filter.get('excluded_doc_ids', [])) or '(none)'}`",
                f"- required sparse terms: `{', '.join(sparse_query.get('required_terms', [])) or '(none)'}`",
                f"- include sparse terms: `{', '.join(sparse_query.get('include_terms', [])) or '(none)'}`",
                f"- phrase terms: `{', '.join(sparse_query.get('phrases', [])) or '(none)'}`",
                f"- excluded terms: `{', '.join(sparse_query.get('exclude_terms', [])) or '(none)'}`",
                f"- constructed sparse query text: `{sparse_query_text or '(empty)'}`",
                f"- required-term annotation applied: `{required_filter.get('applied', False)}`",
                f"- required-term annotation status: `{required_filter.get('status', 'not_applied')}`",
                f"- candidate coverage: `{coverage.get('candidate_count', 0)}` / `{coverage.get('accessible_document_count', 0)}` accessible documents",
                f"- required-term matches: `{coverage.get('required_terms_match_count', 0)}`",
                f"- required-term non-matches: `{coverage.get('required_terms_non_match_count', 0)}`",
                f"- required-term zero-match: `{coverage.get('required_terms_zero_match', False)}`",
            ]
        )

        if sparse_document_candidates:
            lines.append("- top sparse document candidates (ranked):")
            for candidate in sparse_document_candidates[:5]:
                if not isinstance(candidate, dict):
                    continue
                lines.append(
                    "  "
                    + f"- `#{candidate.get('sparse_rank', '?')}` "
                    + f"doc `{candidate.get('doc_id', '?')}` (sparse_score `{float(candidate.get('sparse_score', 0.0)):.4f}`)"
                )
                lines.append(
                    "    "
                    + f"- required_terms_match: `{bool(candidate.get('required_terms_match', True))}`"
                )
                missing_terms = candidate.get("required_terms_missing", [])
                if isinstance(missing_terms, list):
                    missing_terms_display = ", ".join(str(term) for term in missing_terms if str(term).strip()) or "(none)"
                else:
                    missing_terms_display = "(none)"
                lines.append("    " + f"- required_terms_missing: `{missing_terms_display}`")
                lines.append("    - document text:")
                for text_line in summarize_document_text(candidate.get('document_text')).splitlines():
                    lines.append(f"      {text_line}")
        else:
            lines.append("- top sparse document candidates: `(none)`")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    query_ids = load_query_ids(args.query_id)

    def process(single_query_id: str) -> dict[str, object]:
        return build_sparse_retrieval_payload(single_query_id, find_query_plan(single_query_id))

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        retrieval_payloads = list(executor.map(process, query_ids))

    STEP5_DIR.mkdir(parents=True, exist_ok=True)
    output_path = STEP5_DIR / OUTPUT_FILENAME
    summary_path = STEP5_DIR / SUMMARY_FILENAME
    write_jsonl(output_path, retrieval_payloads)
    summary_path.write_text(build_summary_markdown(retrieval_payloads), encoding="utf-8")

    print(f"Wrote Step 05 artifact -> {output_path}")
    print(f"Wrote Step 05 summary -> {summary_path}")


if __name__ == "__main__":
    main()
