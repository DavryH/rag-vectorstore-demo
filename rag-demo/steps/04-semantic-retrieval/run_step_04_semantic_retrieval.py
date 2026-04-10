import argparse
import hashlib
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.io_utils import read_jsonl, write_jsonl
from shared.openai_client import get_openai_client
from shared.paths import STEP4_DIR, VECTOR_STORE_MANIFEST_PATH
from shared.step3_outputs import find_query_plan

SUMMARY_FILENAME = "04-semantic-retrieval-summary.md"
OUTPUT_FILENAME = "semantic-retrieval.jsonl"
DENSE_TOP_K = 25
RETRIEVAL_MODE = "openai_vector_store_search_no_rerank"


def build_semantic_retrieval_payload(query_id: str, query_plan: dict[str, object]) -> dict[str, object]:
    retrieval_query = extract_retrieval_query(query_plan)
    tenant_id = str(query_plan.get("tenant_id", "unknown")).strip()
    role = extract_query_role(query_plan)
    search_filters = build_search_filters(tenant_id=tenant_id, role=role)
    vector_store_id = resolve_vector_store_id()
    semantic_search_results = search_vector_store(
        query=retrieval_query,
        vector_store_id=vector_store_id,
        filters=search_filters,
    )
    semantic_chunk_candidates = build_semantic_chunk_candidates(semantic_search_results)

    return {
        "query_id": query_id,
        "input_query_plan": query_plan,
        "retrieval_query": retrieval_query,
        "retrieval_mode": RETRIEVAL_MODE,
        "access_filter": build_access_filter_summary(
            role=role,
            search_filters=search_filters,
            candidate_count=len(semantic_chunk_candidates),
        ),
        "candidates": semantic_chunk_candidates,
        "status": "ready_for_rerank",
    }


def load_query_ids(query_id: str | None) -> list[str]:
    if query_id:
        return [query_id]
    raise RuntimeError("Step 04 requires --query-id and does not infer query ids from query_eval.json.")



def load_existing_payloads(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows = read_jsonl(path)
    return [row for row in rows if isinstance(row, dict) and str(row.get("query_id", "")).strip()]


def merge_payloads(existing: list[dict[str, object]], updates: list[dict[str, object]]) -> list[dict[str, object]]:
    merged_by_id = {str(row.get("query_id", "")): row for row in existing if str(row.get("query_id", "")).strip()}
    for row in updates:
        merged_by_id[str(row.get("query_id", ""))] = row
    return [merged_by_id[query_id] for query_id in sorted(merged_by_id)]

def summarize_chunk_text(text: object) -> str:
    value = str(text or "").strip()
    return value if value else "(missing chunk text)"


def build_summary_markdown(payloads: list[dict[str, object]]) -> str:
    lines = [
        "# Step 04 Summaries",
        "",
        "## Run configuration",
        "",
        f"- retrieval mode: `{RETRIEVAL_MODE}`",
        "- retrieval query source: `rewritten_query` (fallback: `original_query`)",
        "- query rewriting: `enabled in Step 03 plan`",
        "- managed reranking: `disabled`",
        "",
    ]
    for payload in payloads:
        query_id = str(payload.get("query_id", "unknown"))
        query_plan = payload.get("input_query_plan", {})
        if not isinstance(query_plan, dict):
            query_plan = {}
        candidates = payload.get("candidates", [])
        if not isinstance(candidates, list):
            candidates = []
        access_filter = payload.get("access_filter", {})
        if not isinstance(access_filter, dict):
            access_filter = {}

        lines.extend(
            [
                f"## Query `{query_id}`",
                "",
                f"- source query: `{query_plan.get('original_query', '(missing)')}`",
                f"- retrieval query: `{payload.get('retrieval_query', '(missing)')}`",
                f"- retrieval mode: `{payload.get('retrieval_mode', '(missing)')}`",
                f"- query role: `{access_filter.get('role', '(missing)')}`",
                f"- server-side filters applied: `{access_filter.get('server_side', False)}`",
                f"- server-side filters: `{compact_json(access_filter.get('filters', {}))}`",
                f"- returned candidates: `{access_filter.get('returned_candidate_count', 0)}`",
            ]
        )

        if candidates:
            lines.append("- top semantic candidates (ranked):")
            for candidate in candidates[:5]:
                if not isinstance(candidate, dict):
                    continue
                lines.append(
                    "  "
                    + f"- `#{candidate.get('semantic_rank', '?')}` "
                    + f"doc `{candidate.get('doc_id', '?')}` "
                    + f"(semantic_score `{float(candidate.get('semantic_score', 0.0)):.4f}`, "
                    + f"dense_candidate_id `{candidate.get('dense_candidate_id', '(missing)')}`)"
                )
                lines.append("    - chunk text:")
                for chunk_line in summarize_chunk_text(candidate.get('text')).splitlines():
                    lines.append(f"      {chunk_line}")
        else:
            lines.append("- top semantic candidates: `(none)`")

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
        return build_semantic_retrieval_payload(single_query_id, find_query_plan(single_query_id))

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        retrieval_payloads = list(executor.map(process, query_ids))

    STEP4_DIR.mkdir(parents=True, exist_ok=True)
    output_path = STEP4_DIR / OUTPUT_FILENAME
    summary_path = STEP4_DIR / SUMMARY_FILENAME
    if args.query_id:
        existing_payloads = load_existing_payloads(output_path)
        retrieval_payloads = merge_payloads(existing_payloads, retrieval_payloads)

    write_jsonl(output_path, retrieval_payloads)
    summary_path.write_text(build_summary_markdown(retrieval_payloads), encoding="utf-8")

    print(f"Wrote Step 04 artifact -> {output_path}")
    print(f"Wrote Step 04 summary -> {summary_path}")


def extract_query_role(query_plan: dict[str, object]) -> str:
    role = str(query_plan.get("role", "")).strip().lower()
    return role if role else "unknown"


def extract_retrieval_query(query_plan: dict[str, object]) -> str:
    rewritten_query = str(query_plan.get("rewritten_query", "")).strip()
    if rewritten_query:
        return rewritten_query
    original_query = str(query_plan.get("original_query", "")).strip()
    if not original_query:
        raise RuntimeError("Step 04 requires rewritten_query or original_query in the Step 03 query plan.")
    return original_query


def build_search_filters(tenant_id: str, role: str) -> dict[str, object]:
    base_filters: list[dict[str, object]] = [
        {
            "type": "eq",
            "key": "tenant_id",
            "value": tenant_id,
        }
    ]
    sensitivity_filter = build_sensitivity_filter(role=role)
    if sensitivity_filter is not None:
        base_filters.append(sensitivity_filter)
    return {
        "type": "and",
        "filters": base_filters,
    }


def build_sensitivity_filter(role: str) -> dict[str, object] | None:
    if role.strip().lower() == "partner":
        return None
    return {
        "type": "nin",
        "key": "sensitivity",
        "value": ["confidential"],
    }


def build_access_filter_summary(role: str, search_filters: dict[str, object], candidate_count: int) -> dict[str, object]:
    return {
        "role": role,
        "applied": True,
        "server_side": True,
        "filters": search_filters,
        "returned_candidate_count": candidate_count,
    }


def build_semantic_chunk_candidates(search_results: list[dict[str, Any]]) -> list[dict[str, object]]:
    semantic_chunk_candidates: list[dict[str, object]] = []
    for semantic_rank, search_result in enumerate(search_results[:DENSE_TOP_K], start=1):
        metadata_value = search_result.get("metadata", {})
        metadata = dict(metadata_value) if isinstance(metadata_value, dict) else {}
        doc_id = str(search_result.get("doc_id", "")).strip()
        text = str(search_result.get("text", "")).strip()
        if not doc_id:
            raise RuntimeError(f"Step 04 semantic candidate at rank={semantic_rank} is missing required doc_id.")
        if not text:
            raise RuntimeError(f"Step 04 semantic candidate at rank={semantic_rank} for doc_id={doc_id} has empty text.")

        chunk_id = str(search_result.get("chunk_id", "")).strip()
        dense_result_id = str(search_result.get("dense_result_id", "")).strip()
        dense_candidate_id = build_dense_candidate_id(
            doc_id=doc_id,
            text=text,
            metadata=metadata,
            chunk_id=chunk_id,
            dense_result_id=dense_result_id,
        )
        if not dense_candidate_id:
            raise RuntimeError(
                f"Step 04 semantic candidate at rank={semantic_rank} for doc_id={doc_id} is missing dense_candidate_id."
            )

        semantic_chunk_candidates.append(
            {
                "dense_candidate_id": dense_candidate_id,
                "chunk_id": chunk_id,
                "dense_result_id": dense_result_id,
                "doc_id": doc_id,
                "text": text,
                "metadata": metadata,
                "semantic_rank": semantic_rank,
                "semantic_score": float(search_result.get("score", 0.0)),
            }
        )

    return semantic_chunk_candidates


def build_dense_candidate_id(
    doc_id: str,
    text: str,
    metadata: dict[str, Any],
    chunk_id: str,
    dense_result_id: str,
) -> str:
    normalized_doc_id = doc_id.strip()
    normalized_text = text.strip()
    if not normalized_doc_id or not normalized_text:
        return ""

    normalized_payload = {
        "doc_id": normalized_doc_id,
        "text": normalized_text,
        "metadata_subset": build_stable_metadata_subset(metadata),
        "trace": {
            "chunk_id": chunk_id.strip(),
            "dense_result_id": dense_result_id.strip(),
        },
    }
    payload_json = json.dumps(normalized_payload, sort_keys=True, separators=(",", ":"))
    return f"densecand_{hashlib.sha256(payload_json.encode('utf-8')).hexdigest()}"


def build_stable_metadata_subset(metadata: dict[str, Any]) -> dict[str, Any]:
    stable_keys = (
        "doc_id",
        "tenant_id",
        "sensitivity",
        "doc_type",
        "date",
        "primary_company",
        "participants",
    )
    subset: dict[str, Any] = {}
    for key in stable_keys:
        value = metadata.get(key)
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            subset[key] = value
            continue
        if isinstance(value, list):
            subset[key] = [str(item) for item in value]
            continue
        subset[key] = str(value)
    return subset


def resolve_vector_store_id() -> str:
    if not VECTOR_STORE_MANIFEST_PATH.exists():
        raise RuntimeError(
            "Step 04 requires the Step 02 vector store manifest. Run Step 02 first to index the corpus."
        )
    manifest = json.loads(VECTOR_STORE_MANIFEST_PATH.read_text(encoding="utf-8"))
    vector_store_id = str(manifest.get("vector_store_id", "")).strip()
    if not vector_store_id:
        raise RuntimeError(f"Missing vector_store_id in manifest: {VECTOR_STORE_MANIFEST_PATH}")
    return vector_store_id


def search_vector_store(query: str, vector_store_id: str, filters: dict[str, object]) -> list[dict[str, Any]]:
    client = get_openai_client()
    response = client.vector_stores.search(
        vector_store_id=vector_store_id,
        query=query,
        filters=cast(Any, filters),
        max_num_results=DENSE_TOP_K,
        ranking_options={"ranker": "none"},
        rewrite_query=False,
    )
    response_data = getattr(response, "data", [])
    return [normalize_search_result(item) for item in response_data]


def normalize_search_result(item: Any) -> dict[str, Any]:
    metadata = dict(extract_item_field(item, "attributes", {}))
    doc_id = str(metadata.get("doc_id", "")).strip()
    if not doc_id:
        raise RuntimeError(
            "Step 04 vector-store result is missing required metadata.doc_id; cannot map dense chunk to parent document."
        )
    content = extract_item_field(item, "content", [])
    chunk_text = extract_text_from_content(content)
    return {
        "chunk_id": str(metadata.get("chunk_id", "")).strip(),
        "dense_result_id": str(extract_item_field(item, "id", "")).strip(),
        "doc_id": doc_id,
        "text": chunk_text,
        "metadata": metadata,
        "score": float(extract_item_field(item, "score", 0.0)),
    }


def extract_item_field(item: Any, field_name: str, default: Any) -> Any:
    if isinstance(item, dict):
        return item.get(field_name, default)
    return getattr(item, field_name, default)


def extract_text_from_content(content: Any) -> str:
    if isinstance(content, list):
        parts: list[str] = []
        for piece in content:
            text = ""
            if isinstance(piece, dict):
                text = str(piece.get("text", "")).strip()
            else:
                text = str(getattr(piece, "text", "")).strip()
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "").strip()


def compact_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    main()
