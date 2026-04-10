import argparse
import hashlib
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.io_utils import read_jsonl, write_jsonl
from shared.paths import QUERY_EVAL_PATH, ROOT, STEP4_DIR, STEP5_DIR, STEP6_DIR

DENSE_RRF_K = 60
SPARSE_RRF_K = 60
DENSE_WEIGHT = 1.0
SPARSE_WEIGHT = 1.0
MAX_DENSE_CANDIDATES = 20
DEFAULT_FINAL_CANDIDATES = 8
MIN_FINAL_CANDIDATES = 5
SUMMARY_FILENAME = "06-rerank-summary.md"
OUTPUT_FILENAME = "rerank.jsonl"

RECENCY_INTENT_TERMS = {"latest", "most recent", "current", "newest", "recent", "today"}
TIMELINE_INTENT_TERMS = {
    "timeline",
    "progression",
    "over time",
    "from intro to latest",
    "from first contact to latest",
    "first contact",
}
ROLE_TITLE_PHRASES = {
    "ceo", "cfo", "cto", "coo", "founder", "co-founder", "vp", "vice president", "director", "manager", "partner", "board", "chief",
}
NON_PERSON_LEADING_TERMS = {"project", "operation", "initiative", "program", "plan", "deal"}

COMPANY_MATCH_BOOST = 0.08
PERSON_MATCH_BOOST = 0.08
ROLE_MATCH_BOOST = 0.05
BUSINESS_TERM_MATCH_BOOST = 0.06
RECENCY_BOOST = 0.04


def load_query_ids(query_id: str | None) -> list[str]:
    if query_id:
        return [query_id]
    rows = json.loads(QUERY_EVAL_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("query_eval.json must be a JSON array.")
    return [str(row.get("id", "")).strip() for row in rows if isinstance(row, dict) and str(row.get("id", "")).strip()]


def rows_by_query_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("query_id", "")): row for row in rows if isinstance(row, dict) and str(row.get("query_id", ""))}


def normalize_terms(values: Sequence[object]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = str(value).strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        unique.append(term)
    return unique


def extract_company_scope_terms(query_plan: dict[str, Any]) -> list[str]:
    explicit_terms = query_plan.get("company_scope_terms")
    if isinstance(explicit_terms, list):
        terms = normalize_terms(explicit_terms)
        if terms:
            return terms
    return []


def extract_business_terms(query_plan: dict[str, Any]) -> list[str]:
    sparse_query = query_plan.get("sparse_query", {})
    if not isinstance(sparse_query, dict):
        return []
    term_pool: list[object] = []
    for field in ("required_terms", "include_terms", "phrases"):
        values = sparse_query.get(field, [])
        if isinstance(values, list):
            term_pool.extend(values)
    return normalize_terms(term_pool)


def extract_person_name_terms(query_text: str) -> list[str]:
    people_terms: list[str] = []
    tokens = query_text.split()
    for index in range(len(tokens) - 1):
        first = tokens[index].strip(".,!?;:()[]{}\"'")
        second = tokens[index + 1].strip(".,!?;:()[]{}\"'")
        if first.lower() in NON_PERSON_LEADING_TERMS:
            continue
        if first.istitle() and second.istitle() and first.isalpha() and second.isalpha() and len(first) > 1 and len(second) > 1:
            people_terms.append(f"{first.lower()} {second.lower()}")
    return normalize_terms(people_terms)


def extract_role_phrases(query_text: str) -> list[str]:
    lowered_query = query_text.lower()
    return [phrase for phrase in sorted(ROLE_TITLE_PHRASES) if phrase in lowered_query]


def parse_doc_date(candidate: dict[str, Any]) -> date | None:
    metadata = candidate.get("metadata", {})
    if not isinstance(metadata, dict):
        return None
    raw_date = str(metadata.get("date", "")).strip()
    if not raw_date:
        return None
    try:
        return date.fromisoformat(raw_date)
    except ValueError:
        return None


def has_any_term(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def count_term_hits(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term in text)


def has_recency_intent(query_text: str) -> bool:
    lowered_query = query_text.lower()
    return any(term in lowered_query for term in RECENCY_INTENT_TERMS)


def has_timeline_intent(query_text: str) -> bool:
    lowered_query = query_text.lower()
    if " from " in f" {lowered_query} " and " to " in f" {lowered_query} ":
        return True
    return any(term in lowered_query for term in TIMELINE_INTENT_TERMS)


def candidate_identity(candidate: dict[str, Any]) -> str:
    dense_candidate_id = str(candidate.get("dense_candidate_id", "")).strip()
    if dense_candidate_id:
        return dense_candidate_id

    doc_id = str(candidate.get("doc_id", "")).strip()
    text = str(candidate.get("text", "")).strip()
    metadata = candidate.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    if not doc_id or not text:
        raise RuntimeError("Step 06 dense candidate is missing dense_candidate_id and cannot derive legacy identity.")

    chunk_id = str(candidate.get("chunk_id", "")).strip()
    dense_result_id = str(candidate.get("dense_result_id", "")).strip()
    payload = {
        "doc_id": doc_id,
        "text": text,
        "metadata_subset": build_stable_metadata_subset(metadata),
        "trace": {
            "chunk_id": chunk_id,
            "dense_result_id": dense_result_id,
        },
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"legacy_densecand_{hashlib.sha256(payload_json.encode('utf-8')).hexdigest()}"


def build_stable_metadata_subset(metadata: dict[str, Any]) -> dict[str, str]:
    stable_fields = ("tenant_id", "company", "date", "source_file", "source_path", "sensitivity")
    return {field: str(metadata.get(field, "")).strip() for field in stable_fields if str(metadata.get(field, "")).strip()}


def semantic_component(rank: int | None) -> float:
    if rank is None:
        return 0.0
    return DENSE_WEIGHT * (1.0 / (DENSE_RRF_K + rank))


def sparse_component(rank: int | None) -> float:
    if rank is None:
        return 0.0
    return SPARSE_WEIGHT * (1.0 / (SPARSE_RRF_K + rank))


def dedupe_dense_candidates(semantic_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for candidate in semantic_candidates:
        if not isinstance(candidate, dict):
            raise RuntimeError("Step 06 received a non-dict dense candidate row.")
        identity = candidate_identity(candidate)
        doc_id = str(candidate.get("doc_id", "")).strip()
        text = str(candidate.get("text", "")).strip()
        metadata = candidate.get("metadata", {})
        if not doc_id:
            raise RuntimeError(f"Step 06 dense candidate identity={identity} is missing doc_id.")
        if not text:
            raise RuntimeError(f"Step 06 dense candidate identity={identity} is missing text.")
        if not isinstance(metadata, dict):
            raise RuntimeError(f"Step 06 dense candidate identity={identity} metadata must be a dict.")

        existing = deduped.get(identity)
        if existing is None:
            deduped[identity] = dict(candidate)
            continue

        conflict_fields = []
        for field in ("doc_id", "text", "metadata"):
            if existing.get(field) != candidate.get(field):
                conflict_fields.append(field)
        if conflict_fields:
            raise RuntimeError(
                f"Step 06 dense dedupe conflict for identity={identity}; mismatched fields={','.join(conflict_fields)}."
            )

    return sorted(
        deduped.values(),
        key=lambda item: (int(item.get("semantic_rank", 10**9)), str(item.get("doc_id", "")), candidate_identity(item)),
    )


def sparse_documents_by_doc_id(sparse_candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    docs: dict[str, dict[str, Any]] = {}
    for row in sparse_candidates:
        if not isinstance(row, dict):
            raise RuntimeError("Step 06 received a non-dict sparse candidate row.")
        doc_id = str(row.get("doc_id", "")).strip()
        if not doc_id:
            raise RuntimeError("Step 06 sparse document candidate is missing doc_id.")
        if doc_id in docs:
            if docs[doc_id] != row:
                raise RuntimeError(f"Step 06 sparse candidates contain duplicate conflicting rows for doc_id={doc_id}.")
            continue
        docs[doc_id] = dict(row)
    return docs


def metadata_explicitly_matches_required_terms(metadata: dict[str, Any], required_terms: list[str]) -> bool:
    if not required_terms:
        return True
    searchable_values: list[str] = []
    for key, value in metadata.items():
        if isinstance(value, str):
            searchable_values.append(value.lower())
        elif isinstance(value, list):
            searchable_values.extend(str(item).lower() for item in value)
        elif isinstance(value, dict):
            searchable_values.extend(str(item).lower() for item in value.values())
        else:
            searchable_values.append(str(value).lower())
    combined = " ".join(searchable_values)
    return any(term in combined for term in required_terms)


def build_recency_map(candidates: list[dict[str, Any]]) -> dict[str, float]:
    dated_rows: list[tuple[str, int]] = []
    for candidate in candidates:
        parsed_date = parse_doc_date(candidate)
        if parsed_date is None:
            continue
        dated_rows.append((candidate_identity(candidate), parsed_date.toordinal()))
    if not dated_rows:
        return {}
    ordinal_values = [value for _, value in dated_rows]
    oldest = min(ordinal_values)
    newest = max(ordinal_values)
    if oldest == newest:
        return {identity: 1.0 for identity, _ in dated_rows}
    return {identity: (ordinal - oldest) / (newest - oldest) for identity, ordinal in dated_rows}


def deterministic_rerank_sort_key(row: dict[str, Any]) -> tuple[float, float, str, str]:
    return (
        -float(row.get("deterministic_score", 0.0)),
        -float(row.get("mixed_score", 0.0)),
        str(row.get("doc_id", "")),
        candidate_identity(row),
    )


def apply_deterministic_adjustments(
    candidates: list[dict[str, Any]],
    query_text: str,
    query_plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    company_terms = extract_company_scope_terms(query_plan)
    business_terms = extract_business_terms(query_plan)
    person_terms = extract_person_name_terms(query_text)
    role_terms = extract_role_phrases(query_text)
    recency_intent = has_recency_intent(query_text)
    timeline_intent = has_timeline_intent(query_text)
    recency_by_identity = build_recency_map(candidates)

    adjusted: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_text = str(candidate.get("text", "")).lower()
        identity = candidate_identity(candidate)
        parent_sparse_required_terms_match = bool(candidate.get("parent_sparse_required_terms_match", True))

        company_match = has_any_term(candidate_text, company_terms) if company_terms else False
        person_match = has_any_term(candidate_text, person_terms) if person_terms else False
        role_match = has_any_term(candidate_text, role_terms) if role_terms else False
        business_hits = count_term_hits(candidate_text, business_terms)
        business_match_score = min(1.0, business_hits / 3.0)

        if not parent_sparse_required_terms_match:
            company_match = False
            person_match = False
            business_hits = 0
            business_match_score = 0.0

        boost = 0.0
        if company_match:
            boost += COMPANY_MATCH_BOOST
        if person_match:
            boost += PERSON_MATCH_BOOST
        if role_match:
            boost += ROLE_MATCH_BOOST
        boost += BUSINESS_TERM_MATCH_BOOST * business_match_score

        recency_score = recency_by_identity.get(identity, 0.0)
        if recency_intent:
            boost += RECENCY_BOOST * recency_score

        deterministic_score = float(candidate.get("mixed_score", 0.0)) + boost
        adjusted.append(
            {
                **candidate,
                "company_match": company_match,
                "person_match": person_match,
                "role_match": role_match,
                "business_term_hits": business_hits,
                "recency_score": recency_score,
                "deterministic_boost": boost,
                "deterministic_score": deterministic_score,
            }
        )

    return sorted(adjusted, key=deterministic_rerank_sort_key), {
        "company_scope_terms": company_terms,
        "person_terms": person_terms,
        "role_terms": role_terms,
        "business_terms": business_terms,
        "query_time_intent": recency_intent,
        "query_timeline_intent": timeline_intent,
        "candidate_pool_size": len(candidates),
    }


def choose_final_candidates(scored_candidates: list[dict[str, Any]], timeline_intent: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    target_count = min(len(scored_candidates), max(MIN_FINAL_CANDIDATES, DEFAULT_FINAL_CANDIDATES))
    selected = list(scored_candidates[:target_count])
    selection_details = {"target_count": target_count, "timeline_preserved_earliest": False, "timeline_preserved_latest": False}
    if not timeline_intent or not selected:
        return selected, selection_details

    dated_candidates: list[tuple[dict[str, Any], date]] = []
    for candidate in scored_candidates:
        parsed_date = parse_doc_date(candidate)
        if parsed_date is None:
            continue
        dated_candidates.append((candidate, parsed_date))
    if not dated_candidates:
        return selected, selection_details

    earliest_candidate = min(dated_candidates, key=lambda row: (row[1], str(row[0].get("doc_id", "")), candidate_identity(row[0])))[0]
    latest_candidate = max(
        dated_candidates,
        key=lambda row: (
            row[1],
            -float(row[0].get("deterministic_score", 0.0)),
            -float(row[0].get("mixed_score", 0.0)),
            str(row[0].get("doc_id", "")),
            candidate_identity(row[0]),
        ),
    )[0]

    selected_ids = {candidate_identity(row) for row in selected}
    if candidate_identity(earliest_candidate) not in selected_ids:
        selected[-1] = earliest_candidate
    selection_details["timeline_preserved_earliest"] = True

    selected_ids = {candidate_identity(row) for row in selected}
    if candidate_identity(latest_candidate) not in selected_ids:
        replacement_index = len(selected) - 1
        if candidate_identity(selected[-1]) == candidate_identity(earliest_candidate) and len(selected) > 1:
            replacement_index = len(selected) - 2
        selected[replacement_index] = latest_candidate
    selection_details["timeline_preserved_latest"] = True

    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for candidate in selected:
        identity = candidate_identity(candidate)
        if identity in seen_ids:
            continue
        seen_ids.add(identity)
        deduped.append(candidate)
    if len(deduped) < target_count:
        for candidate in scored_candidates:
            identity = candidate_identity(candidate)
            if identity in seen_ids:
                continue
            deduped.append(candidate)
            seen_ids.add(identity)
            if len(deduped) >= target_count:
                break
    return deduped, selection_details


def assign_relevance_scores(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    scored: list[dict[str, Any]] = []
    for rank, candidate in enumerate(candidates, start=1):
        relevance_score = max(1, 6 - rank)
        scored.append({**candidate, "relevance_score": relevance_score})
    return scored


def rerank_for_query(query_id: str, semantic_row: dict[str, Any], sparse_row: dict[str, Any]) -> dict[str, Any]:
    query_plan = semantic_row.get("input_query_plan", {})
    query_text = str(query_plan.get("original_query", ""))

    semantic_chunk_candidates_input = semantic_row.get("candidates", [])
    sparse_document_candidates_input = sparse_row.get("candidates", [])
    if not isinstance(semantic_chunk_candidates_input, list):
        raise RuntimeError(f"Step 06 query_id={query_id} semantic candidates must be a list.")
    if not isinstance(sparse_document_candidates_input, list):
        raise RuntimeError(f"Step 06 query_id={query_id} sparse candidates must be a list.")

    semantic_chunk_candidates = dedupe_dense_candidates(semantic_chunk_candidates_input)
    semantic_chunk_candidates_for_fusion = semantic_chunk_candidates[:MAX_DENSE_CANDIDATES]
    sparse_documents_by_id = sparse_documents_by_doc_id(sparse_document_candidates_input)
    required_terms = normalize_terms((sparse_row.get("required_terms_filter", {}) or {}).get("required_terms", []))
    sparse_required_terms_zero_match = bool((sparse_row.get("required_terms_filter", {}) or {}).get("required_terms_zero_match", False))

    if not semantic_chunk_candidates_for_fusion:
        return {
            "query_id": query_id,
            "input_dense_chunk_candidates": semantic_chunk_candidates_input,
            "input_sparse_document_candidates": sparse_document_candidates_input,
            "fusion_config": {
                "dense_rrf_k": DENSE_RRF_K,
                "sparse_rrf_k": SPARSE_RRF_K,
                "dense_weight": DENSE_WEIGHT,
                "sparse_weight": SPARSE_WEIGHT,
                "mode": "mixed_granularity_dense_chunk_plus_parent_document_lexical",
            },
            "selection_config": {
                "company_scope_terms": [],
                "person_terms": [],
                "role_terms": [],
                "business_terms": [],
                "query_time_intent": False,
                "query_timeline_intent": False,
                "candidate_pool_size": 0,
                "max_dense_candidates": MAX_DENSE_CANDIDATES,
                "min_final_candidates": MIN_FINAL_CANDIDATES,
                "default_final_candidates": DEFAULT_FINAL_CANDIDATES,
                "final_count": 0,
                "no_accessible_required_term_match": False,
                "entity_grounding_failed": False,
                "anchor_gate_triggered": True,
                "short_circuit_reason": "no_dense_candidates_to_evaluate",
            },
            "all_scored_candidates": [],
            "ranked_candidates": [],
            "status": "short_circuit_no_accessible_evidence",
        }

    missing_sparse_doc_ids = sorted(
        {
            str(row.get("doc_id", "")).strip()
            for row in semantic_chunk_candidates_for_fusion
            if str(row.get("doc_id", "")).strip() not in sparse_documents_by_id
        }
    )
    if missing_sparse_doc_ids:
        raise RuntimeError(
            f"Step 06 query_id={query_id} missing Step 05 sparse document coverage for doc_ids={missing_sparse_doc_ids}."
        )

    mixed_chunk_candidates: list[dict[str, Any]] = []
    for semantic_chunk_candidate in semantic_chunk_candidates_for_fusion:
        doc_id = str(semantic_chunk_candidate.get("doc_id", "")).strip()
        sparse_document_candidate = sparse_documents_by_id[doc_id]

        semantic_rank_raw = semantic_chunk_candidate.get("semantic_rank")
        semantic_rank = int(semantic_rank_raw) if isinstance(semantic_rank_raw, int) else None
        parent_sparse_rank_raw = sparse_document_candidate.get("sparse_rank")
        parent_sparse_rank = int(parent_sparse_rank_raw) if isinstance(parent_sparse_rank_raw, int) else None

        semantic_signal = semantic_component(semantic_rank)
        parent_sparse_required_terms_match = bool(sparse_document_candidate.get("required_terms_match", True))
        sparse_doc_metadata = sparse_document_candidate.get("document_metadata", {})
        parent_sparse_metadata_entity_match = (
            metadata_explicitly_matches_required_terms(sparse_doc_metadata, required_terms)
            if isinstance(sparse_doc_metadata, dict)
            else False
        )
        entity_linked = parent_sparse_required_terms_match or parent_sparse_metadata_entity_match
        parent_sparse_signal = sparse_component(parent_sparse_rank) if parent_sparse_required_terms_match else 0.0
        mixed_score = semantic_signal + parent_sparse_signal

        mixed_chunk_candidates.append(
            {
                "dense_candidate_id": candidate_identity(semantic_chunk_candidate),
                "doc_id": doc_id,
                "chunk_id": str(semantic_chunk_candidate.get("chunk_id", "")).strip(),
                "dense_result_id": str(semantic_chunk_candidate.get("dense_result_id", "")).strip(),
                "text": str(semantic_chunk_candidate.get("text", "")).strip(),
                "metadata": (
                    dict(semantic_chunk_candidate.get("metadata", {}))
                    if isinstance(semantic_chunk_candidate.get("metadata", {}), dict)
                    else {}
                ),
                "semantic_rank": semantic_rank,
                "semantic_score": float(semantic_chunk_candidate.get("semantic_score", 0.0)),
                "semantic_signal": semantic_signal,
                "parent_sparse_rank": parent_sparse_rank,
                "parent_sparse_score": float(sparse_document_candidate.get("sparse_score", 0.0)),
                "parent_sparse_signal": parent_sparse_signal,
                "parent_sparse_required_terms_match": parent_sparse_required_terms_match,
                "parent_sparse_metadata_entity_match": parent_sparse_metadata_entity_match,
                "entity_linked": entity_linked,
                "parent_sparse_missing": False,
                "mixed_score": mixed_score,
            }
        )

    if required_terms:
        mixed_chunk_candidates = [
            candidate for candidate in mixed_chunk_candidates if bool(candidate.get("entity_linked", False))
        ]

    if not mixed_chunk_candidates:
        return {
            "query_id": query_id,
            "input_dense_chunk_candidates": semantic_chunk_candidates_input,
            "input_sparse_document_candidates": sparse_document_candidates_input,
            "fusion_config": {
                "dense_rrf_k": DENSE_RRF_K,
                "sparse_rrf_k": SPARSE_RRF_K,
                "dense_weight": DENSE_WEIGHT,
                "sparse_weight": SPARSE_WEIGHT,
                "mode": "mixed_granularity_dense_chunk_plus_parent_document_lexical",
            },
            "selection_config": {
                "company_scope_terms": [],
                "person_terms": [],
                "role_terms": [],
                "business_terms": [],
                "query_time_intent": False,
                "query_timeline_intent": False,
                "candidate_pool_size": 0,
                "max_dense_candidates": MAX_DENSE_CANDIDATES,
                "min_final_candidates": MIN_FINAL_CANDIDATES,
                "default_final_candidates": DEFAULT_FINAL_CANDIDATES,
                "final_count": 0,
                "no_accessible_required_term_match": sparse_required_terms_zero_match,
                "entity_grounding_failed": bool(required_terms),
                "anchor_gate_triggered": True,
                "short_circuit_reason": "no_candidates_after_entity_linking",
            },
            "all_scored_candidates": [],
            "ranked_candidates": [],
            "status": "short_circuit_no_accessible_evidence",
        }

    reranked_chunk_candidates, feature_config = apply_deterministic_adjustments(
        mixed_chunk_candidates,
        query_text,
        query_plan,
    )
    final_candidates, selection_config = choose_final_candidates(
        scored_candidates=reranked_chunk_candidates,
        timeline_intent=bool(feature_config.get("query_timeline_intent", False)),
    )
    ranked_candidates = assign_relevance_scores(final_candidates)

    return {
        "query_id": query_id,
        "input_dense_chunk_candidates": semantic_chunk_candidates_input,
        "input_sparse_document_candidates": sparse_document_candidates_input,
        "fusion_config": {
            "dense_rrf_k": DENSE_RRF_K,
            "sparse_rrf_k": SPARSE_RRF_K,
            "dense_weight": DENSE_WEIGHT,
            "sparse_weight": SPARSE_WEIGHT,
            "mode": "mixed_granularity_dense_chunk_plus_parent_document_lexical",
        },
        "selection_config": {
            **feature_config,
            **selection_config,
            "max_dense_candidates": MAX_DENSE_CANDIDATES,
            "min_final_candidates": MIN_FINAL_CANDIDATES,
            "default_final_candidates": DEFAULT_FINAL_CANDIDATES,
            "final_count": len(ranked_candidates),
            "no_accessible_required_term_match": sparse_required_terms_zero_match,
            "entity_grounding_failed": False,
            "anchor_gate_triggered": False,
            "short_circuit_reason": "",
        },
        "all_scored_candidates": reranked_chunk_candidates,
        "ranked_candidates": ranked_candidates,
        "status": "ready_for_quote_extraction",
    }


def summarize_chunk_text(text: object) -> str:
    value = str(text or "").strip()
    return value if value else "(missing chunk text)"


def build_summary_markdown(rows: list[dict[str, Any]]) -> str:
    config_line = "(missing)"
    if rows and isinstance(rows[0], dict):
        cfg = rows[0].get("fusion_config", {})
        if isinstance(cfg, dict):
            config_line = (
                f"dense_rrf_k={cfg.get('dense_rrf_k', '?')}, sparse_rrf_k={cfg.get('sparse_rrf_k', '?')}, "
                f"dense_weight={cfg.get('dense_weight', '?')}, sparse_weight={cfg.get('sparse_weight', '?')}"
            )

    lines = [
        "# Step 06 Summaries",
        "",
        "## Run configuration",
        "",
        f"- mixed-granularity fusion config: `{config_line}`",
        "- dense input granularity: `chunk`",
        "- sparse input granularity: `document`",
        "- final ranking granularity: `chunk`",
        "",
    ]
    for row in rows:
        query_id = str(row.get("query_id", "unknown"))
        ranked_candidates = row.get("ranked_candidates", [])
        selection_config = row.get("selection_config", {})
        if not isinstance(ranked_candidates, list):
            ranked_candidates = []

        lines.extend(
            [
                f"## Query `{query_id}`",
                "",
                f"- company_scope_terms: `{', '.join(selection_config.get('company_scope_terms', [])) or '(none)'}`",
                f"- role_terms: `{', '.join(selection_config.get('role_terms', [])) or '(none)'}`",
                f"- query recency intent detected: `{selection_config.get('query_time_intent', False)}`",
                f"- query timeline intent detected: `{selection_config.get('query_timeline_intent', False)}`",
                f"- selected chunk candidates: `{selection_config.get('final_count', len(ranked_candidates))}`",
                "",
            ]
        )

        if ranked_candidates:
            lines.append("- top mixed-granularity candidates (ranked chunks):")
            for candidate in ranked_candidates[:5]:
                if not isinstance(candidate, dict):
                    continue
                lines.append(
                    "  "
                    + f"- `#{candidate.get('relevance_score', 0)}` doc `{candidate.get('doc_id', '?')}` "
                    + f"(semantic_rank `{candidate.get('semantic_rank', '?')}`, parent_sparse_rank `{candidate.get('parent_sparse_rank', '?')}`, "
                    + f"required_terms_match `{candidate.get('parent_sparse_required_terms_match', True)}`, "
                    + f"mixed `{float(candidate.get('mixed_score', 0.0)):.4f}`, boost `{float(candidate.get('deterministic_boost', 0.0)):.4f}`, "
                    + f"score `{float(candidate.get('deterministic_score', 0.0)):.4f}`)"
                )
                lines.append("    - chunk text:")
                for chunk_line in summarize_chunk_text(candidate.get("text")).splitlines():
                    lines.append(f"      {chunk_line}")
        else:
            lines.append("- top mixed-granularity candidates: `(none)`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    query_ids = load_query_ids(args.query_id)
    semantic_by_id = rows_by_query_id(read_jsonl(STEP4_DIR / "semantic-retrieval.jsonl"))
    sparse_by_id = rows_by_query_id(read_jsonl(STEP5_DIR / "sparse-keyword-retrieval.jsonl"))

    def process(single_query_id: str) -> dict[str, Any]:
        semantic_row = semantic_by_id.get(single_query_id)
        sparse_row = sparse_by_id.get(single_query_id)
        if semantic_row is None or sparse_row is None:
            raise RuntimeError(f"Missing Step 04/05 artifacts for query_id={single_query_id}")
        return rerank_for_query(single_query_id, semantic_row, sparse_row)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        reranked_rows = list(executor.map(process, query_ids))

    STEP6_DIR.mkdir(parents=True, exist_ok=True)
    output_path = STEP6_DIR / OUTPUT_FILENAME
    write_jsonl(output_path, reranked_rows)

    summary_path = STEP6_DIR / SUMMARY_FILENAME
    summary_path.write_text(build_summary_markdown(reranked_rows), encoding="utf-8")

    print(f"Wrote Step 06 artifact -> {output_path.relative_to(ROOT)}")
    print(f"Wrote Step 06 summary -> {summary_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
