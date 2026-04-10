import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False

from shared.api_payload import create_chat_completion
from shared.openai_client import deterministic_seed, get_openai_client
from shared.paths import QUERY_EVAL_PATH, ROOT, STEP3_DIR
from shared.step3_outputs import QUERY_PLANS_FILENAME

SUMMARIES_FILENAME = "summaries.md"
_WHITESPACE_RE = re.compile(r"\s+")
_PROVENANCE_PATTERN = re.compile(
    r"\b(?:in|from|according to)\s+([a-z0-9][a-z0-9&.\- ]{0,80}?)\s*(?:'s)?\s+(?:records?|crm|database)\b",
    flags=re.IGNORECASE,
)
_GENERIC_SCOPE_TOKENS = {"our", "the", "records", "record", "crm", "database", "side"}
_PROVENANCE_ANCHOR_TOKEN_PATTERN = re.compile(r"\b(?:records?|crm|database)\b", flags=re.IGNORECASE)

QUERY_REWRITE_SYSTEM_PROMPT = """You rewrite a CRM-style search query for retrieval and produce a sparse keyword query.

Output must match the provided JSON schema.

Rules:
- Do NOT infer or mention tenant, role, access control, confidentiality, or metadata filters.
- rewritten_query: a compact search query (5-14 words), remove filler words, keep key nouns/proper nouns/numbers.
- sparse_query fields:
  - required_terms: 0-3 anchor tokens that MUST appear for keyword search (usually a company/person token).
  - include_terms: keywords + synonyms (lowercase). MUST include every term from required_terms.
  - phrases: important multi-word phrases (lowercase), e.g. "term sheet", "board observer".
  - exclude_terms: only if the user explicitly asks to exclude something (e.g. "not X", "excluding Y"); otherwise [].
- Token formatting:
  - Use lowercase for required_terms/include_terms/exclude_terms/phrases.
  - Keep numbers and symbols when meaningful (e.g. "82m", "0.70%", "$90m").
  - Avoid stopwords like: the, a, an, to, of, for, with, on, in, and, or.

Return only JSON that matches the schema.
""".strip()

QUERY_REWRITE_RESPONSE_FORMAT: "ResponseFormatJSONSchema" = {
    "type": "json_schema",
    "json_schema": {
        "name": "query_rewrite",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "rewritten_query": {"type": "string"},
                "sparse_query": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "required_terms": {"type": "array", "items": {"type": "string"}},
                        "include_terms": {"type": "array", "items": {"type": "string"}},
                        "phrases": {"type": "array", "items": {"type": "string"}},
                        "exclude_terms": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["required_terms", "include_terms", "phrases", "exclude_terms"],
                },
            },
            "required": ["rewritten_query", "sparse_query"],
        },
    },
}


def load_queries() -> list[dict[str, Any]]:
    if not QUERY_EVAL_PATH.exists():
        raise FileNotFoundError(f"Query eval file not found: {QUERY_EVAL_PATH}")

    rows = json.loads(QUERY_EVAL_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("query_eval.json must contain a JSON array of query rows.")
    return rows


def load_query(query_id: str) -> dict[str, Any]:
    rows = load_queries()
    for row in rows:
        if row.get("id") == query_id:
            return row
    raise ValueError(f"Query id not found in query_eval.json: {query_id}")


def build_query_rewrite_user_prompt(original_query: str) -> str:
    return f"""Rewrite this query and produce sparse_query.

QUERY:
{original_query}
"""


def rewrite_query_and_build_sparse_query(model: str, original_query: str) -> dict[str, Any]:
    """Rewrite one query into dense and sparse retrieval inputs via OpenAI structured output."""
    client = get_openai_client()
    response = create_chat_completion(
        client,
        payload={
            "model": model,
            "temperature": 0,
            "seed": deterministic_seed(),
            "messages": [
                {"role": "system", "content": QUERY_REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": build_query_rewrite_user_prompt(original_query)},
            ],
            "response_format": QUERY_REWRITE_RESPONSE_FORMAT,
        },
    )
    content_text = response.choices[0].message.content
    if not content_text:
        raise RuntimeError("Model returned no structured content.")
    if isinstance(content_text, list):
        content_text = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content_text
        )
    parsed = json.loads(content_text)
    ensure_schema_shape(parsed)
    return parsed


def ensure_schema_shape(parsed: dict[str, Any]) -> None:
    if "rewritten_query" not in parsed or not isinstance(parsed["rewritten_query"], str):
        raise RuntimeError("Missing or invalid 'rewritten_query' in structured output.")
    if "sparse_query" not in parsed or not isinstance(parsed["sparse_query"], dict):
        raise RuntimeError("Missing or invalid 'sparse_query' in structured output.")

    sparse_query = parsed["sparse_query"]
    for field in ["required_terms", "include_terms", "phrases", "exclude_terms"]:
        values = sparse_query.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise RuntimeError(f"Missing or invalid sparse_query.{field} in structured output.")


def normalize_sparse_term_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = _WHITESPACE_RE.sub(" ", value.strip().lower())
        if not term or term in seen:
            continue
        seen.add(term)
        normalized.append(term)
    return normalized


def extract_provenance_scope_terms(original_query: str) -> list[str]:
    lowered = original_query.lower()
    matches: list[str] = []
    for match in _PROVENANCE_PATTERN.finditer(lowered):
        captured = _WHITESPACE_RE.sub(" ", match.group(1)).strip(" -")
        if not captured:
            continue
        cleaned_tokens = [token for token in captured.split(" ") if token and token not in _GENERIC_SCOPE_TOKENS]
        if cleaned_tokens:
            matches.append(" ".join(cleaned_tokens))
            continue
        matches.extend(_PROVENANCE_ANCHOR_TOKEN_PATTERN.findall(match.group(0)))
    return normalize_sparse_term_list(matches)


def ensure_required_terms_are_in_include_terms(sparse_query: dict[str, Any]) -> dict[str, Any]:
    required_terms = normalize_sparse_term_list([str(value) for value in sparse_query.get("required_terms", []) if isinstance(value, str)])
    include_terms = normalize_sparse_term_list([str(value) for value in sparse_query.get("include_terms", []) if isinstance(value, str)])
    include_set = set(include_terms)
    for required_term in required_terms:
        if required_term not in include_set:
            include_terms.append(required_term)
            include_set.add(required_term)
    return {
        **sparse_query,
        "required_terms": required_terms,
        "include_terms": include_terms,
    }


def sanitize_sparse_query(original_query: str, sparse_query: dict[str, Any]) -> dict[str, Any]:
    provenance_scope_terms = extract_provenance_scope_terms(original_query)
    provenance_scope_tokens = {
        token
        for term in provenance_scope_terms
        for token in term.split(" ")
        if token
    }

    required_terms = normalize_sparse_term_list([str(value) for value in sparse_query.get("required_terms", []) if isinstance(value, str)])
    include_terms = normalize_sparse_term_list([str(value) for value in sparse_query.get("include_terms", []) if isinstance(value, str)])
    phrases = normalize_sparse_term_list([str(value) for value in sparse_query.get("phrases", []) if isinstance(value, str)])
    exclude_terms = normalize_sparse_term_list([str(value) for value in sparse_query.get("exclude_terms", []) if isinstance(value, str)])

    sanitized_required_terms = [
        term
        for term in required_terms
        if term not in provenance_scope_terms
        and not (len(term.split(" ")) == 1 and term in provenance_scope_tokens)
    ]

    sanitized = {
        "required_terms": sanitized_required_terms,
        "include_terms": include_terms,
        "phrases": phrases,
        "exclude_terms": exclude_terms,
    }
    return ensure_required_terms_are_in_include_terms(sanitized)


def resolve_rewritten_query(original_query: str, rewrite_result: dict[str, Any]) -> tuple[str, str | None]:
    rewritten_query = str(rewrite_result.get("rewritten_query", "")).strip()
    if rewritten_query:
        return rewritten_query, None
    return original_query.strip(), "original_query_fallback"


def build_query_plan(query: dict[str, Any], rewrite_result: dict[str, Any], model: str, source: str) -> dict[str, Any]:
    rewritten_query, rewrite_source = resolve_rewritten_query(query["question"], rewrite_result)
    provenance_scope_terms = extract_provenance_scope_terms(query["question"])
    sparse_query = sanitize_sparse_query(query["question"], rewrite_result["sparse_query"])
    return {
        "query_id": query["id"],
        "tenant_id": query.get("tenant_id", "unknown"),
        "role": query.get("role", "unknown"),
        "original_query": query["question"],
        "rewritten_query": rewritten_query,
        "sparse_query": sparse_query,
        "provenance_scope_terms": provenance_scope_terms,
        "sanitized_required_terms": sparse_query["required_terms"],
        "notes": "Step 03 rewrites the query and derives sparse retrieval terms only.",
        "status": "ready_for_retrieval",
        "rewrite_model": model,
        "rewrite_source": source if rewrite_source is None else f"{source}:{rewrite_source}",
    }


def build_summary_lines(query_plan: dict[str, Any]) -> list[str]:
    sparse_query = query_plan["sparse_query"]
    return [
        f"## Query `{query_plan['query_id']}`",
        "",
        f"- query_id: `{query_plan['query_id']}`",
        f"- source query: `{query_plan['original_query']}`",
        f"- rewritten query: `{query_plan['rewritten_query']}`",
        f"- provenance/scope terms: `{', '.join(query_plan.get('provenance_scope_terms', [])) or '(none)'}`",
        f"- required sparse terms: `{', '.join(sparse_query['required_terms']) or '(none)'}`",
        f"- sanitized required sparse terms: `{', '.join(query_plan.get('sanitized_required_terms', [])) or '(none)'}`",
        f"- include sparse terms: `{', '.join(sparse_query['include_terms']) or '(none)'}`",
        f"- phrases: `{', '.join(sparse_query['phrases']) or '(none)'}`",
        f"- exclusions: `{', '.join(sparse_query['exclude_terms']) or '(none)'}`",
        f"- rewrite source: `{query_plan['rewrite_source']}`",
    ]


def load_existing_query_plans(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Expected a JSON array in {path}.")

    return [row for row in payload if isinstance(row, dict) and isinstance(row.get("query_id"), str)]


def merge_query_plans(existing: list[dict[str, Any]], updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged_by_id = {row["query_id"]: row for row in existing}
    for row in updates:
        merged_by_id[row["query_id"]] = row
    return [merged_by_id[query_id] for query_id in sorted(merged_by_id)]


def build_summaries_markdown(query_plans: list[dict[str, Any]]) -> str:
    summaries: list[str] = ["# Step 03 Summaries", ""]
    for query_plan in query_plans:
        summaries.extend(build_summary_lines(query_plan))
        summaries.append("")
    return "\n".join(summaries).rstrip() + "\n"


def process_query_row(query: dict[str, Any], model: str) -> dict[str, Any]:
    rewrite_result = rewrite_query_and_build_sparse_query(model, query["question"])
    return build_query_plan(query, rewrite_result, model, "openai_structured_output")



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id")
    parser.add_argument(
        "--all-queries",
        action="store_true",
        help="Process all query ids from query_eval.json.",
    )
    parser.add_argument("--model")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of queries to rewrite concurrently when processing multiple queries.",
    )
    args = parser.parse_args()

    if args.query_id is not None and not args.query_id.strip():
        parser.error("--query-id cannot be empty; omit it to process all queries or provide a valid query id.")

    load_dotenv(ROOT / ".env")
    model = args.model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    query_rows = load_queries() if args.all_queries or args.query_id is None else [load_query(args.query_id)]

    query_plans: list[dict[str, Any]]
    if len(query_rows) <= 1:
        query_plans = [process_query_row(query_rows[0], model)] if query_rows else []
    else:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            query_plans = list(executor.map(lambda query: process_query_row(query, model), query_rows))

    STEP3_DIR.mkdir(parents=True, exist_ok=True)

    query_plans_path = STEP3_DIR / QUERY_PLANS_FILENAME
    if args.query_id is not None and not args.all_queries:
        existing_query_plans = load_existing_query_plans(query_plans_path)
        query_plans = merge_query_plans(existing_query_plans, query_plans)

    query_plans_path.write_text(json.dumps(query_plans, indent=2) + "\n", encoding="utf-8")

    summaries_path = STEP3_DIR / SUMMARIES_FILENAME
    summaries_path.write_text(build_summaries_markdown(query_plans), encoding="utf-8")

    print(f"Wrote Step 03 query plans -> {query_plans_path.relative_to(ROOT)}")
    print(f"Wrote Step 03 summaries -> {summaries_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
