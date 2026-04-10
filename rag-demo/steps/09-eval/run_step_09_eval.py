import argparse
import hashlib
import json
import logging
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

from shared.io_utils import read_jsonl, write_jsonl
from shared.api_payload import create_chat_completion
from shared.openai_client import deterministic_seed, get_openai_client
from shared.paths import (
    EXTRACTIONS_PATH,
    QUERY_EVAL_PATH,
    STEP3_DIR,
    STEP4_DIR,
    STEP5_DIR,
    STEP6_DIR,
    STEP7_DIR,
    STEP8_DIR,
    STEP9_DIR,
)

logger = logging.getLogger(__name__)

OUTPUT_FILENAME = "answer-eval.jsonl"
SUMMARY_FILENAME = "09-eval-summary.md"
FAILURE_TRACES_DIRNAME = "failure-traces"
SAFE_TRACE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

ANSWER_EVAL_SYSTEM_PROMPT = """You are the answer evaluation stage in a RAG pipeline.

Task:
Given a query, an expected answer, a generated answer, and extracted evidence quotes, produce structured evaluation findings.

You must:
1) Decompose the query into required answer requirements.
2) Decompose the answer into atomic factual claims.
3) Judge each requirement against the query's expected answer (as a semantic target) and evidence.
4) Judge each claim for explicit support in evidence.
5) Identify hard and soft issues, including material incompleteness, unsupported claims, over-answering, or style drift.

Strict evidence policy:
- Use only the provided exact_quote text and resolver_context text.
- exact_quote is the primary evidence span.
- resolver_context is raw source text from the same document and may be used only to resolve references inside the exact_quote, such as pronouns, addressees, speaker labels, section headers, or table headers.
- Do not treat resolver_context as a license to infer new facts that are not explicitly stated when exact_quote and resolver_context are read together.
- No outside knowledge.
- No guessing.
- If a requested fact is not explicitly stated in the provided evidence package, treat it as missing evidence (unsupported inference).
- Do not treat actions as titles.
- Do not infer role/title/status from responsibilities, behavior, or vague context unless it is explicitly stated in the provided evidence package.

Status labels:
- explicitly_supported
- unsupported_inference
- contradicted
- out_of_scope

Guidance:
- Evaluate semantic sufficiency, not template matching.
- Treat expected_answer as a meaning target, not exact wording requirements.
- expected_answer is not an exhaustive checklist of mandatory facts.
- Do not fail an answer just because it omits non-essential detail that appears in expected_answer but is not required to answer the user question.
- Accept paraphrases, reordered facts, concise responses, and supported extra detail when the question is still sufficiently answered.
- Answers can be acceptable even when wording differs from expected_answer, as long as meaning is preserved and constraints are respected.
- Assess only claims actually made in generated_answer. Do not invent claims from expected_answer and do not score omissions as hallucinated generated claims.
- When supporting_quotes is empty and both expected_answer and generated_answer correctly state that no accessible evidence/documents are available, do not require positive evidence citations for that absence claim.
- In the approved zero-evidence absence/no-access case, an absence answer may be acceptable with zero supporting quotes and should not be turned into a hard failure merely for lacking positive citations.
- A requirement is satisfied only when status=explicitly_supported.
- A claim is safe only when status=explicitly_supported.
- Use out_of_scope for answer content that spills beyond the user question or evidence scope.
- Compare generated_answer to expected_answer for semantic correctness, not exact wording.
- exact_quote plus resolver_context may jointly establish support when the resolver_context directly identifies who or what the exact_quote refers to.
- Use unsupported_inference when the claim could be plausible but is not explicitly stated by the provided evidence package.
- Use contradicted when the provided evidence package directly conflicts with the answer content.
- Never use status=explicitly_supported unless evidence_quote_ids contains at least one quoted support id.
- If no quote id supports the judgment, use unsupported_inference instead.
- Every substantive claim in the generated answer must map to evidence quotes.
- Use soft_issues for warnings and non-fatal quality concerns.
- Reserve hard_issues for severe failures such as unsupported substantive claims, contradictions, missing required evidence, or forbidden/access-violating content.

Output only JSON matching the schema.
""".strip()

ANSWER_EVAL_RESPONSE_FORMAT: "ResponseFormatJSONSchema" = {
    "type": "json_schema",
    "json_schema": {
        "name": "answer_eval_findings",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query_requirements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "requirement_id": {"type": "string"},
                            "text": {"type": "string"},
                            "critical": {"type": "boolean"},
                        },
                        "required": ["requirement_id", "text", "critical"],
                    },
                },
                "answer_claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "claim_id": {"type": "string"},
                            "text": {"type": "string"},
                            "substantive": {"type": "boolean"},
                        },
                        "required": ["claim_id", "text", "substantive"],
                    },
                },
                "requirement_results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "requirement_id": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": [
                                    "explicitly_supported",
                                    "unsupported_inference",
                                    "contradicted",
                                    "out_of_scope",
                                ],
                            },
                            "evidence_quote_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["requirement_id", "status", "evidence_quote_ids", "reason"],
                    },
                },
                "claim_results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "claim_id": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": [
                                    "explicitly_supported",
                                    "unsupported_inference",
                                    "contradicted",
                                    "out_of_scope",
                                ],
                            },
                            "evidence_quote_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["claim_id", "status", "evidence_quote_ids", "reason"],
                    },
                },
                "hard_issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "issue_type": {"type": "string"},
                            "detail": {"type": "string"},
                            "related_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["issue_type", "detail", "related_ids"],
                    },
                },
                "soft_issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "issue_type": {"type": "string"},
                            "detail": {"type": "string"},
                            "related_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["issue_type", "detail", "related_ids"],
                    },
                },
            },
            "required": [
                "query_requirements",
                "answer_claims",
                "requirement_results",
                "claim_results",
                "hard_issues",
                "soft_issues",
            ],
        },
    },
}

EXAMPLE_EVAL_INPUT: dict[str, Any] = {
    "query_id": "MVP-EXAMPLE",
    "original_query": "Who is the primary point of contact, and is their role stated?",
    "generated_answer": "The primary point of contact is Priya Singh. Her role is not stated.",
    "supporting_quotes": [
        {
            "quote_id": "q1",
            "doc_id": "AUR-EMAIL-001",
            "text": "Primary point of contact on Aurora side: Priya Singh.",
            "resolver_context": "Subject: Aurora partner sync",
            "display_snippet": "Subject: Aurora partner sync\n[...]\nPrimary point of contact on Aurora side: Priya Singh.",
        },
        {
            "quote_id": "q2",
            "doc_id": "AUR-EMAIL-001",
            "text": "No formal title listed for Priya in this thread.",
            "resolver_context": "",
            "display_snippet": "No formal title listed for Priya in this thread.",
        },
    ],
    "expected_facts": [
        "Primary point of contact identity",
        "Whether role/title is explicitly stated",
    ],
    "forbidden_claims": ["Any inferred role/title for Priya Singh"],
}
VALID_STATUSES = {"explicitly_supported", "unsupported_inference", "contradicted", "out_of_scope"}
VALID_CITATION_POLICIES = {"subset", "exact"}
PLACEHOLDER_TOKENS = {"", "none", "n/a", "na", "null", "nil", "-", "(none)", "(n/a)"}
NO_FILES_AVAILABLE_HINTS = (
    "no accessible documents",
    "no documents",
    "no files are available",
    "do not contain any information",
    "does not contain any information",
)


def is_no_files_available_text(value: str) -> bool:
    text = value.strip().lower()
    return bool(text) and any(hint in text for hint in NO_FILES_AVAILABLE_HINTS)


def load_queries(query_id: str | None) -> list[dict[str, Any]]:
    rows = json.loads(QUERY_EVAL_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("query_eval.json must contain a JSON array.")
    if query_id:
        matching = [row for row in rows if isinstance(row, dict) and row.get("id") == query_id]
        if not matching:
            raise RuntimeError(f"Unknown query_id={query_id} in query_eval.json")
        return matching
    return [row for row in rows if isinstance(row, dict) and str(row.get("id", "")).strip()]


def answer_rows_by_query_id() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(STEP8_DIR / "answer.jsonl")
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        query_id = str(row.get("query_id", "")).strip()
        if query_id:
            output[query_id] = row
    return output


def quote_rows_by_query_id() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(STEP7_DIR / "quote-extraction.jsonl")
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        query_id = str(row.get("query_id", "")).strip()
        if query_id:
            output[query_id] = row
    return output


def normalize_supporting_quotes(quote_payload: dict[str, Any]) -> list[dict[str, str]]:
    quotes = quote_payload.get("quotes", [])
    normalized: list[dict[str, str]] = []
    if not isinstance(quotes, list):
        return normalized

    for index, item in enumerate(quotes, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("quote", "")).strip()
        if not text:
            continue
        normalized.append(
            {
                "quote_id": str(item.get("quote_id") or f"q{index}"),
                "doc_id": str(item.get("doc_id", "")).strip(),
                "text": text,
                "resolver_context": str(item.get("resolver_context", "")).strip(),
                "display_snippet": str(item.get("display_snippet", "")).strip(),
                "doc_date": str(item.get("doc_date", "")).strip(),
                "timeline_milestone": str(item.get("timeline_milestone", "")).strip(),
            }
        )
    return normalized
def optional_expected_facts(query: dict[str, Any]) -> list[str]:
    values = query.get("expected_facts", [])
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for item in values:
        if isinstance(item, str) and item.strip():
            output.append(item.strip())
    return output


def merge_forbidden_claim_aliases(query: dict[str, Any]) -> list[str]:
    output: list[str] = []
    for field_name in ("forbidden_claims", "forbidden_facts"):
        values = query.get(field_name, [])
        if not isinstance(values, list):
            continue
        for item in values:
            value = str(item).strip()
            if value and value not in output:
                output.append(value)
    return output


def optional_expected_citations(query: dict[str, Any]) -> list[str]:
    values = query.get("expected_citations", [])
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for item in values:
        value = str(item).strip()
        if value and value not in output:
            output.append(value)
    return output


def optional_citation_policy(query: dict[str, Any], default_policy: str) -> str:
    configured = str(query.get("citation_policy", "")).strip().lower()
    if configured in VALID_CITATION_POLICIES:
        return configured
    return default_policy if default_policy in VALID_CITATION_POLICIES else "subset"


def normalize_doc_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for item in values:
        value = str(item).strip()
        if value and value not in output:
            output.append(value)
    return output


def normalize_related_reference_id(value: str) -> str:
    normalized = str(value).strip()
    if re.fullmatch(r"[cCrR]\d+", normalized):
        return normalized.lower()
    return normalized


def normalize_related_reference_ids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for item in values:
        normalized = normalize_related_reference_id(str(item))
        if normalized and normalized not in output:
            output.append(normalized)
    return output


def is_placeholder_text(value: Any) -> bool:
    text = str(value).strip().lower()
    return text in PLACEHOLDER_TOKENS


def normalize_evidence_quote_ids(raw_ids: Any, valid_quote_ids: set[str]) -> list[str]:
    if not isinstance(raw_ids, list):
        return []

    output: list[str] = []
    for raw_id in raw_ids:
        quote_id = str(raw_id).strip()
        if not quote_id or is_placeholder_text(quote_id):
            continue
        if quote_id not in valid_quote_ids:
            continue
        if quote_id not in output:
            output.append(quote_id)
    return output


def normalize_issue_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    cleaned: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        issue_type = str(item.get("issue_type", "")).strip()
        detail = str(item.get("detail", "")).strip()
        if not issue_type or is_placeholder_text(issue_type):
            continue
        if not detail or is_placeholder_text(detail):
            continue
        related_ids = item.get("related_ids", [])
        normalized_related = normalize_related_reference_ids(related_ids) if isinstance(related_ids, list) else []
        cleaned.append({"issue_type": issue_type, "detail": detail, "related_ids": normalized_related})
    return cleaned


def metadata_by_doc_id() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(EXTRACTIONS_PATH)
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        doc_id = str(row.get("doc_id", "")).strip()
        if doc_id:
            output[doc_id] = row
    return output


def rerank_rows_by_query_id() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(STEP6_DIR / "rerank.jsonl")
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        query_id = str(row.get("query_id", "")).strip()
        if query_id:
            output[query_id] = row
    return output


def query_plan_rows_by_query_id() -> dict[str, dict[str, Any]]:
    path = STEP3_DIR / "query-plans.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return {}

    output: dict[str, dict[str, Any]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        query_id = str(row.get("query_id", "")).strip()
        if query_id:
            output[query_id] = row
    return output


def semantic_rows_by_query_id() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(STEP4_DIR / "semantic-retrieval.jsonl")
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        query_id = str(row.get("query_id", "")).strip()
        if query_id:
            output[query_id] = row
    return output


def sparse_rows_by_query_id() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(STEP5_DIR / "sparse-keyword-retrieval.jsonl")
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        query_id = str(row.get("query_id", "")).strip()
        if query_id:
            output[query_id] = row
    return output


def role_can_access_sensitivity(role: str, sensitivity: str) -> bool:
    normalized_role = role.strip().lower()
    normalized_sensitivity = sensitivity.strip().lower()
    if normalized_sensitivity == "confidential":
        return normalized_role == "partner"
    return True


def diagnose_citation_mismatch(
    query: dict[str, Any],
    returned_citations: list[str],
    expected_citations: list[str],
    doc_metadata: dict[str, dict[str, Any]],
    rerank_payload: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str], bool, bool]:
    expected_set = set(expected_citations)
    returned_set = set(returned_citations)
    missing = sorted(expected_set - returned_set)
    extra = sorted(returned_set - expected_set)

    query_id = str(query.get("id", "")).strip()
    query_tenant = str(query.get("tenant_id", "")).strip()
    query_role = str(query.get("role", "")).strip()

    rerank_doc_ids: set[str] = set()
    if isinstance(rerank_payload, dict):
        candidates = rerank_payload.get("ranked_candidates")
        if not isinstance(candidates, list):
            # Backward compatibility for older payloads.
            candidates = rerank_payload.get("selected_candidates", [])
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                doc_id = str(candidate.get("doc_id", "")).strip()
                if doc_id:
                    rerank_doc_ids.add(doc_id)

    hard_issues: list[dict[str, Any]] = []
    root_causes: list[str] = []

    if missing:
        missing_in_rerank = [doc_id for doc_id in missing if doc_id not in rerank_doc_ids]
        if missing_in_rerank:
            hard_issues.append(
                {
                    "issue_type": "missing_expected_citation_not_retrieved",
                    "detail": (
                        f"Expected citations missing from answer and not present in rerank candidates for "
                        f"query_id={query_id}: {', '.join(missing_in_rerank)}"
                    ),
                    "related_ids": missing_in_rerank,
                }
            )
            root_causes.append("missed_document_retrieval")

        missing_seen_but_not_used = [doc_id for doc_id in missing if doc_id in rerank_doc_ids]
        if missing_seen_but_not_used:
            hard_issues.append(
                {
                    "issue_type": "missing_expected_citation_not_used",
                    "detail": (
                        f"Expected citations were retrieved but absent from final answer citations for "
                        f"query_id={query_id}: {', '.join(missing_seen_but_not_used)}"
                    ),
                    "related_ids": missing_seen_but_not_used,
                }
            )
            root_causes.append("answer_generation_missed_retrieved_document")

    spillover_docs: list[str] = []
    access_violation_docs: list[str] = []
    for doc_id in extra:
        metadata = doc_metadata.get(doc_id, {})
        doc_tenant = str(metadata.get("tenant_id", "")).strip()
        doc_sensitivity = str(metadata.get("sensitivity", "")).strip()

        if doc_tenant and query_tenant and doc_tenant != query_tenant:
            spillover_docs.append(doc_id)

        if doc_sensitivity and not role_can_access_sensitivity(query_role, doc_sensitivity):
            access_violation_docs.append(doc_id)

    if spillover_docs:
        hard_issues.append(
            {
                "issue_type": "tenant_data_spillover",
                "detail": (
                    f"Returned citations include documents from a different tenant than query tenant {query_tenant}: "
                    f"{', '.join(spillover_docs)}"
                ),
                "related_ids": spillover_docs,
            }
        )
        root_causes.append("tenant_data_spillover")

    if access_violation_docs:
        hard_issues.append(
            {
                "issue_type": "access_permission_violation",
                "detail": (
                    f"Returned citations include documents the query role {query_role} should not access: "
                    f"{', '.join(access_violation_docs)}"
                ),
                "related_ids": access_violation_docs,
            }
        )
        root_causes.append("access_permissions_not_respected")

    tenant_respected = len(spillover_docs) == 0
    access_respected = len(access_violation_docs) == 0

    if not root_causes:
        root_causes.append("citation_set_mismatch")

    return hard_issues, root_causes, tenant_respected, access_respected


def assess_citation_policy(
    citation_policy: str,
    query: dict[str, Any],
    returned_citations: list[str],
    expected_citations: list[str],
    supporting_quotes: list[dict[str, str]],
    doc_metadata: dict[str, dict[str, Any]],
    rerank_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    expected_set = set(expected_citations)
    returned_set = set(returned_citations)
    missing = sorted(expected_set - returned_set)
    extra = sorted(returned_set - expected_set)

    hard_issues, root_causes, tenant_respected, access_respected = diagnose_citation_mismatch(
        query=query,
        returned_citations=returned_citations,
        expected_citations=expected_citations,
        doc_metadata=doc_metadata,
        rerank_payload=rerank_payload,
    )

    quote_doc_ids = {str(row.get("doc_id", "")).strip() for row in supporting_quotes if str(row.get("doc_id", "")).strip()}
    unsupported_returned = sorted([doc_id for doc_id in returned_citations if doc_id not in quote_doc_ids])
    if unsupported_returned:
        hard_issues.append(
            {
                "issue_type": "returned_citation_not_in_supporting_quotes",
                "detail": (
                    "Returned citations must be backed by Step 07 supporting quotes. "
                    f"Missing quote evidence for: {', '.join(unsupported_returned)}"
                ),
                "related_ids": unsupported_returned,
            }
        )

    soft_issues: list[dict[str, Any]] = []
    if citation_policy == "exact" and extra:
        hard_issues.append(
            {
                "issue_type": "exact_policy_extra_citations",
                "detail": "Exact citation policy requires returned citations to exactly match expected_citations.",
                "related_ids": extra,
            }
        )

    if not missing and not extra and root_causes == ["citation_set_mismatch"]:
        root_causes = []

    return {
        "citation_policy": citation_policy,
        "citations_match": returned_set == expected_set,
        "missing_expected_citations": missing,
        "unexpected_returned_citations": extra,
        "tenant_isolation_respected": tenant_respected,
        "access_permissions_respected": access_respected,
        "citation_mismatch_root_causes": root_causes,
        "hard_issues": normalize_issue_rows(hard_issues),
        "soft_issues": normalize_issue_rows(soft_issues),
    }


def build_eval_user_prompt(
    query_id: str,
    original_query: str,
    expected_answer: str,
    generated_answer: str,
    supporting_quotes: list[dict[str, str]],
    expected_facts: list[str],
    forbidden_claims: list[str],
) -> str:
    supporting_quotes_payload = build_supporting_quotes_payload(supporting_quotes)

    lines = [
        "Evaluate this answer using semantic sufficiency with strict evidence grounding.",
        "",
        "Return all findings as structured JSON.",
        "",
        "Evidence package notes:",
        "- quote_text is the exact evidence span.",
        "- resolver_context is raw source text from the same document and may be used only to resolve references inside quote_text.",
        "- display_snippet is for readability only and must not be treated as stronger evidence than quote_text plus resolver_context.",
        "",
        f"query_id: {query_id}",
        f"original_query: {original_query}",
        f"expected_answer: {expected_answer}",
        f"generated_answer: {generated_answer}",
        "",
        "optional_expected_facts:",
    ]
    if expected_facts:
        for item in expected_facts:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")

    lines.extend(["", "optional_forbidden_claims:"])
    if forbidden_claims:
        for item in forbidden_claims:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")

    lines.extend(["", "supporting_quotes_json:", "```json", to_json_block(supporting_quotes_payload), "```"])
    return "\n".join(lines)


def build_supporting_quotes_payload(supporting_quotes: list[dict[str, str]]) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for quote in supporting_quotes:
        normalized_quote = build_single_supporting_quote_payload(quote)
        if not normalized_quote["quote_id"]:
            continue
        if not normalized_quote["doc_id"]:
            continue
        if not normalized_quote["quote_text"]:
            continue
        payload.append(normalized_quote)
    return payload


def build_single_supporting_quote_payload(quote: dict[str, str]) -> dict[str, str]:
    return {
        "quote_id": str(quote.get("quote_id", "")).strip(),
        "doc_id": str(quote.get("doc_id", "")).strip(),
        "quote_text": str(quote.get("text", "")).strip(),
        "resolver_context": str(quote.get("resolver_context", "")).strip(),
        "display_snippet": str(quote.get("display_snippet", "")).strip(),
        "doc_date": str(quote.get("doc_date", "")).strip(),
        "timeline_milestone": str(quote.get("timeline_milestone", "")).strip(),
    }
def parse_structured_response_content(content: Any) -> dict[str, Any]:
    if content is None:
        raise RuntimeError("Model returned no structured content.")
    if isinstance(content, list):
        content_text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    else:
        content_text = str(content)
    payload = json.loads(content_text)
    if not isinstance(payload, dict):
        raise RuntimeError("Structured response must be a JSON object.")
    return payload



def normalize_supported_rows(payload: dict[str, Any], valid_quote_ids: set[str]) -> dict[str, Any]:
    for field_name, id_key in (("requirement_results", "requirement_id"), ("claim_results", "claim_id")):
        rows = payload.get(field_name)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            row["evidence_quote_ids"] = normalize_evidence_quote_ids(row.get("evidence_quote_ids"), valid_quote_ids)
            if row.get("status") != "explicitly_supported":
                continue
            normalized_ids = row.get("evidence_quote_ids", [])
            has_evidence = len(normalized_ids) > 0
            if has_evidence:
                continue

            row["status"] = "unsupported_inference"
            row["evidence_quote_ids"] = []

            subject_id = str(row.get(id_key, "")).strip() or "unknown"
            existing_reason = str(row.get("reason", "")).strip()
            fallback_reason = (
                f"Normalized from explicitly_supported because {field_name}.{subject_id} had no supporting evidence_quote_ids."
            )
            row["reason"] = f"{existing_reason} {fallback_reason}".strip() if existing_reason else fallback_reason
    payload["hard_issues"] = normalize_issue_rows(payload.get("hard_issues", []))
    payload["soft_issues"] = normalize_issue_rows(payload.get("soft_issues", []))
    return payload

def validate_eval_shape(payload: dict[str, Any], valid_quote_ids: set[str]) -> None:
    required_arrays = [
        "query_requirements",
        "answer_claims",
        "requirement_results",
        "claim_results",
        "hard_issues",
        "soft_issues",
    ]
    for field in required_arrays:
        value = payload.get(field)
        if not isinstance(value, list):
            raise RuntimeError(f"Missing or invalid '{field}' in structured output.")

    requirement_results = payload["requirement_results"]
    claim_results = payload["claim_results"]

    if not requirement_results:
        raise RuntimeError("Structured output requirement_results must not be empty.")
    if not claim_results:
        raise RuntimeError("Structured output claim_results must not be empty.")

    for row in requirement_results:
        if not isinstance(row, dict):
            raise RuntimeError("requirement_results entries must be objects.")
        row["evidence_quote_ids"] = normalize_evidence_quote_ids(row.get("evidence_quote_ids"), valid_quote_ids)
        status = row.get("status")
        if status not in VALID_STATUSES:
            raise RuntimeError(f"Invalid requirement_results status: {status}")
        if status == "explicitly_supported":
            evidence_ids = row.get("evidence_quote_ids", [])
            if not evidence_ids:
                raise RuntimeError(
                    "requirement_results entries with explicitly_supported status must include at least one evidence_quote_id."
                )

    for row in claim_results:
        if not isinstance(row, dict):
            raise RuntimeError("claim_results entries must be objects.")
        row["evidence_quote_ids"] = normalize_evidence_quote_ids(row.get("evidence_quote_ids"), valid_quote_ids)
        status = row.get("status")
        if status not in VALID_STATUSES:
            raise RuntimeError(f"Invalid claim_results status: {status}")
        if status == "explicitly_supported":
            evidence_ids = row.get("evidence_quote_ids", [])
            if not evidence_ids:
                raise RuntimeError(
                    "claim_results entries with explicitly_supported status must include at least one evidence_quote_id."
                )

    payload["hard_issues"] = normalize_issue_rows(payload.get("hard_issues", []))
    payload["soft_issues"] = normalize_issue_rows(payload.get("soft_issues", []))


def evaluate_with_llm(
    model: str,
    query_id: str,
    original_query: str,
    expected_answer: str,
    generated_answer: str,
    supporting_quotes: list[dict[str, str]],
    expected_facts: list[str],
    forbidden_claims: list[str],
) -> dict[str, Any]:
    """Run deterministic structured LLM grading for one generated answer."""
    supporting_quotes_payload = build_supporting_quotes_payload(supporting_quotes)
    valid_quote_ids = {
        str(row.get("quote_id", "")).strip()
        for row in supporting_quotes_payload
        if str(row.get("quote_id", "")).strip()
    }
    client = get_openai_client()
    response = create_chat_completion(
        client,
        payload={
            "model": model,
            "temperature": 0,
            "seed": deterministic_seed(),
            "messages": [
                {"role": "system", "content": ANSWER_EVAL_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_eval_user_prompt(
                        query_id=query_id,
                        original_query=original_query,
                        expected_answer=expected_answer,
                        generated_answer=generated_answer,
                        supporting_quotes=supporting_quotes,
                        expected_facts=expected_facts,
                        forbidden_claims=forbidden_claims,
                    ),
                },
            ],
            "response_format": ANSWER_EVAL_RESPONSE_FORMAT,
        },
    )
    payload = parse_structured_response_content(response.choices[0].message.content)
    payload = normalize_supported_rows(payload, valid_quote_ids=valid_quote_ids)
    validate_eval_shape(payload, valid_quote_ids=valid_quote_ids)
    return payload


def evaluate_dry_run(original_query: str, generated_answer: str, supporting_quotes: list[dict[str, str]]) -> dict[str, Any]:
    quote_ids = [row["quote_id"] for row in supporting_quotes]
    return {
        "query_requirements": [
            {"requirement_id": "r1", "text": f"Answer the query directly: {original_query}", "critical": True}
        ],
        "answer_claims": [
            {"claim_id": "c1", "text": generated_answer, "substantive": True}
        ],
        "requirement_results": [
            {
                "requirement_id": "r1",
                "status": "explicitly_supported",
                "evidence_quote_ids": quote_ids[:1],
                "reason": "Dry-run placeholder judgment.",
            }
        ],
        "claim_results": [
            {
                "claim_id": "c1",
                "status": "explicitly_supported",
                "evidence_quote_ids": quote_ids[:1],
                "reason": "Dry-run placeholder judgment.",
            }
        ],
        "hard_issues": [],
        "soft_issues": [],
    }


def list_statuses(rows: list[dict[str, Any]]) -> list[str]:
    statuses: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            value = str(row.get("status", "")).strip()
            if value:
                statuses.append(value)
    return statuses


def has_issue_type(issues: list[dict[str, Any]], target: str) -> bool:
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("issue_type", "")).strip() == target:
            return True
    return False


def build_test_result(test_name: str, passed: bool | None, detail: str) -> dict[str, str]:
    if passed is True:
        status = "pass"
    elif passed is False:
        status = "fail"
    else:
        status = "n/a"
    return {"test": test_name, "status": status, "detail": detail}


def has_material_incompleteness(
    requirement_rows: list[dict[str, Any]],
    critical_requirement_ids: set[str],
    allow_no_evidence_absence_claims: bool = False,
) -> bool:
    rows_to_check = [
        row for row in requirement_rows if str(row.get("requirement_id", "")).strip() in critical_requirement_ids
    ]
    if not rows_to_check:
        rows_to_check = requirement_rows

    for row in rows_to_check:
        status = str(row.get("status", "")).strip()
        if status == "contradicted":
            return True
        if status == "unsupported_inference" and not allow_no_evidence_absence_claims:
            return True
    return False


def is_allowed_no_evidence_absence_case(
    expected_citations: list[str],
    returned_citations: list[str],
    supporting_quotes: list[dict[str, str]],
    expected_answer: str,
    generated_answer: str,
) -> bool:
    return (
        len(expected_citations) == 0
        and len(returned_citations) == 0
        and len(supporting_quotes) == 0
        and is_no_files_available_text(expected_answer)
        and is_no_files_available_text(generated_answer)
    )


def strip_invalid_hard_issues_for_no_evidence_absence_case(
    hard_issues: list[dict[str, Any]],
    claim_text_by_id: dict[str, str],
    requirement_text_by_id: dict[str, str],
) -> list[dict[str, Any]]:
    allowed_claim_ids = {
        normalize_related_reference_id(claim_id)
        for claim_id, text in claim_text_by_id.items()
        if is_no_files_available_text(text)
    }
    allowed_requirement_ids = {
        normalize_related_reference_id(requirement_id)
        for requirement_id, text in requirement_text_by_id.items()
        if is_no_files_available_text(text)
    }
    allowed_reference_ids = allowed_claim_ids | allowed_requirement_ids
    allowed_issue_types = {
        "unsupported_substantive_claim",
        "missing_evidence",
        "missing_required_evidence",
        "answer_lacks_explicit_evidence_citation",
    }

    filtered: list[dict[str, Any]] = []
    for issue in hard_issues:
        if not isinstance(issue, dict):
            continue
        issue_type = str(issue.get("issue_type", "")).strip()
        related_ids = normalize_related_reference_ids(issue.get("related_ids", []))
        if issue_type in allowed_issue_types and related_ids and all(item in allowed_reference_ids for item in related_ids):
            continue
        filtered.append(issue)
    return filtered


def remove_hallucinated_hard_issues(
    answer_claims: list[dict[str, Any]],
    hard_issues: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    claim_ids = {
        normalize_related_reference_id(str(row.get("claim_id", "")).strip())
        for row in answer_claims
        if isinstance(row, dict) and str(row.get("claim_id", "")).strip()
    }

    filtered: list[dict[str, Any]] = []
    discarded_reasons: list[str] = []
    for issue in hard_issues:
        if not isinstance(issue, dict):
            continue
        issue_type = str(issue.get("issue_type", "")).strip()
        if issue_type != "unsupported_substantive_claim":
            filtered.append(issue)
            continue

        related_ids = normalize_related_reference_ids(issue.get("related_ids", []))
        if not related_ids:
            discarded_reasons.append("missing related claim IDs")
            continue

        related_claim_ids = [claim_id for claim_id in related_ids if claim_id in claim_ids]
        if not related_claim_ids:
            if any(claim_id.startswith("c") for claim_id in related_ids):
                discarded_reasons.append("referenced claim ID does not exist")
            else:
                discarded_reasons.append("issue could not be tied to a real generated-answer claim")
            continue

        issue["related_ids"] = related_claim_ids
        filtered.append(issue)
    return filtered, discarded_reasons


def claims_are_semantically_safe(
    claim_rows: list[dict[str, Any]],
    claim_text_by_id: dict[str, str],
    allow_no_evidence_absence_claims: bool,
) -> bool:
    for row in claim_rows:
        status = str(row.get("status", "")).strip()
        if status in {"contradicted", "out_of_scope"}:
            return False
        if status != "unsupported_inference":
            continue
        if not allow_no_evidence_absence_claims:
            return False
        claim_id = str(row.get("claim_id", "")).strip()
        if not is_no_files_available_text(claim_text_by_id.get(claim_id, "")):
            return False
    return True


def should_ignore_remaining_hard_issues(
    findings: dict[str, Any],
    allow_no_evidence_absence_claims: bool,
) -> bool:
    requirement_rows = findings.get("requirement_results", [])
    claim_rows = findings.get("claim_results", [])
    hard_issues = findings.get("hard_issues", [])
    answer_claims = findings.get("answer_claims", [])
    if not isinstance(requirement_rows, list) or not isinstance(claim_rows, list) or not isinstance(hard_issues, list):
        return False

    critical_requirements = {
        str(row.get("requirement_id", "")).strip()
        for row in findings.get("query_requirements", [])
        if isinstance(row, dict) and bool(row.get("critical", False))
    }
    substantive_claims = {
        str(row.get("claim_id", "")).strip()
        for row in answer_claims
        if isinstance(row, dict) and bool(row.get("substantive", False))
    }
    claim_text_by_id = {
        str(row.get("claim_id", "")).strip(): str(row.get("text", "")).strip()
        for row in answer_claims
        if isinstance(row, dict)
    }

    requirement_rows_for_hard = [
        row for row in requirement_rows if str(row.get("requirement_id", "")).strip() in critical_requirements
    ] or requirement_rows
    claim_rows_for_hard = [row for row in claim_rows if str(row.get("claim_id", "")).strip() in substantive_claims] or claim_rows

    if has_material_incompleteness(
        requirement_rows_for_hard,
        critical_requirements,
        allow_no_evidence_absence_claims=allow_no_evidence_absence_claims,
    ):
        return False

    if not claims_are_semantically_safe(
        claim_rows_for_hard,
        claim_text_by_id=claim_text_by_id,
        allow_no_evidence_absence_claims=allow_no_evidence_absence_claims,
    ):
        return False

    ignorable_issue_types = {
        "unsupported_substantive_claim",
        "missing_evidence",
        "missing_required_evidence",
        "answer_lacks_explicit_evidence_citation",
    }
    for issue in hard_issues:
        issue_type = str(issue.get("issue_type", "")).strip()
        if not issue_type or issue_type not in ignorable_issue_types:
            return False
    return True


def finalize_reportable_hard_issues(
    findings: dict[str, Any],
    allow_no_evidence_absence_claims: bool,
) -> list[dict[str, Any]]:
    hard_issues = findings.get("hard_issues", [])
    if not isinstance(hard_issues, list):
        return []

    normalized = normalize_issue_rows(hard_issues)
    if not allow_no_evidence_absence_claims:
        return normalized

    local_findings = {**findings, "hard_issues": normalized}
    if should_ignore_remaining_hard_issues(
        local_findings,
        allow_no_evidence_absence_claims=allow_no_evidence_absence_claims,
    ):
        return []
    return normalized


def deterministic_verdict(findings: dict[str, Any], allow_no_evidence_absence_claims: bool = False) -> dict[str, Any]:
    requirement_rows = findings.get("requirement_results", [])
    claim_rows = findings.get("claim_results", [])
    hard_issues = findings.get("hard_issues", [])
    soft_issues = findings.get("soft_issues", [])

    if not isinstance(requirement_rows, list) or not isinstance(claim_rows, list):
        raise RuntimeError("Findings missing requirement_results or claim_results arrays.")
    if not isinstance(hard_issues, list) or not isinstance(soft_issues, list):
        raise RuntimeError("Findings missing hard_issues or soft_issues arrays.")

    if not requirement_rows:
        raise RuntimeError("Findings requirement_results must not be empty.")
    if not claim_rows:
        raise RuntimeError("Findings claim_results must not be empty.")

    critical_requirements: set[str] = {
        str(row.get("requirement_id", "")).strip()
        for row in findings.get("query_requirements", [])
        if isinstance(row, dict) and bool(row.get("critical", False))
    }
    substantive_claims: set[str] = {
        str(row.get("claim_id", "")).strip()
        for row in findings.get("answer_claims", [])
        if isinstance(row, dict) and bool(row.get("substantive", False))
    }

    critical_requirement_rows = [
        row
        for row in requirement_rows
        if str(row.get("requirement_id", "")).strip() in critical_requirements
    ]
    substantive_claim_rows = [row for row in claim_rows if str(row.get("claim_id", "")).strip() in substantive_claims]
    claim_text_by_id: dict[str, str] = {
        str(row.get("claim_id", "")).strip(): str(row.get("text", "")).strip()
        for row in findings.get("answer_claims", [])
        if isinstance(row, dict)
    }

    requirement_rows_for_hard = critical_requirement_rows if critical_requirement_rows else requirement_rows
    claim_rows_for_hard = substantive_claim_rows if substantive_claim_rows else claim_rows

    requirement_supported_have_evidence = all(
        str(row.get("status", "")).strip() != "explicitly_supported"
        or (
            isinstance(row.get("evidence_quote_ids"), list)
            and any(str(item).strip() for item in row.get("evidence_quote_ids", []))
        )
        for row in requirement_rows
    )
    claim_supported_have_evidence = all(
        str(row.get("status", "")).strip() != "explicitly_supported"
        or (
            isinstance(row.get("evidence_quote_ids"), list)
            and any(str(item).strip() for item in row.get("evidence_quote_ids", []))
        )
        for row in claim_rows
    )

    if allow_no_evidence_absence_claims:
        requirements_allowable = all(
            str(row.get("status", "")).strip() in {"explicitly_supported", "unsupported_inference"}
            for row in requirement_rows_for_hard
        )
    else:
        requirements_allowable = all(
            str(row.get("status", "")).strip() != "contradicted" for row in requirement_rows_for_hard
        )

    if allow_no_evidence_absence_claims:
        no_unsupported_inference_claims = all(
            str(row.get("status", "")).strip() != "unsupported_inference"
            or is_no_files_available_text(claim_text_by_id.get(str(row.get("claim_id", "")).strip(), ""))
            for row in claim_rows_for_hard
        )
    else:
        no_unsupported_inference_claims = all(
            str(row.get("status", "")).strip() != "unsupported_inference" for row in claim_rows_for_hard
        )
    no_contradicted_claims = all(str(row.get("status", "")).strip() != "contradicted" for row in claim_rows_for_hard)
    no_spillover_outside_evidence_claims = all(
        str(row.get("status", "")).strip() != "out_of_scope" for row in claim_rows_for_hard
    )
    no_llm_hard_issues = len(hard_issues) == 0 or should_ignore_remaining_hard_issues(
        findings,
        allow_no_evidence_absence_claims=allow_no_evidence_absence_claims,
    )

    hard_tests = [
        build_test_result(
            test_name="requirements_not_contradicted",
            passed=requirements_allowable,
            detail="Critical requirements must not be contradicted by the generated answer.",
        ),
        build_test_result(
            test_name="supported_requirements_have_evidence",
            passed=requirement_supported_have_evidence,
            detail="Each explicitly_supported requirement_result must include at least one evidence_quote_id.",
        ),
        build_test_result(
            test_name="no_unsupported_inference_claims",
            passed=no_unsupported_inference_claims,
            detail="No substantive claim_result may have status unsupported_inference.",
        ),
        build_test_result(
            test_name="supported_claims_have_evidence",
            passed=claim_supported_have_evidence,
            detail="Each explicitly_supported claim_result must include at least one evidence_quote_id.",
        ),
        build_test_result(
            test_name="no_contradicted_claims",
            passed=no_contradicted_claims,
            detail="No substantive claim_result may have status contradicted.",
        ),
        build_test_result(
            test_name="no_spillover_outside_evidence_claims",
            passed=no_spillover_outside_evidence_claims,
            detail="No substantive claim_result may have status out_of_scope.",
        ),
        build_test_result(
            test_name="no_hard_issues",
            passed=no_llm_hard_issues,
            detail="LLM hard_issues array must be empty.",
        ),
    ]

    hard_fail = not all(test["status"] == "pass" for test in hard_tests)

    material_incompleteness = has_material_incompleteness(
        requirement_rows_for_hard,
        critical_requirements,
        allow_no_evidence_absence_claims=allow_no_evidence_absence_claims,
    )

    soft_tests = [
        build_test_result(
            test_name="answer_materially_complete",
            passed=not material_incompleteness,
            detail="Critical query requirements should be sufficiently answered, allowing semantic paraphrase.",
        ),
        build_test_result(
            test_name="soft_issues_present",
            passed=None if not soft_issues else True,
            detail="Soft issues are warnings and do not automatically fail the verdict.",
        ),
    ]

    if hard_fail:
        failed_tests = [test["test"] for test in hard_tests if test["status"] == "fail"]
        return {
            "verdict": "hard_fail",
            "reasons": failed_tests,
            "failed_tests": failed_tests,
            "hard_tests": hard_tests,
            "soft_tests": soft_tests,
        }

    if material_incompleteness:
        failed_tests = ["answer_materially_complete"]
        return {
            "verdict": "soft_fail",
            "reasons": failed_tests,
            "failed_tests": failed_tests,
            "hard_tests": hard_tests,
            "soft_tests": soft_tests,
        }

    return {
        "verdict": "pass",
        "reasons": [],
        "failed_tests": [],
        "hard_tests": hard_tests,
        "soft_tests": soft_tests,
    }


def run_for_query(
    query: dict[str, Any],
    answer_payload: dict[str, Any],
    quote_payload: dict[str, Any],
    rerank_payload: dict[str, Any] | None,
    doc_metadata: dict[str, dict[str, Any]],
    model: str,
    dry_run: bool,
    default_citation_policy: str,
) -> dict[str, Any]:
    query_id = str(query["id"])
    question = str(query.get("question", ""))
    expected_answer = str(query.get("expected_answer", "")).strip()
    generated_answer = str(answer_payload.get("answer", "")).strip()

    if not generated_answer:
        raise RuntimeError(f"Missing generated answer for query_id={query_id}")

    supporting_quotes = normalize_supporting_quotes(quote_payload)
    returned_citations = normalize_doc_ids(answer_payload.get("citations", []))
    expected_citations = optional_expected_citations(query)
    citation_policy = optional_citation_policy(query, default_policy=default_citation_policy)
    expected_facts = optional_expected_facts(query)
    forbidden_claims = merge_forbidden_claim_aliases(query)

    no_evidence_absence_mode = is_allowed_no_evidence_absence_case(
        expected_citations=expected_citations,
        returned_citations=returned_citations,
        supporting_quotes=supporting_quotes,
        expected_answer=expected_answer,
        generated_answer=generated_answer,
    )

    if dry_run:
        findings = evaluate_dry_run(question, generated_answer, supporting_quotes)
        eval_source = "heuristic_dry_run"
    else:
        findings = evaluate_with_llm(
            model=model,
            query_id=query_id,
            original_query=question,
            expected_answer=expected_answer,
            generated_answer=generated_answer,
            supporting_quotes=supporting_quotes,
            expected_facts=expected_facts,
            forbidden_claims=forbidden_claims,
        )
        eval_source = "openai_structured_output"

    citation_assessment = assess_citation_policy(
        citation_policy=citation_policy,
        query=query,
        returned_citations=returned_citations,
        expected_citations=expected_citations,
        supporting_quotes=supporting_quotes,
        doc_metadata=doc_metadata,
        rerank_payload=rerank_payload,
    )

    evaluator_hard_issues = findings.get("hard_issues", []) if isinstance(findings.get("hard_issues", []), list) else []
    llm_hard_issues, discarded_hard_issue_reasons = remove_hallucinated_hard_issues(
        answer_claims=findings.get("answer_claims", []) if isinstance(findings.get("answer_claims", []), list) else [],
        hard_issues=evaluator_hard_issues,
    )
    logger.info(
        "step09 query_id=%s evaluator_hard_issues=%s discarded_by_strict_validation=%s",
        query_id,
        len(evaluator_hard_issues),
        len(discarded_hard_issue_reasons),
    )
    for reason in discarded_hard_issue_reasons:
        logger.info("step09 query_id=%s discarded_hard_issue_reason=%s", query_id, reason)

    findings["hard_issues"] = normalize_issue_rows([*llm_hard_issues, *citation_assessment["hard_issues"]])
    findings["soft_issues"] = normalize_issue_rows([*(findings.get("soft_issues", []) if isinstance(findings.get("soft_issues", []), list) else []), *citation_assessment["soft_issues"]])

    if no_evidence_absence_mode:
        answer_claims = findings.get("answer_claims", []) if isinstance(findings.get("answer_claims", []), list) else []
        query_requirements = findings.get("query_requirements", []) if isinstance(findings.get("query_requirements", []), list) else []
        claim_text_by_id = {
            str(row.get("claim_id", "")).strip(): str(row.get("text", "")).strip()
            for row in answer_claims
            if isinstance(row, dict)
        }
        requirement_text_by_id = {
            str(row.get("requirement_id", "")).strip(): str(row.get("text", "")).strip()
            for row in query_requirements
            if isinstance(row, dict)
        }
        findings["hard_issues"] = strip_invalid_hard_issues_for_no_evidence_absence_case(
            findings.get("hard_issues", []),
            claim_text_by_id=claim_text_by_id,
            requirement_text_by_id=requirement_text_by_id,
        )

    findings["hard_issues"] = finalize_reportable_hard_issues(
        findings,
        allow_no_evidence_absence_claims=no_evidence_absence_mode,
    )
    verdict = deterministic_verdict(findings, allow_no_evidence_absence_claims=no_evidence_absence_mode)

    no_hard_issues_test = next(
        (
            test for test in verdict.get("hard_tests", [])
            if isinstance(test, dict) and str(test.get("test", "")).strip() == "no_hard_issues"
        ),
        None,
    )
    if (
        no_evidence_absence_mode
        and verdict.get("verdict") == "pass"
        and isinstance(no_hard_issues_test, dict)
        and str(no_hard_issues_test.get("status", "")).strip() == "pass"
    ):
        assert len(findings.get("hard_issues", [])) == 0, (
            f"no-evidence absence alignment failed for query_id={query_id}: "
            f"verdict/no_hard_issues passed but hard_issues remained non-empty"
        )

    return {
        "query_id": query_id,
        "question": question,
        "answer": generated_answer,
        "expected_answer": expected_answer,
        "expected_citations": expected_citations,
        "returned_citations": returned_citations,
        "citation_policy": citation_policy,
        "citations_match": citation_assessment["citations_match"],
        "missing_expected_citations": citation_assessment["missing_expected_citations"],
        "unexpected_returned_citations": citation_assessment["unexpected_returned_citations"],
        "tenant_isolation_respected": citation_assessment["tenant_isolation_respected"],
        "access_permissions_respected": citation_assessment["access_permissions_respected"],
        "citation_mismatch_root_causes": citation_assessment["citation_mismatch_root_causes"],
        "eval_model": model,
        "eval_source": eval_source,
        "quote_count": len(supporting_quotes),
        "findings": findings,
        "verdict": verdict["verdict"],
        "failed_tests": verdict["failed_tests"],
        "hard_tests": verdict["hard_tests"],
        "soft_tests": verdict["soft_tests"],
    }


def build_halted_eval_row(query: dict[str, Any], answer_payload: dict[str, Any]) -> dict[str, Any]:
    query_id = str(query.get("id", ""))
    question = str(query.get("question", ""))
    expected_answer = str(query.get("expected_answer", "")).strip()
    error_type = str(answer_payload.get("error_type", "")).strip() or "UpstreamStep08Error"
    error_message = str(answer_payload.get("error_message", "")).strip() or "Step 08 halted this query before evaluation."
    detail = (
        f"Step 08 halted query processing; Step 09 evaluation skipped. "
        f"error_type={error_type}; error={error_message}"
    )
    return {
        "query_id": query_id,
        "question": question,
        "answer": "",
        "expected_answer": expected_answer,
        "expected_citations": optional_expected_citations(query),
        "returned_citations": [],
        "citation_policy": optional_citation_policy(query, default_policy="subset"),
        "citations_match": False,
        "missing_expected_citations": optional_expected_citations(query),
        "unexpected_returned_citations": [],
        "tenant_isolation_respected": True,
        "access_permissions_respected": True,
        "citation_mismatch_root_causes": ["upstream_step08_halted"],
        "eval_model": "(skipped)",
        "eval_source": "skipped_due_to_upstream_error",
        "quote_count": 0,
        "findings": {
            "query_requirements": [],
            "answer_claims": [],
            "requirement_results": [],
            "claim_results": [],
            "hard_issues": [
                {
                    "issue_type": "upstream_query_halted",
                    "detail": detail,
                    "related_ids": [query_id],
                }
            ],
            "soft_issues": [],
        },
        "verdict": "hard_fail",
        "verdict_reasons": ["upstream_query_halted"],
        "failed_tests": ["upstream_query_halted"],
        "hard_tests": [],
        "soft_tests": [],
    }


def is_step08_halted(answer_payload: dict[str, Any]) -> bool:
    status = str(answer_payload.get("status", "ready_for_eval")).strip() or "ready_for_eval"
    return status.startswith("halted")


def extract_doc_ids(candidates: Any) -> list[str]:
    if not isinstance(candidates, list):
        return []
    output: list[str] = []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        doc_id = str(row.get("doc_id", "")).strip()
        if doc_id and doc_id not in output:
            output.append(doc_id)
    return output


def to_json_block(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


FAILED_TEST_REASON_LABELS: dict[str, str] = {
    "requirements_not_contradicted": "Required answer points are contradicted by the generated answer",
    "supported_requirements_have_evidence": "Supported requirements lack evidence citations",
    "no_unsupported_inference_claims": "Answer includes claims that are not explicitly supported by evidence",
    "supported_claims_have_evidence": "Supported claims lack evidence citations",
    "no_contradicted_claims": "Answer includes claims contradicted by evidence",
    "no_spillover_outside_evidence_claims": "Answer includes claims outside the requested/evidence scope",
    "no_hard_issues": "Evaluator reported hard issues",
    "answer_materially_complete": "Answer is materially incomplete for the question",
    "soft_issues_present": "Evaluator reported soft issues (warning only)",
}


def humanize_test_name(label: str) -> str:
    return label.replace("_", " ").strip().capitalize()


def readable_test_reason(test_name: str, status: str | None = None) -> str:
    key = test_name.strip()
    normalized_status = (status or "").strip().lower()
    if normalized_status in {"", "fail"} and key in FAILED_TEST_REASON_LABELS:
        return FAILED_TEST_REASON_LABELS[key]
    return humanize_test_name(key)


def format_failed_tests_with_status(row: dict[str, Any]) -> str:
    failed = row.get("failed_tests", [])
    if not isinstance(failed, list) or not failed:
        return "(none)"

    tests_by_name: dict[str, dict[str, Any]] = {}
    for group in (row.get("hard_tests", []), row.get("soft_tests", [])):
        if not isinstance(group, list):
            continue
        for test in group:
            if not isinstance(test, dict):
                continue
            name = str(test.get("test", "")).strip()
            if name:
                tests_by_name[name] = test

    rendered: list[str] = []
    for test_name in failed:
        key = str(test_name).strip()
        if not key:
            continue
        status = "fail"
        if isinstance(tests_by_name.get(key), dict):
            status = str(tests_by_name[key].get("status", "fail")).strip() or "fail"
        rendered.append(f"{readable_test_reason(key, status)} ({status})")
    return ", ".join(rendered) if rendered else "(none)"


def format_failed_tests(row: dict[str, Any]) -> str:
    return format_failed_tests_with_status(row)


def build_failure_trace_markdown(
    row: dict[str, Any],
    step3_payload: dict[str, Any] | None,
    step4_payload: dict[str, Any] | None,
    step5_payload: dict[str, Any] | None,
    step6_payload: dict[str, Any] | None,
    step7_payload: dict[str, Any] | None,
    step8_payload: dict[str, Any] | None,
) -> str:
    query_id = str(row.get("query_id", ""))
    verdict = str(row.get("verdict", ""))
    failed_tests_text = format_failed_tests(row)
    expected_answer = str(row.get("expected_answer", "")).strip()
    generated_answer = str(row.get("answer", "")).strip()
    question = str(row.get("question", "")).strip()

    expected_citations = normalize_doc_ids(row.get("expected_citations", []))
    returned_citations = normalize_doc_ids(row.get("returned_citations", []))
    missing = normalize_doc_ids(row.get("missing_expected_citations", []))
    extra = normalize_doc_ids(row.get("unexpected_returned_citations", []))
    if not missing:
        missing = sorted(set(expected_citations) - set(returned_citations))
    if not extra:
        extra = sorted(set(returned_citations) - set(expected_citations))

    step4_doc_ids = extract_doc_ids((step4_payload or {}).get("candidates", []))
    step5_doc_ids = extract_doc_ids((step5_payload or {}).get("candidates", []))
    step6_candidates = (step6_payload or {}).get("ranked_candidates")
    if not isinstance(step6_candidates, list):
        step6_candidates = (step6_payload or {}).get("selected_candidates", [])
    step6_doc_ids = extract_doc_ids(step6_candidates)

    step7_quotes = (step7_payload or {}).get("quotes", [])
    step7_doc_ids = extract_doc_ids(step7_quotes)

    deviation_hints: list[str] = []
    for doc_id in missing:
        if doc_id not in step6_doc_ids:
            deviation_hints.append(
                f"Expected citation `{doc_id}` is missing from Step 06 rerank output, so the fault likely occurs by Step 06 (retrieval/rerank path)."
            )
        elif doc_id not in step7_doc_ids:
            deviation_hints.append(
                f"Expected citation `{doc_id}` exists in Step 06 but not in Step 07 extracted quotes, so the fault likely occurs in Step 07 quote extraction."
            )
        elif doc_id not in returned_citations:
            deviation_hints.append(
                f"Expected citation `{doc_id}` reaches Step 07 evidence but is absent from Step 08 citations, so the fault likely occurs in Step 08 answer assembly."
            )
    for doc_id in extra:
        if doc_id not in step6_doc_ids:
            deviation_hints.append(
                f"Unexpected citation `{doc_id}` appears in Step 08 but not in Step 06 candidates, indicating a likely Step 08 citation assembly issue."
            )

    suspected_source_summary = (
        deviation_hints[0]
        if deviation_hints
        else "Unable to isolate a single step from citation flow; inspect the step payload chain below."
    )

    findings = row.get("findings", {})
    hard_issues = findings.get("hard_issues", []) if isinstance(findings, dict) else []

    lines = [
        f"# Failure Trace — {query_id}",
        "",
        "## Step 09 Failure Signal",
        f"- verdict: `{verdict}`",
        f"- failed_tests: `{failed_tests_text}`",
        f"- question: `{question}`",
        f"- expected_answer: `{expected_answer}`",
        f"- generated_answer: `{generated_answer}`",
        f"- expected_citations: `{expected_citations}`",
        f"- returned_citations: `{returned_citations}`",
        f"- missing_expected_citations: `{missing}`",
        f"- unexpected_returned_citations: `{extra}`",
    ]

    lines.extend(
        [
            "",
            "## Suspected Source of Failure",
            f"- {suspected_source_summary}",
        ]
    )

    if isinstance(hard_issues, list) and hard_issues:
        lines.append("- hard_issues:")
        for issue in hard_issues:
            if not isinstance(issue, dict):
                continue
            lines.append(f"  - `{issue.get('issue_type', 'unknown')}`: {issue.get('detail', '')}")

    lines.extend(
        [
            "",
            "## Step 03 — Query Rewrite + Sparse Plan",
            "```json",
            to_json_block(step3_payload or {}),
            "```",
            "",
            "## Step 04 — Semantic Retrieval",
            f"- candidate_doc_ids: `{step4_doc_ids}`",
            "```json",
            to_json_block(step4_payload or {}),
            "```",
            "",
            "## Step 05 — Sparse Retrieval",
            f"- candidate_doc_ids: `{step5_doc_ids}`",
            "```json",
            to_json_block(step5_payload or {}),
            "```",
            "",
            "## Step 06 — Rerank",
            f"- ranked_doc_ids: `{step6_doc_ids}`",
            "```json",
            to_json_block(step6_payload or {}),
            "```",
            "",
            "## Step 07 — Quote Extraction",
            f"- extracted_quote_doc_ids: `{step7_doc_ids}`",
            "```json",
            to_json_block(step7_payload or {}),
            "```",
            "",
            "## Step 08 — Answer",
            "```json",
            to_json_block(step8_payload or {}),
            "```",
            "",
            "## Deviation Analysis (Step 03 → Step 08)",
        ]
    )
    if deviation_hints:
        lines.extend([f"- {hint}" for hint in deviation_hints])
    else:
        lines.append("- Unable to isolate a single step from citation flow; inspect the full payload chain above.")

    return "\n".join(lines) + "\n"


def write_failure_traces(
    rows: list[dict[str, Any]],
    step3_by_id: dict[str, dict[str, Any]],
    step4_by_id: dict[str, dict[str, Any]],
    step5_by_id: dict[str, dict[str, Any]],
    step6_by_id: dict[str, dict[str, Any]],
    step7_by_id: dict[str, dict[str, Any]],
    step8_by_id: dict[str, dict[str, Any]],
) -> None:
    def safe_trace_stem(query_id: str) -> str:
        normalized = SAFE_TRACE_FILENAME_RE.sub("_", query_id).strip("._-")
        if normalized:
            return normalized
        return "query"

    traces_dir = STEP9_DIR / FAILURE_TRACES_DIRNAME
    traces_dir.mkdir(parents=True, exist_ok=True)
    used_trace_names: set[str] = set()

    for stale in traces_dir.glob("*.md"):
        stale.unlink()

    for row in rows:
        if str(row.get("verdict", "")).strip() == "pass":
            row["failure_trace_path"] = ""
            continue

        query_id = str(row.get("query_id", "")).strip()
        if not query_id:
            continue

        sanitized_stem = safe_trace_stem(query_id)
        query_hash = hashlib.sha1(query_id.encode("utf-8")).hexdigest()[:8]
        trace_name = f"{sanitized_stem}-{query_hash}.md"
        while trace_name in used_trace_names:
            query_hash = hashlib.sha1(f"{query_id}:{trace_name}".encode("utf-8")).hexdigest()[:8]
            trace_name = f"{sanitized_stem}-{query_hash}.md"
        used_trace_names.add(trace_name)

        trace_path = traces_dir / trace_name
        trace_markdown = build_failure_trace_markdown(
            row=row,
            step3_payload=step3_by_id.get(query_id),
            step4_payload=step4_by_id.get(query_id),
            step5_payload=step5_by_id.get(query_id),
            step6_payload=step6_by_id.get(query_id),
            step7_payload=step7_by_id.get(query_id),
            step8_payload=step8_by_id.get(query_id),
        )
        trace_path.write_text(trace_markdown, encoding="utf-8")
        row["failure_trace_path"] = str(Path(FAILURE_TRACES_DIRNAME) / trace_name)


def build_summary(rows: list[dict[str, Any]]) -> str:
    def format_issue(issue: Any) -> str:
        if not isinstance(issue, dict):
            return "(invalid issue payload)"
        issue_type = humanize_test_name(str(issue.get("issue_type", "unspecified")))
        detail = str(issue.get("detail", "")).strip() or "(no detail provided)"
        related_ids = issue.get("related_ids", [])
        related = ", ".join(str(item).strip() for item in related_ids if str(item).strip()) if isinstance(related_ids, list) else ""
        related_suffix = f" [related: {related}]" if related else ""
        return f"{issue_type}: {detail}{related_suffix}"

    lines = ["# Step 09 Summaries", ""]
    for row in rows:
        hard_tests = row.get("hard_tests", [])
        soft_tests = row.get("soft_tests", [])
        hard_issues = row.get("findings", {}).get("hard_issues", [])
        soft_issues = row.get("findings", {}).get("soft_issues", [])
        readable_failed_tests = format_failed_tests(row)
        if isinstance(row.get("failed_tests"), list) and row.get("failed_tests"):
            readable_verdict_reasons = format_failed_tests_with_status(row)
        else:
            verdict_reasons = row.get("verdict_reasons", [])
            if isinstance(verdict_reasons, list) and verdict_reasons:
                status_by_test: dict[str, str] = {}
                for test_row in [*(hard_tests if isinstance(hard_tests, list) else []), *(soft_tests if isinstance(soft_tests, list) else [])]:
                    if isinstance(test_row, dict):
                        status_by_test[str(test_row.get("test", ""))] = str(test_row.get("status", ""))
                parts: list[str] = []
                for reason in verdict_reasons:
                    reason_name = str(reason).strip()
                    if not reason_name:
                        continue
                    readable = readable_test_reason(reason_name, status_by_test.get(reason_name))
                    status = status_by_test.get(reason_name)
                    parts.append(f"{readable} ({status})" if status else readable)
                readable_verdict_reasons = ", ".join(parts) if parts else "(none)"
            else:
                readable_verdict_reasons = "(none)"
        lines.extend(
            [
                f"## Query `{row['query_id']}`",
                "",
                f"- question: `{row.get('question', '')}`",
                f"- verdict: `{row.get('verdict', '(missing)')}`",
                f"- verdict reasons: `{readable_verdict_reasons}`",
                f"- failed tests: `{readable_failed_tests}`",
                "- expected answer:",
                "```md",
                str(row.get('expected_answer', '')),
                "```",
                "- generated answer:",
                "```md",
                str(row.get('answer', '')),
                "```",
                f"- failure trace: `{row.get('failure_trace_path') or '(none)'}`",
                f"- hard issues: `{len(hard_issues)}`",
                f"- soft issues: `{len(soft_issues)}`",
                "- hard tests:",
            ]
        )
        if isinstance(hard_tests, list) and hard_tests:
            for test in hard_tests:
                if not isinstance(test, dict):
                    continue
                test_name = str(test.get("test", "(missing)"))
                test_status = str(test.get("status", "(missing)"))
                lines.append(
                    f"  - `{test_name}` ({readable_test_reason(test_name, test_status)}) => `{test_status}`"
                )
        else:
            lines.append("  - `(none)`")

        lines.append("- soft tests:")
        if isinstance(soft_tests, list) and soft_tests:
            for test in soft_tests:
                if not isinstance(test, dict):
                    continue
                test_name = str(test.get("test", "(missing)"))
                test_status = str(test.get("status", "(missing)"))
                lines.append(
                    f"  - `{test_name}` ({readable_test_reason(test_name, test_status)}) => `{test_status}`"
                )
        else:
            lines.append("  - `(none)`")

        lines.append("- summary:")
        if isinstance(hard_issues, list) and hard_issues:
            lines.append("  - hard issue details:")
            for issue in hard_issues:
                lines.append(f"    - {format_issue(issue)}")
        if isinstance(soft_issues, list) and soft_issues:
            lines.append("  - soft issue details:")
            for issue in soft_issues:
                lines.append(f"    - {format_issue(issue)}")
        if (not isinstance(hard_issues, list) or not hard_issues) and (not isinstance(soft_issues, list) or not soft_issues):
            lines.append("  - No LLM-reported hard/soft issues.")

        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id")
    parser.add_argument("--all-queries", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--model")
    parser.add_argument("--citation-policy", choices=sorted(VALID_CITATION_POLICIES), default="subset")
    parser.add_argument("--dry-run", action="store_true", help="Skip OpenAI calls and generate deterministic placeholder findings.")
    parser.add_argument("--print-example-payload", action="store_true", help="Print an example evaluation input payload and exit.")
    args = parser.parse_args()

    if args.print_example_payload:
        print(json.dumps(EXAMPLE_EVAL_INPUT, indent=2))
        return

    model = args.model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    query_filter = None if args.all_queries or args.query_id is None else args.query_id
    queries = load_queries(query_filter)
    answers_by_id = answer_rows_by_query_id()
    quotes_by_id = quote_rows_by_query_id()
    query_plans_by_id = query_plan_rows_by_query_id()
    semantic_by_id = semantic_rows_by_query_id()
    sparse_by_id = sparse_rows_by_query_id()
    reranks_by_id = rerank_rows_by_query_id()
    doc_metadata = metadata_by_doc_id()

    def process(query: dict[str, Any]) -> dict[str, Any]:
        query_id = str(query["id"])
        answer_payload = answers_by_id.get(query_id)
        quote_payload = quotes_by_id.get(query_id)
        if answer_payload is None:
            raise RuntimeError(f"Missing Step 08 artifact for query_id={query_id}")
        if quote_payload is None:
            raise RuntimeError(f"Missing Step 07 artifact for query_id={query_id}")
        if is_step08_halted(answer_payload):
            return build_halted_eval_row(query, answer_payload)
        return run_for_query(
            query,
            answer_payload,
            quote_payload,
            rerank_payload=reranks_by_id.get(query_id),
            doc_metadata=doc_metadata,
            model=model,
            dry_run=args.dry_run,
            default_citation_policy=args.citation_policy,
        )

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        rows = list(executor.map(process, queries))

    STEP9_DIR.mkdir(parents=True, exist_ok=True)
    write_failure_traces(
        rows=rows,
        step3_by_id=query_plans_by_id,
        step4_by_id=semantic_by_id,
        step5_by_id=sparse_by_id,
        step6_by_id=reranks_by_id,
        step7_by_id=quotes_by_id,
        step8_by_id=answers_by_id,
    )
    write_jsonl(STEP9_DIR / OUTPUT_FILENAME, rows)
    (STEP9_DIR / SUMMARY_FILENAME).write_text(build_summary(rows), encoding="utf-8")

    print(f"Wrote Step 09 eval outputs for {len(rows)} query(s) -> {STEP9_DIR}")


if __name__ == "__main__":
    main()
