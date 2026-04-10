import argparse
import json
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.io_utils import read_jsonl, write_jsonl
from shared.api_payload import create_chat_completion
from shared.openai_client import deterministic_seed, get_openai_client
from shared.paths import QUERY_EVAL_PATH, STEP6_DIR, STEP8_DIR, STEP7_DIR

logger = logging.getLogger(__name__)

ANSWER_SYSTEM_PROMPT = """You are the final answer stage in a RAG pipeline.

You will receive:
- the original user query
- one or more extracted evidence records, each with a document_id and optional file_name
- each evidence record contains an exact_quote and may also include resolver_context from the same source document
- evidence_coverage rows describing which requested fields are supported by the returned evidence

Rules:
- Answer only from provided source text.
- Treat each requested fact in the query as a separate support check.
- A fact is supported only when the source text explicitly states it.
- exact_quote is the primary evidence.
- resolver_context is raw source text from the same document and may be used only to resolve references inside the exact_quote, such as pronouns, addressees, section headers, speaker labels, or table headers.
- Do not use resolver_context to invent missing facts or to rely on metadata that is not present in the source text.
- You may resolve pronouns or references when the exact_quote and resolver_context together explicitly state the fact.
- Do not infer a person's title, role, status, or attributes from their actions, responsibilities, or conversational context.
- For people, role/title means an explicitly stated position (e.g., Partner, CFO, CEO, analyst).
- If a requested fact is not explicitly stated, say it is not stated in the document.
- Do not contradict evidence_coverage when a matching supporting quote is present in documents.
- Never claim that a fact is not stated if the returned evidence explicitly states it.
- Keep the answer concise and directly responsive.
- Include citations to source documents in the citations array.
- Cite using the provided document_id when available; file_name is allowed only when document_id is unavailable.
- Never cite chunk_id. chunk_id is provided only as non-citable trace metadata.
- If evidence is partial, answer supported facts and explicitly mark unsupported facts as missing.
- Return only JSON that matches the schema.
""".strip()

ANSWER_RESPONSE_FORMAT: "ResponseFormatJSONSchema" = {
    "type": "json_schema",
    "json_schema": {
        "name": "final_answer",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "answer": {"type": "string"},
                "citations": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "supported_facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "field": {"type": "string"},
                            "value": {"type": "string"},
                            "supported": {"type": "boolean"},
                            "missing_reason": {"type": "string"},
                            "citations": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["field", "value", "supported", "missing_reason", "citations"],
                    },
                },
            },
            "required": ["answer", "citations", "supported_facts"],
        },
    },
}


class EvidenceDocument(TypedDict):
    document_id: str
    file_name: str
    chunk_id: str
    exact_quote: str
    resolver_context: str
    display_snippet: str
    doc_date: str
    timeline_milestone: str
    fact_labels: list[str]
    milestone_details: dict[str, Any]
    quote_rationale: str


class CandidateLookup(TypedDict):
    by_pair: dict[tuple[str, str], dict[str, Any]]
    by_doc_unique: dict[str, dict[str, Any]]


def load_queries(query_id: str | None) -> list[dict[str, Any]]:
    rows = json.loads(QUERY_EVAL_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("query_eval.json must contain a JSON array of query rows.")
    if query_id:
        filtered = [row for row in rows if isinstance(row, dict) and row.get("id") == query_id]
        if not filtered:
            raise RuntimeError(f"Unknown query_id={query_id} in query_eval.json")
        return filtered
    return [row for row in rows if isinstance(row, dict) and str(row.get("id", "")).strip()]


def quote_rows_by_query_id() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(STEP7_DIR / "quote-extraction.jsonl")
    return {str(row.get("query_id", "")): row for row in rows if isinstance(row, dict) and str(row.get("query_id", ""))}


def rerank_rows_by_query_id() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(STEP6_DIR / "rerank.jsonl")
    return {str(row.get("query_id", "")): row for row in rows if isinstance(row, dict) and str(row.get("query_id", ""))}


def normalize_placeholder_documents(
    query: dict[str, Any],
    quote_payload: dict[str, Any],
    rerank_payload: dict[str, Any] | None,
) -> list[EvidenceDocument]:
    quotes = quote_payload.get("quotes", [])
    documents: list[EvidenceDocument] = []
    candidate_lookup = build_candidate_lookup(rerank_payload)

    for idx, quote_row in enumerate(quotes, start=1):
        if not isinstance(quote_row, dict):
            continue

        document_id = str(quote_row.get("doc_id") or f"candidate-{idx}")
        chunk_id = str(quote_row.get("chunk_id") or "")
        exact_quote = str(quote_row.get("quote") or "").strip()
        if not exact_quote:
            continue

        candidate = find_candidate_for_document(candidate_lookup, document_id, chunk_id)
        resolver_context = build_resolver_context(quote_row, candidate)
        display_snippet = build_display_snippet(quote_row, resolver_context)
        documents.append(
            {
                "document_id": document_id,
                "file_name": "",
                "chunk_id": chunk_id,
                "exact_quote": exact_quote,
                "resolver_context": resolver_context,
                "display_snippet": display_snippet,
                "doc_date": str(quote_row.get("doc_date") or str(((candidate or {}).get("metadata", {}) or {}).get("date", ""))),
                "timeline_milestone": str(quote_row.get("timeline_milestone") or ""),
                "fact_labels": normalize_fact_labels(quote_row.get("fact_labels")),
                "milestone_details": normalize_milestone_details(quote_row.get("milestone_details")),
                "quote_rationale": str(quote_row.get("rationale") or ""),
            }
        )

    documents = sort_documents_canonically(documents, query_requires_timeline_summary(str(query.get("question", ""))))
    logger.info("step08 input_document_order=%s", [(d.get("document_id", ""), d.get("chunk_id", "")) for d in documents])
    return documents




def stable_document_sort_key(doc: EvidenceDocument) -> tuple[str, str, str]:
    return (
        str(doc.get("doc_date", "") or "9999-99-99"),
        str(doc.get("document_id", "")),
        str(doc.get("chunk_id", "")),
    )


def sort_documents_canonically(documents: list[EvidenceDocument], timeline: bool) -> list[EvidenceDocument]:
    if timeline:
        return sorted(documents, key=stable_document_sort_key)
    return sorted(documents, key=stable_document_sort_key)


def sort_citations_by_document_order(citations: list[str], documents: list[EvidenceDocument]) -> list[str]:
    order = {str(doc.get("document_id", "")): i for i, doc in enumerate(documents)}
    return sorted({c for c in citations if c}, key=lambda c: (order.get(c, 10**6), c))


def canonicalize_supported_facts_order(supported_facts: list[dict[str, Any]], expected_fields: list[str]) -> list[dict[str, Any]]:
    expected_rank = {normalize_field_key(field): idx for idx, field in enumerate(expected_fields)}
    return sorted(
        supported_facts,
        key=lambda fact: (
            expected_rank.get(normalize_field_key(fact.get("field")), 10**6),
            str(fact.get("field", "")).lower(),
        ),
    )

def normalize_fact_labels(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def normalize_milestone_details(raw: Any) -> dict[str, Any]:
    template = {
        "milestone_type": "",
        "intro_date_text": "",
        "valuation_text": "",
        "raise_amount_text": "",
        "board_term": "",
        "liquidation_preference": "",
        "pro_rata_rights": "",
        "investor_side": "",
        "company_side": "",
        "term_summary_parts": [],
    }
    if not isinstance(raw, dict):
        return template

    normalized = dict(template)
    for key in template:
        if key == "term_summary_parts":
            continue
        value = raw.get(key)
        normalized[key] = str(value).strip() if isinstance(value, str) else ""
    parts = raw.get("term_summary_parts")
    if isinstance(parts, list):
        normalized["term_summary_parts"] = [str(part).strip() for part in parts if str(part).strip()]
    return normalized


def sort_documents_for_timeline(documents: list[EvidenceDocument]) -> list[EvidenceDocument]:
    def sort_key(doc: EvidenceDocument) -> tuple[str, str, str]:
        return (
            str(doc.get("doc_date", "") or "9999-99-99"),
            str(doc.get("document_id", "")),
            str(doc.get("chunk_id", "")),
        )

    return sorted(documents, key=sort_key)


def query_requires_timeline_summary(question: str) -> bool:
    lowered = question.lower()
    return any(token in lowered for token in ("timeline", "chronological", "intro", "initial", "latest", "from intro"))


def is_internal_coverage_field(field: Any) -> bool:
    normalized = str(field).strip().lower()
    if not normalized:
        return False
    return normalized.endswith("_repair")


def filter_answer_evidence_coverage(evidence_coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in evidence_coverage:
        if not isinstance(row, dict):
            continue
        if is_internal_coverage_field(row.get("field")):
            continue
        filtered.append(row)
    return filtered


def ordered_supported_fact_fields(query: dict[str, Any], quote_payload: dict[str, Any]) -> list[str]:
    evidence_coverage = quote_payload.get("evidence_coverage", [])
    if isinstance(evidence_coverage, list) and evidence_coverage:
        fields = [
            str(row.get("field", "")).strip()
            for row in evidence_coverage
            if isinstance(row, dict)
            and str(row.get("field", "")).strip()
            and not is_internal_coverage_field(row.get("field"))
        ]
        if fields:
            return fields

    expected_facts = query.get("expected_facts", [])
    if isinstance(expected_facts, list) and expected_facts:
        return [str(item).strip() for item in expected_facts if str(item).strip()]
    return []


def compose_timeline_milestone_summary(doc: EvidenceDocument) -> str:
    milestone = str(doc.get("timeline_milestone", "")).strip()
    details = normalize_milestone_details(doc.get("milestone_details"))

    if milestone == "intro_contact":
        if details["intro_date_text"]:
            return f"Introduced on {details['intro_date_text']}."
        return ""
    if milestone == "initial_terms":
        parts = [part for part in (details["raise_amount_text"], details["valuation_text"]) if part]
        if parts:
            return "Initial terms: " + " at ".join(parts[:2]) + "."
        return ""
    if milestone in {"counter_terms", "latest_terms"}:
        summary_parts = [
            details["valuation_text"],
            details["board_term"],
            details["liquidation_preference"],
            details["pro_rata_rights"],
        ]
        selected = [part for part in summary_parts if part]
        if selected:
            return f"{milestone.replace('_', ' ').title()}: " + "; ".join(selected) + "."
    return ""


def build_structured_timeline_hints(documents: list[EvidenceDocument], requires_timeline_summary: bool) -> list[str]:
    if not requires_timeline_summary:
        return []
    hints: list[str] = []
    for doc in documents:
        milestone = str(doc.get("timeline_milestone", "")).strip()
        if milestone not in {"intro_contact", "initial_terms", "counter_terms", "latest_terms"}:
            continue
        summary = compose_timeline_milestone_summary(doc)
        if not summary:
            continue
        hints.append(f"- {milestone}: {summary} [citation={doc.get('document_id', '')}]")
    return hints


def build_answer_user_prompt(
    original_query: str,
    documents: list[EvidenceDocument],
    expected_facts: list[str],
    evidence_coverage: list[dict[str, Any]],
    requires_timeline_summary: bool,
) -> str:
    doc_lines = []
    structured_timeline_hints = build_structured_timeline_hints(documents, requires_timeline_summary)
    for doc in documents:
        fact_labels = doc.get("fact_labels", [])
        fact_label_text = ", ".join(fact_labels) if isinstance(fact_labels, list) and fact_labels else "(none)"
        doc_lines.extend(
            [
                "---",
                f"document_id: {doc['document_id']}",
                f"citation_id: {doc['document_id'] or doc['file_name'] or '(none)'}",
                f"file_name: {doc['file_name'] or '(none)'}",
                f"chunk_id: {doc['chunk_id'] or '(none)'}",
                f"doc_date: {doc.get('doc_date', '') or '(none)'}",
                f"timeline_milestone: {doc.get('timeline_milestone', '') or '(none)'}",
                f"fact_labels: {fact_label_text}",
                f"milestone_details: {json.dumps(normalize_milestone_details(doc.get('milestone_details')), ensure_ascii=False)}",
                f"quote_rationale: {doc.get('quote_rationale', '') or '(none)'}",
                f"exact_quote: {doc['exact_quote']}",
                f"resolver_context: {doc['resolver_context'] or '(none)'}",
                f"display_snippet: {doc['display_snippet'] or '(none)'}",
            ]
        )

    expected_facts_lines = [f"- {field}" for field in expected_facts] if expected_facts else ["- (none provided)"]
    evidence_lines: list[str] = []
    if evidence_coverage:
        for row in evidence_coverage:
            if not isinstance(row, dict):
                continue
            evidence_lines.append(
                f"- field={str(row.get('field', ''))}; supported={str(row.get('supported', False)).lower()}; reason={str(row.get('reason', ''))}"
            )
    else:
        evidence_lines.append("- (none provided)")

    timeline_instruction = (
        "For timeline-summary queries, preserve chronology using doc_date, timeline_milestone, and milestone_details. "
        "Use structured milestone_details as the primary source for milestone-supported terms when present; do not collapse counter/latest milestones to valuation-only if supported term fields exist. "
        "Do not relabel evidence as initial/counter/latest unless explicit in quote text or provided in timeline_milestone. "
        "If chronology is ambiguous, keep answer descriptive and avoid invented temporal labels."
        if requires_timeline_summary
        else ""
    )

    return "\n".join(
        [
            "Generate the final grounded answer.",
            "",
            "Also return `supported_facts` with one entry per requested fact in the query.",
            "For each entry:",
            "- `field`: short snake_case fact name",
            "- `value`: exact supported value; empty string when unsupported",
            "- `supported`: true/false",
            "- `missing_reason`: required when unsupported; empty string when supported",
            "- `citations`: supporting document_id values from provided documents; do not return chunk_id",
            "",
            "Use expected_fact_fields (when provided) as naming/order guidance for supported_facts.",
            "Use evidence_coverage to determine which facts are expected supported vs unsupported.",
            "When evidence_coverage says supported=true and a matching quote is present in documents, return that fact as supported=true.",
            "Do not say a fact is missing when the supporting quote explicitly states it.",
            "If documents is empty, explicitly answer that no accessible documents at the requester's permission level provide the requested information.",
            timeline_instruction,
            "",
            f"original_query: {original_query}",
            "",
            "expected_fact_fields:",
            *expected_facts_lines,
            "",
            "evidence_coverage:",
            *evidence_lines,
            "",
            "structured_timeline_hints:",
            *(structured_timeline_hints or ["- (none provided)"]),
            "",
            "documents:",
            *doc_lines,
        ]
    )



def validate_citations(citations: list[str], valid_citations: set[str], context: str) -> None:
    invalid = [citation for citation in citations if citation not in valid_citations]
    if invalid:
        raise RuntimeError(
            "Model returned citation(s) not present in source documents"
            + f" for {context}: "
            + ", ".join(sorted(set(invalid)))
        )


def build_citation_alias_map(documents: list[EvidenceDocument]) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for doc in documents:
        document_id = str(doc.get("document_id", "")).strip()
        file_name = str(doc.get("file_name", "")).strip()
        chunk_id = str(doc.get("chunk_id", "")).strip()

        canonical = document_id or file_name
        if not canonical:
            continue

        for alias in (document_id, file_name, chunk_id):
            if alias:
                alias_map[alias] = canonical
    return alias_map


def canonicalize_citations(citations: Any, alias_map: dict[str, str]) -> list[str]:
    if not isinstance(citations, list):
        return []

    canonicalized: list[str] = []
    for item in citations:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if not value:
            continue
        canonical = alias_map.get(value, value)
        if canonical not in canonicalized:
            canonicalized.append(canonical)
    return canonicalized


def canonicalize_payload_citations(payload: dict[str, Any], documents: list[EvidenceDocument]) -> None:
    alias_map = build_citation_alias_map(documents)
    normalized = canonicalize_citations(payload.get("citations"), alias_map)
    payload["citations"] = sort_citations_by_document_order(normalized, documents)

    supported_facts = payload.get("supported_facts")
    if not isinstance(supported_facts, list):
        return

    for fact in supported_facts:
        if not isinstance(fact, dict):
            continue
        fact_norm = canonicalize_citations(fact.get("citations"), alias_map)
        fact["citations"] = sort_citations_by_document_order(fact_norm, documents)


def ensure_answer_shape(payload: dict[str, Any], documents: list[EvidenceDocument]) -> None:
    if not isinstance(payload.get("answer"), str):
        raise RuntimeError("Missing or invalid 'answer' in structured output.")
    citations = payload.get("citations")
    if not isinstance(citations, list) or not all(isinstance(item, str) for item in citations):
        raise RuntimeError("Missing or invalid 'citations' in structured output.")
    valid_citations = {doc["document_id"] for doc in documents} | {doc["file_name"] for doc in documents if doc.get("file_name")}
    if valid_citations and not citations:
        raise RuntimeError("Structured output must include at least one citation when evidence documents exist.")
    if not valid_citations and citations:
        raise RuntimeError("Structured output must not include citations when no evidence documents were provided.")
    validate_citations(citations, valid_citations, "answer")

    supported_facts = payload.get("supported_facts")
    if not isinstance(supported_facts, list) or not supported_facts:
        raise RuntimeError("Missing or invalid 'supported_facts' in structured output.")

    for idx, fact in enumerate(supported_facts, start=1):
        if not isinstance(fact, dict):
            raise RuntimeError(f"supported_facts[{idx}] must be an object.")

        field = fact.get("field")
        value = fact.get("value")
        supported = fact.get("supported")
        missing_reason = fact.get("missing_reason")
        fact_citations = fact.get("citations")

        if not isinstance(field, str) or not field.strip():
            raise RuntimeError(f"supported_facts[{idx}] has invalid 'field'.")
        if not isinstance(value, str):
            raise RuntimeError(f"supported_facts[{idx}] has invalid 'value'.")
        if not isinstance(supported, bool):
            raise RuntimeError(f"supported_facts[{idx}] has invalid 'supported'.")
        if not isinstance(missing_reason, str):
            raise RuntimeError(f"supported_facts[{idx}] has invalid 'missing_reason'.")
        if not isinstance(fact_citations, list) or not all(isinstance(item, str) for item in fact_citations):
            raise RuntimeError(f"supported_facts[{idx}] has invalid 'citations'.")
        if fact_citations:
            validate_citations(fact_citations, valid_citations, f"supported_facts[{idx}]")

        if supported and missing_reason.strip():
            raise RuntimeError(f"supported_facts[{idx}] cannot include missing_reason when supported=true.")
        if supported and not value.strip():
            raise RuntimeError(f"supported_facts[{idx}] must include non-empty value when supported=true.")
        if supported and not fact_citations:
            raise RuntimeError(f"supported_facts[{idx}] must include at least one citation when supported=true.")
        if not supported and not missing_reason.strip():
            raise RuntimeError(f"supported_facts[{idx}] must include missing_reason when supported=false.")
        if not supported and value.strip():
            raise RuntimeError(f"supported_facts[{idx}] must use empty value when supported=false.")


def repair_supported_fact_citations(payload: dict[str, Any]) -> None:
    """Repair common model formatting mistakes without weakening answer guarantees."""
    citations = payload.get("citations")
    supported_facts = payload.get("supported_facts")
    if not isinstance(citations, list) or not isinstance(supported_facts, list):
        return

    normalized_citations = [item.strip() for item in citations if isinstance(item, str) and item.strip()]
    for fact in supported_facts:
        if not isinstance(fact, dict):
            continue
        fact_citations = fact.get("citations")
        if not isinstance(fact_citations, list):
            continue

        supported = fact.get("supported")
        if supported is True and not fact_citations and len(normalized_citations) == 1:
            fact["citations"] = list(normalized_citations)


def normalize_field_key(field: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(field).strip().lower())


def build_evidence_coverage_lookup(evidence_coverage: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    coverage_lookup: dict[str, dict[str, Any]] = {}
    for row in evidence_coverage:
        if not isinstance(row, dict):
            continue
        field_key = normalize_field_key(row.get("field"))
        if not field_key:
            continue
        coverage_lookup[field_key] = row
    return coverage_lookup


def build_supported_fact_lookup(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    supported_fact_lookup: dict[str, dict[str, Any]] = {}
    supported_facts = payload.get("supported_facts", [])
    if not isinstance(supported_facts, list):
        return supported_fact_lookup

    for fact in supported_facts:
        if not isinstance(fact, dict):
            continue
        field_key = normalize_field_key(fact.get("field"))
        if not field_key:
            continue
        supported_fact_lookup[field_key] = fact

    return supported_fact_lookup


def coverage_marks_entity_grounding_failed(evidence_coverage: list[dict[str, Any]]) -> bool:
    for row in evidence_coverage:
        if not isinstance(row, dict):
            continue
        field = str(row.get("field", "")).strip().lower()
        reason = str(row.get("reason", "")).strip().lower()
        if bool(row.get("supported")):
            continue
        if field in {"anchor_entity_presence", "entity_grounding"}:
            return True
        if "entity grounding failed" in reason or "required" in reason and "accessible evidence" in reason:
            return True
    return False


def enforce_unsupported_coverage(payload: dict[str, Any], evidence_coverage: list[dict[str, Any]]) -> None:
    supported_fact_lookup = build_supported_fact_lookup(payload)
    for row in evidence_coverage:
        if not isinstance(row, dict):
            continue
        if bool(row.get("supported")):
            continue
        field_key = normalize_field_key(row.get("field"))
        if not field_key:
            continue
        fact = supported_fact_lookup.get(field_key)
        if not isinstance(fact, dict):
            continue
        fact["supported"] = False
        fact["value"] = ""
        fact["missing_reason"] = str(row.get("reason", "")).strip() or build_missing_reason_from_coverage(row)
        fact["citations"] = []


def ensure_payload_matches_evidence_coverage(payload: dict[str, Any], evidence_coverage: list[dict[str, Any]]) -> None:
    coverage_lookup = build_evidence_coverage_lookup(evidence_coverage)
    supported_fact_lookup = build_supported_fact_lookup(payload)
    mismatched_fields: list[str] = []

    for field_key, coverage_row in coverage_lookup.items():
        coverage_supported = bool(coverage_row.get("supported"))
        if not coverage_supported:
            continue

        supported_fact = supported_fact_lookup.get(field_key)
        if not isinstance(supported_fact, dict):
            mismatched_fields.append(str(coverage_row.get("field", field_key)))
            continue
        if supported_fact.get("supported") is not True:
            mismatched_fields.append(str(coverage_row.get("field", field_key)))

    if mismatched_fields:
        raise RuntimeError(
            "Structured output contradicted supported evidence_coverage for field(s): "
            + ", ".join(sorted(set(mismatched_fields)))
        )


def request_answer_payload(
    model: str,
    question: str,
    documents: list[EvidenceDocument],
    expected_facts: list[str],
    evidence_coverage: list[dict[str, Any]],
    requires_timeline_summary: bool,
) -> dict[str, Any]:
    client = get_openai_client()
    response = create_chat_completion(
        client,
        payload={
            "model": model,
            "temperature": 0,
            "seed": deterministic_seed(),
            "messages": [
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_answer_user_prompt(
                        question,
                        documents,
                        expected_facts,
                        evidence_coverage,
                        requires_timeline_summary,
                    ),
                },
            ],
            "response_format": ANSWER_RESPONSE_FORMAT,
        },
    )
    content_text = response.choices[0].message.content
    if not content_text:
        raise RuntimeError("Model returned no structured content.")
    if isinstance(content_text, list):
        content_text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content_text)

    try:
        payload = json.loads(content_text)
    except Exception as exc:
        logger.error("step08 validation_stage=parse_json error=%s", exc)
        raise

    try:
        canonicalize_payload_citations(payload, documents)
    except RuntimeError as exc:
        logger.error("step08 validation_stage=canonicalize_citations error=%s", exc)
        raise

    repair_supported_fact_citations(payload)
    enforce_unsupported_coverage(payload, evidence_coverage)

    try:
        ensure_answer_shape(payload, documents)
    except RuntimeError as exc:
        logger.error("step08 validation_stage=answer_shape error=%s", exc)
        raise

    try:
        ensure_payload_matches_evidence_coverage(payload, evidence_coverage)
    except RuntimeError as exc:
        logger.error("step08 validation_stage=evidence_coverage_consistency error=%s", exc)
        raise
    return payload

def answer_query_with_llm(
    model: str,
    question: str,
    documents: list[EvidenceDocument],
    expected_facts: list[str],
    evidence_coverage: list[dict[str, Any]],
    requires_timeline_summary: bool,
) -> dict[str, Any]:
    """Generate a structured answer deterministically from curated evidence documents."""
    return request_answer_payload(
        model=model,
        question=question,
        documents=documents,
        expected_facts=expected_facts,
        evidence_coverage=evidence_coverage,
        requires_timeline_summary=requires_timeline_summary,
    )



def build_no_evidence_supported_facts(
    expected_facts: list[str],
    evidence_coverage: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if expected_facts:
        fact_fields = expected_facts
    else:
        fact_fields = [
            str(row.get("field", "")).strip()
            for row in evidence_coverage
            if isinstance(row, dict) and str(row.get("field", "")).strip()
        ]

    supported_facts: list[dict[str, Any]] = []
    for field in fact_fields:
        coverage_row = find_evidence_coverage_row(evidence_coverage, field)
        missing_reason = build_missing_reason_from_coverage(coverage_row)
        supported_facts.append(
            {
                "field": field,
                "value": "",
                "supported": False,
                "missing_reason": missing_reason,
                "citations": [],
            }
        )

    if supported_facts:
        return supported_facts

    return [
        {
            "field": "requested_information",
            "value": "",
            "supported": False,
            "missing_reason": "No accessible documents at the requester's permission level provide the requested information.",
            "citations": [],
        }
    ]


def find_evidence_coverage_row(evidence_coverage: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    normalized_field_key = normalize_field_key(field)
    for row in evidence_coverage:
        if not isinstance(row, dict):
            continue
        if normalize_field_key(row.get("field")) == normalized_field_key:
            return row
    return None


def build_missing_reason_from_coverage(coverage_row: dict[str, Any] | None) -> str:
    if isinstance(coverage_row, dict):
        reason = str(coverage_row.get("reason", "")).strip()
        if reason:
            return reason
    return "No accessible documents at the requester's permission level provide the requested information."


def permission_level_phrase(role: Any) -> str:
    normalized_role = str(role).strip().lower()
    placeholder_roles = {"none", "null", "unknown", "n/a", "na", "unspecified"}
    if normalized_role and normalized_role not in placeholder_roles:
        return f"the {normalized_role} permission level"
    return "the requester's permission level"


def build_no_evidence_answer(question: str, role: Any) -> str:
    return f"No accessible documents at {permission_level_phrase(role)} provide the requested information."


def build_entity_no_evidence_answer(question: str, role: Any, evidence_coverage: list[dict[str, Any]]) -> str:
    entity_name = extract_project_entity_name(question)
    if entity_name:
        return (
            f"No accessible documents at {permission_level_phrase(role)} mention {entity_name} "
            "or its related diligence details."
        )
    return build_no_evidence_answer(question, role)


def extract_project_entity_name(question: str) -> str:
    match = re.search(r"\b(Project\s+[A-Z][A-Za-z0-9\-]*)\b", str(question))
    if not match:
        return ""
    return match.group(1)


def grounded_document_count(answer_result: dict[str, Any]) -> int:
    citations = answer_result.get("citations", [])
    if not isinstance(citations, list):
        return 0
    unique = {str(item).strip() for item in citations if str(item).strip()}
    return len(unique)


def answer_query_dry_run(question: str, documents: list[EvidenceDocument]) -> dict[str, Any]:
    if not documents:
        return {
            "answer": f"Placeholder final answer for: {question}",
            "citations": [],
            "supported_facts": [
                {
                    "field": "query_answer",
                    "value": "",
                    "supported": False,
                    "missing_reason": "No evidence documents were provided.",
                    "citations": [],
                }
            ],
        }

    citation = documents[0]["document_id"]
    return {
        "answer": f"Placeholder final answer for: {question}",
        "citations": [citation],
        "supported_facts": [
            {
                "field": "query_answer",
                "value": f"Placeholder final answer for: {question}",
                "supported": True,
                "missing_reason": "",
                "citations": [citation],
            }
        ],
    }


def run_for_query(
    query: dict[str, Any],
    quote_payload: dict[str, Any],
    rerank_payload: dict[str, Any] | None,
    model: str,
    dry_run: bool,
) -> dict[str, Any]:
    query_id = str(query["id"])
    question = str(query["question"])
    query_role = query.get("role", "")
    documents = normalize_placeholder_documents(query, quote_payload, rerank_payload)
    expected_facts = ordered_supported_fact_fields(query, quote_payload)
    evidence_coverage = quote_payload.get("evidence_coverage", [])
    if not isinstance(evidence_coverage, list):
        evidence_coverage = []
    evidence_coverage = filter_answer_evidence_coverage(evidence_coverage)
    requires_timeline_summary = query_requires_timeline_summary(question)

    if dry_run:
        answer_result = answer_query_dry_run(question, documents)
        answer_source = "heuristic_dry_run"
    elif not documents or coverage_marks_entity_grounding_failed(evidence_coverage):
        answer_result = {
            "answer": build_entity_no_evidence_answer(question, query_role, evidence_coverage),
            "citations": [],
            "supported_facts": build_no_evidence_supported_facts(expected_facts, evidence_coverage),
        }
        answer_source = "deterministic_no_evidence"
    else:
        logger.info("step08 query_id=%s single_answer_attempt=true", query_id)
        answer_result = answer_query_with_llm(
            model=model,
            question=question,
            documents=documents,
            expected_facts=expected_facts,
            evidence_coverage=evidence_coverage,
            requires_timeline_summary=requires_timeline_summary,
        )
        answer_source = "openai_structured_output"

    supporting_quotes = [
        str(quote_row.get("quote", "")).strip()
        for quote_row in quote_payload.get("quotes", [])
        if isinstance(quote_row, dict) and str(quote_row.get("quote", "")).strip()
    ][:5]

    answer_result["citations"] = sort_citations_by_document_order(list(answer_result.get("citations", [])), documents)
    supported_facts = answer_result.get("supported_facts", [])
    if isinstance(supported_facts, list):
        for fact in supported_facts:
            if isinstance(fact, dict):
                fact["citations"] = sort_citations_by_document_order(list(fact.get("citations", [])), documents)
        answer_result["supported_facts"] = canonicalize_supported_facts_order(supported_facts, expected_facts)
    logger.info("step08 final_citation_order=%s", answer_result.get("citations", []))
    logger.info("step08 supported_facts_order=%s", [str(f.get("field", "")) for f in answer_result.get("supported_facts", []) if isinstance(f, dict)])

    return {
        "query_id": query_id,
        "question": question,
        "answer": answer_result["answer"],
        "citations": answer_result["citations"],
        "supported_facts": answer_result["supported_facts"],
        "supporting_quotes": supporting_quotes,
        "document_count": grounded_document_count(answer_result),
        "input_quote_count": len(quote_payload.get("quotes", [])),
        "status": "ready_for_eval",
        "answer_model": model,
        "answer_source": answer_source,
    }


def build_halted_query_row(
    query: dict[str, Any],
    exc: Exception,
    model: str,
    document_count: int = 0,
    input_quote_count: int = 0,
) -> dict[str, Any]:
    query_id = str(query.get("id", ""))
    question = str(query.get("question", ""))
    error_type = type(exc).__name__
    error_message = str(exc).strip() or "(no error detail)"
    logger.error("step08 query_id=%s halted error_type=%s error=%s", query_id, error_type, error_message)
    return {
        "query_id": query_id,
        "question": question,
        "answer": "",
        "citations": [],
        "supported_facts": [],
        "supporting_quotes": [],
        "document_count": max(0, int(document_count)),
        "input_quote_count": max(0, int(input_quote_count)),
        "status": "halted_error",
        "error_type": error_type,
        "error_message": error_message,
        "answer_model": model,
        "answer_source": "halted_before_eval",
    }


def build_summary(rows: list[dict[str, Any]]) -> str:
    lines = ["# Step 08 Summaries", ""]

    answer_sources = sorted({str(row.get("answer_source", "(missing)")) for row in rows if isinstance(row, dict)})
    answer_models = sorted({str(row.get("answer_model", "(missing)")) for row in rows if isinstance(row, dict)})
    lines.extend(
        [
            "## Run configuration",
            "",
            f"- answer source: `{', '.join(answer_sources) or '(missing)'}`",
            f"- answer model: `{', '.join(answer_models) or '(missing)'}`",
            "",
        ]
    )

    for row in rows:
        supporting_quotes = row.get("supporting_quotes", [])
        if not isinstance(supporting_quotes, list):
            supporting_quotes = []

        lines.extend(
            [
                f"## Query `{row['query_id']}`",
                "",
                f"- question: `{row['question']}`",
                "- generated answer:",
                "```md",
                str(row.get('answer', '')),
                "```",
                f"- citations returned: `{', '.join(row.get('citations', [])) or '(none)'}`",
                f"- supported facts returned: `{len(row.get('supported_facts', []))}`",
            ]
        )
        status = str(row.get("status", "")).strip()
        if status != "ready_for_eval":
            rendered_status = status or "(missing)"
            lines.append(f"- query halted: `true`")
            lines.append(f"- status: `{rendered_status}`")
            lines.append(f"- halt error type: `{row.get('error_type', '(unknown)')}`")
            lines.append(f"- halt error detail: `{row.get('error_message', '(none)')}`")

        if supporting_quotes:
            lines.append("- supporting quotes from quote extraction:")
            for quote in supporting_quotes:
                quote_text = " ".join(str(quote).split())
                lines.append(f"  - {quote_text}")
        else:
            lines.append("- supporting quotes from quote extraction: `(none)`")

        lines.append("")
    return "\n".join(lines)


def merge_answer_rows(new_rows: list[dict[str, Any]], replace_existing: bool) -> list[dict[str, Any]]:
    if replace_existing:
        return new_rows

    answer_path = STEP8_DIR / "answer.jsonl"
    existing_rows = read_jsonl(answer_path)
    merged_by_id = {
        str(row.get("query_id", "")): row
        for row in existing_rows
        if isinstance(row, dict) and str(row.get("query_id", "")).strip()
    }
    for row in new_rows:
        merged_by_id[str(row["query_id"])] = row

    query_order = [str(row["id"]) for row in load_queries(None)]
    rank = {query_id: idx for idx, query_id in enumerate(query_order)}
    return sorted(merged_by_id.values(), key=lambda row: rank.get(str(row.get("query_id", "")), len(rank)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--all-queries", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--dry-run", action="store_true", help="Skip OpenAI calls and generate deterministic placeholder answers.")
    args = parser.parse_args()

    model = resolve_answer_model(args.model)

    query_filter = None if args.all_queries or args.query_id is None else args.query_id
    queries = load_queries(query_filter)
    quote_by_id = quote_rows_by_query_id()
    rerank_by_id = rerank_rows_by_query_id()

    def process(query: dict[str, Any]) -> dict[str, Any]:
        query_id = str(query["id"])
        quote_payload = quote_by_id.get(query_id)
        if quote_payload is None:
            raise RuntimeError(f"Missing Step 07 artifact for query_id={query_id}")

        input_quote_count = len(quote_payload.get("quotes", [])) if isinstance(quote_payload.get("quotes", []), list) else 0
        document_count = 0
        rerank_payload = rerank_by_id.get(query_id)
        try:
            documents = normalize_placeholder_documents(query, quote_payload, rerank_payload)
            document_count = len(documents)
            return run_for_query(query, quote_payload, rerank_payload, model, args.dry_run)
        except Exception as exc:
            return build_halted_query_row(
                query,
                exc,
                model,
                document_count=document_count,
                input_quote_count=input_quote_count,
            )

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        answer_rows = list(executor.map(process, queries))

    output_rows = merge_answer_rows(answer_rows, replace_existing=query_filter is None)

    STEP8_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(STEP8_DIR / "answer.jsonl", output_rows)
    (STEP8_DIR / "08-answer-summary.md").write_text(build_summary(output_rows), encoding="utf-8")

    print(f"Wrote Step 08 answer outputs for {len(answer_rows)} query(s) -> {STEP8_DIR}")


def resolve_answer_model(cli_model: str | None) -> str:
    if cli_model:
        return cli_model

    answer_model = os.getenv("OPENAI_ANSWER_MODEL")
    if answer_model:
        return answer_model

    global_model = os.getenv("OPENAI_MODEL")
    if global_model:
        logger.error(
            "OPENAI_ANSWER_MODEL is unset; falling back to OPENAI_MODEL for Step 08 answers: %s",
            global_model,
        )
        return global_model

    default_model = "gpt-4.1"
    logger.error(
        "OPENAI_ANSWER_MODEL and OPENAI_MODEL are unset; defaulting Step 08 answer model to %s",
        default_model,
    )
    return default_model


def normalize_lookup_id(value: Any) -> str:
    return str(value or "").strip()


def build_candidate_lookup(rerank_payload: dict[str, Any] | None) -> CandidateLookup:
    if not isinstance(rerank_payload, dict):
        return {"by_pair": {}, "by_doc_unique": {}}

    ranked_candidates = rerank_payload.get("ranked_candidates", [])
    if not isinstance(ranked_candidates, list):
        return {"by_pair": {}, "by_doc_unique": {}}

    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    by_doc_candidates: dict[str, list[dict[str, Any]]] = {}
    for candidate in ranked_candidates:
        if not isinstance(candidate, dict):
            continue
        doc_id = normalize_lookup_id(candidate.get("doc_id"))
        chunk_id = normalize_lookup_id(candidate.get("chunk_id"))
        by_pair[(doc_id, chunk_id)] = candidate
        by_doc_candidates.setdefault(doc_id, []).append(candidate)

    by_doc_unique = {
        doc_id: doc_candidates[0]
        for doc_id, doc_candidates in by_doc_candidates.items()
        if doc_id and len(doc_candidates) == 1
    }
    return {"by_pair": by_pair, "by_doc_unique": by_doc_unique}


def find_candidate_for_document(
    candidate_lookup: CandidateLookup,
    document_id: str,
    chunk_id: str,
) -> dict[str, Any] | None:
    doc_id = normalize_lookup_id(document_id)
    chunk = normalize_lookup_id(chunk_id)

    by_pair = candidate_lookup.get("by_pair", {})
    exact = by_pair.get((doc_id, chunk))
    if isinstance(exact, dict):
        return exact

    if chunk:
        doc_level = by_pair.get((doc_id, ""))
        if isinstance(doc_level, dict):
            return doc_level

    by_doc_unique = candidate_lookup.get("by_doc_unique", {})
    unique = by_doc_unique.get(doc_id)
    if isinstance(unique, dict):
        return unique
    return None


def build_resolver_context(quote_row: dict[str, Any], candidate: dict[str, Any] | None) -> str:
    existing_context = str(quote_row.get("resolver_context") or "").strip()
    if existing_context:
        return existing_context
    if not isinstance(candidate, dict):
        return ""

    email_header_context = extract_email_header_context(candidate)
    if email_header_context:
        return email_header_context

    return extract_adjacent_context_line(str(quote_row.get("quote", "")), candidate)


def build_display_snippet(quote_row: dict[str, Any], resolver_context: str) -> str:
    existing_snippet = str(quote_row.get("display_snippet") or "").strip()
    if existing_snippet:
        return existing_snippet

    exact_quote = str(quote_row.get("quote") or "").strip()
    if resolver_context:
        return f"{resolver_context}\n[...]\n{exact_quote}"
    return exact_quote


def extract_email_header_context(candidate: dict[str, Any]) -> str:
    header_lines: list[str] = []
    for line in get_candidate_source_lines(candidate):
        cleaned_line = " ".join(str(line).split())
        if cleaned_line.startswith("From:") or cleaned_line.startswith("To:"):
            header_lines.append(cleaned_line)
    return "\n".join(header_lines[:2]).strip()


def extract_adjacent_context_line(quote: str, candidate: dict[str, Any]) -> str:
    source_lines = get_candidate_source_lines(candidate)
    cleaned_quote = " ".join(str(quote).split())
    if not cleaned_quote:
        return ""

    normalized_lines = [" ".join(str(line).split()) for line in source_lines]
    for index, line in enumerate(normalized_lines):
        if cleaned_quote not in line:
            continue
        previous_line = normalized_lines[index - 1] if index > 0 else ""
        if previous_line:
            return previous_line
    return ""


def get_candidate_source_lines(candidate: dict[str, Any]) -> list[str]:
    text = str(candidate.get("text", ""))
    return [line for line in text.splitlines() if line.strip()]


if __name__ == "__main__":
    main()
