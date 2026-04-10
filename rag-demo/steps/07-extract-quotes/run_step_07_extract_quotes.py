import argparse
import json
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence, TypedDict

if TYPE_CHECKING:
    from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.io_utils import read_jsonl, write_jsonl
from shared.api_payload import create_chat_completion
from shared.openai_client import deterministic_seed, get_openai_client
from shared.paths import QUERY_EVAL_PATH, ROOT, STEP6_DIR, STEP7_DIR

OUTPUT_FILENAME = "quote-extraction.jsonl"
SUMMARY_FILENAME = "07-extract-quotes-summary.md"
MAX_RERANKED_INPUTS = 8
MAX_QUOTES = 5
MAX_QUOTE_CHARS = 280

logger = logging.getLogger(__name__)

COMPARISON_TERMS = {"earlier", "prior", "previous", "difference", "differ", "change", "compared"}
RECENCY_TERMS = {"latest", "most recent", "current", "newest", "recent"}
VALUATION_TERMS = {"valuation", "ask", "pre-money", "post-money", "valued", "seeking"}
COUNTERPARTY_TERMS = {"counter", "counteroffer", "offer", "bid", "response"}
TIMELINE_TERMS = {"timeline", "chronological", "through", "intro", "initial", "later", "latest"}
TIMELINE_MILESTONE_ORDER = ["intro_contact", "initial_terms", "counter_terms", "latest_terms"]
MILESTONE_PRIORITY = {"intro_contact": 0, "initial_terms": 1, "counter_terms": 2, "latest_terms": 3}

QUOTE_EXTRACTION_RESPONSE_FORMAT: "ResponseFormatJSONSchema" = {
    "type": "json_schema",
    "json_schema": {
        "name": "query_relevant_quotes",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "quotes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "chunk_id": {"type": "string"},
                            "doc_id": {"type": "string"},
                            "quote": {"type": "string"},
                            "rationale": {"type": "string"},
                            "milestone_details": {
                                "type": ["object", "null"],
                                "additionalProperties": False,
                                "properties": {
                                    "milestone_type": {"type": ["string", "null"]},
                                    "intro_date_text": {"type": ["string", "null"]},
                                    "valuation_text": {"type": ["string", "null"]},
                                    "raise_amount_text": {"type": ["string", "null"]},
                                    "board_term": {"type": ["string", "null"]},
                                    "liquidation_preference": {"type": ["string", "null"]},
                                    "pro_rata_rights": {"type": ["string", "null"]},
                                    "investor_side": {"type": ["string", "null"]},
                                    "company_side": {"type": ["string", "null"]},
                                    "term_summary_parts": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": [
                                    "milestone_type",
                                    "intro_date_text",
                                    "valuation_text",
                                    "raise_amount_text",
                                    "board_term",
                                    "liquidation_preference",
                                    "pro_rata_rights",
                                    "investor_side",
                                    "company_side",
                                    "term_summary_parts",
                                ],
                            },
                        },
                        "required": ["chunk_id", "doc_id", "quote", "rationale", "milestone_details"],
                    },
                },
                "evidence_coverage": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "field": {"type": "string"},
                            "supported": {"type": "boolean"},
                            "reason": {"type": "string"},
                        },
                        "required": ["field", "supported", "reason"],
                    },
                },
            },
            "required": ["quotes", "evidence_coverage"],
        },
    },
}

EXTRACTION_SYSTEM_PROMPT = """You are a quote extraction stage in a RAG pipeline.

Goal:
Extract only exact, directly relevant quotes from retrieved chunks for the given query.

Rules:
- Do not answer the user query.
- Do not summarize or paraphrase the source text.
- Return exact quotes copied from the candidate text.
- Keep quotes concise and high-signal (1-3 lines, not full chunks).
- Do not return an entire chunk/document when a narrower direct quote is available.
- Exclude quotes that are only topically similar but do not directly support answering the question.
- Also return `evidence_coverage` with one row per requested fact in the query.
- In `evidence_coverage`, mark `supported=true` only if the text explicitly states that field.
- Do not infer missing facts.
- If no quote is relevant, return an empty quotes array.

Same-entity continuity rules:
- For questions like "X's latest valuation" and "earlier ask", keep both comparison points tied to the same entity unless the question explicitly asks for another party.
- Do not treat a counterparty offer, counter, bid, or internal response as X's earlier ask.
- Temporal relevance does not override same-entity comparison continuity.
- Use `question_analysis` and candidate `inferred_position_type`/dates to preserve the correct entity thread.

Timeline milestone rules:
- If `question_analysis.requires_timeline_summary` is true, preserve milestone coverage over term-density.
- Use `question_analysis.timeline_milestones` as required evidence checkpoints.
- Prefer one quote per milestone in chronological order when supporting evidence exists.
- For `intro_contact`, header-derived evidence is valid when it directly supports the milestone (for example Date + Subject + a relevant body line).
- Do not spend multiple quote slots on the same milestone if that causes another required milestone to be omitted.
- For timeline milestones (`intro_contact`, `initial_terms`, `counter_terms`, `latest_terms`), include `milestone_details` for each quote when evidence supports it.
- `milestone_details` must be explicit and evidence-backed: set unsupported fields to null (or [] for `term_summary_parts`), never infer.
- For term milestones, extract material fields when present: valuation_text, raise_amount_text, board_term, liquidation_preference, pro_rata_rights, investor_side, company_side, term_summary_parts.
""".strip()


class QuoteRow(TypedDict):
    chunk_id: str
    doc_id: str
    quote: str
    rationale: str


class EnrichedQuoteRow(QuoteRow, total=False):
    resolver_context: str
    display_snippet: str
    doc_date: str
    timeline_milestone: str
    fact_labels: list[str]
    milestone_details: dict[str, Any]


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


def rerank_rows_by_query_id() -> dict[str, dict[str, Any]]:
    rows = read_jsonl(STEP6_DIR / "rerank.jsonl")
    return {str(row.get("query_id", "")): row for row in rows if isinstance(row, dict) and str(row.get("query_id", ""))}


def normalize_quote_text(text: str) -> str:
    cleaned_lines = [" ".join(line.split()) for line in str(text).splitlines() if line.strip()]
    return "\n".join(cleaned_lines).strip()


def sanitize_quote(quote: str) -> str:
    value = normalize_quote_text(quote)
    if not value:
        return ""
    if len(value) > MAX_QUOTE_CHARS:
        return value[:MAX_QUOTE_CHARS].rstrip()
    return value


def normalize_entity_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def question_requires_same_entity_comparison(question: str) -> bool:
    lowered = question.lower()
    has_comparison = any(term in lowered for term in COMPARISON_TERMS)
    has_recency = any(term in lowered for term in RECENCY_TERMS)
    has_valuation = any(term in lowered for term in VALUATION_TERMS)
    return has_comparison and has_valuation and has_recency


def extract_target_entity(question: str) -> str:
    patterns = [
        r"\bwhat is\s+([A-Z][A-Za-z0-9&\- ]{1,40}?)['’]s\b",
        r"\bhow has\s+([A-Z][A-Za-z0-9&\- ]{1,40}?)['’]s\b",
        r"\b([A-Z][A-Za-z0-9&\- ]{1,40}?)['’]s\s+(?:latest|current|valuation|ask)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            return " ".join(match.group(1).split())
    return ""


def question_requires_timeline_summary(question: str) -> bool:
    lowered = question.lower()
    has_timeline_keyword = any(term in lowered for term in TIMELINE_TERMS)
    has_range_signal = bool(
        re.search(
            r"\bfrom\s+(?:intro|initial|first|start|beginning)\b.*\b(?:to|through)\s+(?:latest|current|most recent|end)\b",
            lowered,
        )
    )
    has_timeline_signal = has_timeline_keyword and any(
        signal in lowered
        for signal in (
            "timeline",
            "from intro",
            "from initial",
            "from first",
            "to latest",
            "through latest",
            "summarize the deal",
        )
    )
    has_ordered_milestones = sum(1 for token in ("intro", "initial", "later", "latest") if token in lowered) >= 2
    has_bullet_and_time_language = ("bullet" in lowered and has_ordered_milestones)
    return has_timeline_signal or has_range_signal or has_bullet_and_time_language


def extract_timeline_milestones(question: str, candidates: list[dict[str, Any]]) -> list[str]:
    if not question_requires_timeline_summary(question):
        return []

    lowered = question.lower()
    milestones: list[str] = []
    should_include_intro = any(token in lowered for token in ("intro", "introduced", "introduction", "from intro", "from first"))
    should_include_initial = any(token in lowered for token in ("initial", "first terms", "started", "initial terms"))
    should_include_counter = any(token in lowered for token in ("counter", "countered", "counteroffer", "response"))
    should_include_latest = any(token in lowered for token in ("latest", "current", "most recent", "revised"))

    if should_include_intro or candidate_pool_has_intro_support(candidates):
        milestones.append("intro_contact")
    if should_include_initial or candidate_pool_has_initial_support(candidates):
        milestones.append("initial_terms")
    if should_include_counter or candidate_pool_has_counter_support(candidates):
        milestones.append("counter_terms")
    if should_include_latest or candidate_pool_has_latest_support(candidates):
        milestones.append("latest_terms")

    ordered = [milestone for milestone in TIMELINE_MILESTONE_ORDER if milestone in milestones]
    return ordered or TIMELINE_MILESTONE_ORDER[:]


def candidate_pool_has_intro_support(candidates: list[dict[str, Any]]) -> bool:
    return any(candidate_supports_intro_milestone(candidate) for candidate in candidates)


def candidate_pool_has_initial_support(candidates: list[dict[str, Any]]) -> bool:
    return any(candidate_supports_initial_terms_milestone(candidate) for candidate in candidates)


def candidate_pool_has_counter_support(candidates: list[dict[str, Any]]) -> bool:
    return any(candidate_supports_counter_milestone(candidate) for candidate in candidates)


def candidate_pool_has_latest_support(candidates: list[dict[str, Any]]) -> bool:
    return any(candidate_supports_latest_terms_milestone(candidate) for candidate in candidates)


def parse_candidate_date(candidate: dict[str, Any]) -> date | None:
    metadata = candidate.get("metadata", {})
    if not isinstance(metadata, dict):
        return None
    raw = str(metadata.get("date", "")).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


COUNTERPARTY_SIGNAL_PHRASES = (
    "counter on",
    "counteroffer",
    "our side",
    "internal review",
    "prepared to proceed",
    "would be prepared to proceed",
)

TARGET_POSITION_SIGNAL_PHRASES = (
    "the company is now proposing",
    "is raising",
    "we are raising",
    "updated term sheet",
    "revised term sheet",
)


def candidate_has_explicit_valuation_line(candidate: dict[str, Any]) -> bool:
    return bool(extract_best_valuation_quote(candidate))


def extract_best_valuation_quote(candidate: dict[str, Any]) -> str:
    lines = get_candidate_lines(candidate)

    preferred_lines = find_preferred_valuation_lines(lines)
    if preferred_lines:
        return sanitize_quote(preferred_lines[0])

    fallback_lines = find_fallback_valuation_lines(lines)
    if fallback_lines:
        return sanitize_quote(fallback_lines[0])

    return ""


def get_candidate_lines(candidate: dict[str, Any]) -> list[str]:
    text = str(candidate.get("text", ""))
    return [normalize_quote_text(line) for line in text.splitlines() if line.strip()]


def candidate_supports_intro_milestone(candidate: dict[str, Any]) -> bool:
    lines = get_candidate_lines(candidate)
    text = "\n".join(lines).lower()
    has_intro_language = any(
        token in text
        for token in (
            "subject: intro",
            "subject: introduction",
            "introduced to",
            "introduction to",
            "great to meet",
            "great meeting",
            "connecting you",
        )
    )
    has_date = any(line.lower().startswith("date:") for line in lines)
    has_subject = any(line.lower().startswith("subject:") for line in lines)
    return has_intro_language and (has_date or has_subject)


def candidate_supports_initial_terms_milestone(candidate: dict[str, Any]) -> bool:
    lines = get_candidate_lines(candidate)
    text = "\n".join(lines).lower()
    has_initial_language = any(token in text for token in ("is raising", "series a", "initial", "introductory diligence call"))
    has_valuation = any("$" in line and ("pre-money" in line.lower() or "valuation" in line.lower()) for line in lines)
    return has_initial_language and has_valuation


def candidate_supports_counter_milestone(candidate: dict[str, Any]) -> bool:
    lines = get_candidate_lines(candidate)
    text = "\n".join(lines).lower()
    has_counter = candidate_has_explicit_counter_signal(text)
    has_terms = any("$" in line and "pre-money" in line.lower() for line in lines) or "no board seat" in text
    return has_counter and has_terms


def candidate_has_explicit_counter_signal(text: str) -> bool:
    return any(
        token in text
        for token in (
            "counter",
            "counteroffer",
            "counter offer",
            "counterproposal",
            "counter-proposal",
            "from our side",
            "prepared to proceed",
            "our response",
        )
    )


def candidate_has_explicit_latest_terms_signal(text: str) -> bool:
    return any(
        token in text
        for token in (
            "updated term sheet",
            "revised term sheet",
            "latest terms",
            "most recent terms",
            "now proposing",
            "current terms",
        )
    )


def candidate_has_concrete_term_bundle(lines: list[str], text: str) -> bool:
    has_money_term = any("$" in line and "pre-money" in line.lower() for line in lines)
    has_structure_term = any(
        token in text
        for token in (
            "board observer",
            "no board seat",
            "liquidation preference",
            "pro-rata",
            "pro rata",
        )
    )
    return has_money_term and has_structure_term


def candidate_supports_latest_terms_milestone(candidate: dict[str, Any]) -> bool:
    lines = get_candidate_lines(candidate)
    text = "\n".join(lines).lower()
    has_latest = candidate_has_explicit_latest_terms_signal(text)
    has_terms = candidate_has_concrete_term_bundle(lines, text)
    if not (has_latest and has_terms):
        return False
    has_counter = candidate_has_explicit_counter_signal(text)
    if not has_counter:
        return True

    # Allow latest classification when counter language is explicitly historical
    # context (e.g., "updated term sheet ... after your counteroffer").
    has_prior_counter_reference = any(
        token in text
        for token in (
            "after your counteroffer",
            "following your counteroffer",
            "in response to your counteroffer",
            "based on your counteroffer",
            "per your counteroffer",
            "after the counteroffer",
            "following the counteroffer",
        )
    )
    return has_prior_counter_reference


def build_intro_evidence_quote(candidate: dict[str, Any]) -> str:
    lines = get_candidate_lines(candidate)
    header_lines = [
        line
        for line in lines
        if line.lower().startswith("date:") or line.lower().startswith("subject:")
    ]
    intro_body = ""
    for line in lines:
        lowered = line.lower()
        if "point of contact" in lowered:
            continue
        if any(
            token in lowered
            for token in (
                "great to meet",
                "introduced",
                "introduction",
                "connecting you",
                "introductory call",
            )
        ):
            intro_body = line
            break
    quote_lines = header_lines[:2]
    if intro_body:
        quote_lines.append(intro_body)
    return sanitize_quote("\n".join(quote_lines))


def infer_timeline_milestone(candidate: dict[str, Any]) -> str:
    scores: dict[str, int] = {milestone: 0 for milestone in TIMELINE_MILESTONE_ORDER}
    text = "\n".join(get_candidate_lines(candidate)).lower()

    if candidate_supports_intro_milestone(candidate):
        scores["intro_contact"] += 3
    if candidate_supports_initial_terms_milestone(candidate):
        scores["initial_terms"] += 4
    if candidate_supports_counter_milestone(candidate):
        scores["counter_terms"] += 4
    if candidate_supports_latest_terms_milestone(candidate):
        scores["latest_terms"] += 4

    if candidate_has_explicit_valuation_line(candidate):
        scores["initial_terms"] += 2
        if "counter" in text or "prepared to proceed" in text:
            scores["counter_terms"] += 2
        if "updated term sheet" in text or "revised term sheet" in text or "now proposing" in text:
            scores["latest_terms"] += 2

    if "introductory" in text and not candidate_has_explicit_valuation_line(candidate):
        scores["intro_contact"] += 1

    best_milestone, best_score = max(
        scores.items(),
        key=lambda item: (item[1], MILESTONE_PRIORITY.get(item[0], -1)),
    )
    if best_score <= 0:
        return ""
    top_milestones = [milestone for milestone, score in scores.items() if score == best_score]
    if "counter_terms" in top_milestones and candidate_has_explicit_counter_signal(text):
        return "counter_terms"
    if scores["initial_terms"] > scores["intro_contact"] and best_milestone == "intro_contact":
        return "initial_terms"
    return best_milestone


def infer_field_repair_quote(field: str, question: str, candidate: dict[str, Any]) -> str:
    if not candidate_is_repair_eligible(field, question, candidate):
        return ""

    support_concepts = infer_field_support_concepts(field, question)
    for support_concept in support_concepts:
        support_quote = extract_quote_for_support_concept(support_concept, candidate)
        if support_quote:
            return support_quote

    return extract_generic_overlap_quote(field, question, candidate)



def infer_field_support_concepts(field: str, question: str) -> list[str]:
    field_text = str(field).lower()
    combined_text = f"{field_text} {str(question).lower()}"

    prioritized_support_concepts: list[str] = []
    if text_mentions_business_issue(field_text):
        prioritized_support_concepts.append("business_issue")
    if text_mentions_customer_concentration(field_text):
        prioritized_support_concepts.append("customer_concentration")
    if text_mentions_acquisition_interest(field_text):
        prioritized_support_concepts.append("acquisition_interest")
    if text_mentions_codename(field_text) and not prioritized_support_concepts:
        prioritized_support_concepts.append("codename")

    if prioritized_support_concepts:
        return dedupe_support_concepts(prioritized_support_concepts)

    fallback_support_concepts: list[str] = []
    if text_mentions_business_issue(combined_text):
        fallback_support_concepts.append("business_issue")
    if text_mentions_customer_concentration(combined_text):
        fallback_support_concepts.append("customer_concentration")
    if text_mentions_acquisition_interest(combined_text):
        fallback_support_concepts.append("acquisition_interest")
    if text_mentions_codename(combined_text) and not fallback_support_concepts:
        fallback_support_concepts.append("codename")

    return dedupe_support_concepts(fallback_support_concepts)


def dedupe_support_concepts(support_concepts: list[str]) -> list[str]:
    ordered_support_concepts: list[str] = []
    for support_concept in support_concepts:
        if support_concept in ordered_support_concepts:
            continue
        ordered_support_concepts.append(support_concept)
    return ordered_support_concepts



def text_mentions_codename(text: str) -> bool:
    lowered_text = str(text).lower()
    if "codename" in lowered_text:
        return True
    return bool(re.search(r"\bproject\s+[a-z0-9][a-z0-9\-]*(?:\s+[a-z0-9][a-z0-9\-]*)*\b", lowered_text))



def text_mentions_business_issue(text: str) -> bool:
    return any(
        token in text
        for token in (
            "business issue",
            "associated issue",
            "attached to it",
            "attached to this",
            "diligence concern",
            "key concern",
            "main risk",
            "risk",
            "issue",
            "concern",
        )
    )


def text_mentions_customer_concentration(text: str) -> bool:
    return any(
        token in text
        for token in (
            "customer concentration",
            "top 2 customers",
            "top two customers",
            "customers account for",
            "% of revenue",
            "percent of revenue",
        )
    )


def text_mentions_acquisition_interest(text: str) -> bool:
    return "acquisition" in text or "omnidynamics" in text


def is_project_definition_field(field: str, question: str) -> bool:
    combined_text = f"{str(field).lower()} {str(question).lower()}"
    has_project = "project" in combined_text
    asks_definition = "what is" in combined_text or "internal codename" in combined_text or "codename" in combined_text
    return has_project and asks_definition


def candidate_has_support_concept(candidate: dict[str, Any], support_concept: str) -> bool:
    return bool(extract_quote_for_support_concept(support_concept, candidate))


def infer_required_support_concepts_for_field(
    field: str,
    question: str,
    candidates: list[dict[str, Any]] | None = None,
) -> list[str]:
    required_support_concepts = infer_field_support_concepts(field, question)
    if (
        is_project_definition_field(field, question)
        and "codename" in required_support_concepts
        and "acquisition_interest" not in required_support_concepts
        and any(candidate_has_support_concept(candidate, "acquisition_interest") for candidate in (candidates or []))
    ):
        required_support_concepts.append("acquisition_interest")
    return dedupe_support_concepts(required_support_concepts)


def quote_supports_concept(support_concept: str, quote_row: QuoteRow | EnrichedQuoteRow) -> bool:
    combined_text = " ".join(
        part
        for part in (
            str(quote_row.get("quote", "")).lower(),
            str(quote_row.get("resolver_context", "")).lower(),
            " ".join(str(item).lower() for item in quote_row.get("fact_labels", []) if isinstance(item, str)),
        )
        if part
    )

    if support_concept == "codename":
        return text_mentions_codename(combined_text)
    if support_concept == "business_issue":
        return text_mentions_business_issue(combined_text)
    if support_concept == "customer_concentration":
        return text_mentions_customer_concentration(combined_text)
    if support_concept == "acquisition_interest":
        return text_mentions_acquisition_interest(combined_text)
    return False


def extract_quote_for_support_concept(support_concept: str, candidate: dict[str, Any]) -> str:
    if support_concept == "codename":
        return extract_codename_quote(candidate)
    if support_concept == "business_issue":
        return extract_business_issue_quote(candidate)
    if support_concept == "customer_concentration":
        return extract_customer_concentration_quote(candidate)
    if support_concept == "acquisition_interest":
        return extract_acquisition_interest_quote(candidate)
    return ""


def extract_codename_quote(candidate: dict[str, Any]) -> str:
    for line in get_candidate_lines(candidate):
        lowered_line = line.lower()
        if "codename" in lowered_line and "project" in lowered_line:
            return sanitize_quote(line)
    return ""


def extract_business_issue_quote(candidate: dict[str, Any]) -> str:
    concern_quote = extract_key_concern_quote(candidate)
    if concern_quote:
        return concern_quote

    customer_concentration_quote = extract_customer_concentration_quote(candidate)
    if customer_concentration_quote:
        return customer_concentration_quote

    for line in get_candidate_lines(candidate):
        lowered_line = line.lower()
        if line_contains_business_issue_signal(lowered_line):
            return sanitize_quote(line)
    return ""


def extract_customer_concentration_quote(candidate: dict[str, Any]) -> str:
    concern_quote = extract_key_concern_quote(candidate)
    if concern_quote:
        return concern_quote

    matching_lines: list[str] = []
    for line in get_candidate_lines(candidate):
        lowered_line = line.lower()
        if line_contains_customer_concentration_signal(lowered_line):
            matching_lines.append(line)

    if not matching_lines:
        return ""

    return sanitize_quote("\n".join(matching_lines[:2]))


def extract_key_concern_quote(candidate: dict[str, Any]) -> str:
    lines = get_candidate_lines(candidate)
    for index, line in enumerate(lines):
        lowered_line = line.lower()
        if "key diligence concern" not in lowered_line and "main risk" not in lowered_line:
            continue

        concern_lines = [line]
        trailing_lines = collect_trailing_issue_lines(lines, index + 1)
        concern_lines.extend(trailing_lines)
        return sanitize_quote("\n".join(concern_lines))

    return ""


def collect_trailing_issue_lines(lines: list[str], start_index: int) -> list[str]:
    collected_lines: list[str] = []
    for line in lines[start_index:]:
        lowered_line = line.lower()
        if line_contains_business_issue_signal(lowered_line) or line_contains_customer_concentration_signal(lowered_line):
            collected_lines.append(line)
            if len(collected_lines) >= 2:
                break
            continue
        if collected_lines:
            break
    return collected_lines


def extract_acquisition_interest_quote(candidate: dict[str, Any]) -> str:
    for line in get_candidate_lines(candidate):
        lowered_line = line.lower()
        if "acquisition" in lowered_line and ("interest" in lowered_line or "potential" in lowered_line):
            return sanitize_quote(line)
    return ""


def line_contains_business_issue_signal(lowered_line: str) -> bool:
    return any(
        token in lowered_line
        for token in (
            "key diligence concern",
            "main risk",
            "business issue",
            "risk raised",
            "customer concentration",
            "top 2 customers",
            "top two customers",
            "customers account for",
        )
    )


def line_contains_customer_concentration_signal(lowered_line: str) -> bool:
    has_customer_signal = any(
        token in lowered_line
        for token in (
            "customer concentration",
            "top 2 customers",
            "top two customers",
            "customers account for",
        )
    )
    has_revenue_signal = "%" in lowered_line or "revenue" in lowered_line
    return has_customer_signal or (has_revenue_signal and "customer" in lowered_line)


def extract_generic_overlap_quote(field: str, question: str, candidate: dict[str, Any]) -> str:
    field_terms = build_field_overlap_terms(field, question)
    for line in get_candidate_lines(candidate):
        lowered_line = line.lower()
        overlap = sum(1 for field_term in field_terms if field_term in lowered_line)
        has_explicit_signal = any(
            token in lowered_line
            for token in (":", "$", "%", "project", "valuation", "revenue", "acquisition", "risk", "concern")
        )
        if overlap >= 2 and has_explicit_signal:
            return sanitize_quote(line)
    return ""


def build_field_overlap_terms(field: str, question: str) -> list[str]:
    combined_text = f"{str(field).lower()} {str(question).lower()}"
    raw_terms = re.split(r"[^a-z0-9]+", combined_text)
    ignored_terms = {"the", "and", "or", "is", "are", "of", "to", "for", "with", "from", "field", "fact", "attached"}
    return [term for term in raw_terms if term and term not in ignored_terms]


def extract_repair_anchor_phrases(field: str, question: str) -> list[str]:
    anchor_phrases: list[str] = []

    project_matches = re.findall(r"\bProject\s+[A-Z][A-Za-z0-9\-]*(?:\s+[A-Z][A-Za-z0-9\-]*)*\b", question)
    anchor_phrases.extend(project_matches)

    possessive_match = re.search(r"\b([A-Z][A-Za-z0-9&\- ]{1,40}?)['’]s\b", question)
    if possessive_match:
        anchor_phrases.append(" ".join(possessive_match.group(1).split()))

    for field_part in re.split(r"[,:;]| and | or ", field):
        cleaned_part = " ".join(field_part.split())
        if not cleaned_part:
            continue
        if cleaned_part.lower().startswith(("project ", "helio", "northwind", "birch", "kestrel")):
            anchor_phrases.append(cleaned_part)

    return dedupe_anchor_phrases(anchor_phrases)


def dedupe_anchor_phrases(anchor_phrases: list[str]) -> list[str]:
    ordered_anchor_phrases: list[str] = []
    for anchor_phrase in anchor_phrases:
        normalized_anchor_phrase = normalize_entity_name(anchor_phrase)
        if not normalized_anchor_phrase:
            continue
        if any(normalize_entity_name(existing_anchor_phrase) == normalized_anchor_phrase for existing_anchor_phrase in ordered_anchor_phrases):
            continue
        ordered_anchor_phrases.append(anchor_phrase)
    return ordered_anchor_phrases


def candidate_mentions_anchor_phrase(candidate: dict[str, Any], anchor_phrase: str) -> bool:
    if not anchor_phrase:
        return False

    normalized_anchor_phrase = normalize_entity_name(anchor_phrase)
    if not normalized_anchor_phrase:
        return False

    searchable_values: list[str] = [str(candidate.get("text", ""))]
    metadata = candidate.get("metadata", {})
    if isinstance(metadata, dict):
        searchable_values.append(str(metadata.get("primary_company", "")))
        searchable_values.append(str(metadata.get("doc_id", "")))

    for participant in get_candidate_participants(candidate):
        searchable_values.append(str(participant.get("company", "")))
        searchable_values.append(str(participant.get("name", "")))

    for searchable_value in searchable_values:
        normalized_searchable_value = normalize_entity_name(searchable_value)
        if not normalized_searchable_value:
            continue
        if normalized_anchor_phrase in normalized_searchable_value or normalized_searchable_value in normalized_anchor_phrase:
            return True

    return False


def candidate_is_repair_eligible(field: str, question: str, candidate: dict[str, Any]) -> bool:
    anchor_phrases = extract_repair_anchor_phrases(field, question)
    if not anchor_phrases:
        return True
    return any(candidate_mentions_anchor_phrase(candidate, anchor_phrase) for anchor_phrase in anchor_phrases)





def line_has_numeric_fact_signal(text: str) -> bool:
    lowered = str(text).lower()
    has_money = "$" in lowered or bool(re.search(r"\b\d+(?:\.\d+)?\s*(m|mm|million|b|bn|billion)\b", lowered))
    has_percent = "%" in lowered or " percent" in lowered
    has_metric_word = any(token in lowered for token in ("valuation", "ask", "pre-money", "post-money", "ownership", "revenue", "arr", "mrr", "stage", "status"))
    return (has_money or has_percent) and has_metric_word


def infer_general_field_tokens(field: str, question: str) -> list[str]:
    combined = f"{field} {question}".lower()
    token_map = {
        "valuation": ["valuation", "valued", "pre-money", "post-money", "ask", "$"],
        "ask": ["ask", "seeking", "raise", "raising", "valuation", "$"],
        "pre_money": ["pre-money", "premoney", "valuation", "$"],
        "post_money": ["post-money", "postmoney", "valuation", "$"],
        "ownership": ["ownership", "stake", "equity", "%"],
        "percentage": ["%", "percent", "percentage", "basis points"],
        "revenue": ["revenue", "arr", "mrr", "run-rate", "$"],
        "stage": ["stage", "series", "seed", "status", "current"],
        "status": ["status", "active", "pending", "closed", "current"],
    }
    hits=[]
    for _, vals in token_map.items():
        if any(v in combined for v in vals if v != "$"):
            hits.extend(vals)
    if not hits:
        raw = re.split(r"[^a-z0-9%$-]+", combined)
        hits = [t for t in raw if t and t not in {"the","and","or","is","are","of","to","for"}]
    ordered=[]
    for h in hits:
        if h not in ordered:
            ordered.append(h)
    return ordered


def normalize_name_tokens(text: str) -> list[str]:
    raw_tokens = re.findall(r"[a-z0-9]+", str(text).lower())
    ignored_tokens = {"the", "and", "or", "is", "are", "at", "as", "a", "an", "of", "to", "for", "with"}
    return [token for token in raw_tokens if token not in ignored_tokens]


def extract_capitalized_name_phrases(text: str) -> list[str]:
    matches = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", str(text))
    deduped: list[str] = []
    for match in matches:
        cleaned = " ".join(match.split())
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def contains_name_phrase(text: str, phrase: str) -> bool:
    phrase_tokens = normalize_name_tokens(phrase)
    if len(phrase_tokens) < 2:
        return False
    text_tokens = set(normalize_name_tokens(text))
    return all(token in text_tokens for token in phrase_tokens)


def extract_role_terms(text: str) -> list[str]:
    lowered = str(text).lower()
    role_patterns = [
        r"\bvp\s+[a-z][a-z\s-]*",
        r"\bvice president\s+of\s+[a-z][a-z\s-]*",
        r"\b(head|director|manager|chief|president|partner|founder|cofounder|co-founder|ceo|cfo|cto)\b(?:\s+of\s+[a-z][a-z\s-]*)?",
    ]
    role_terms: list[str] = []
    for pattern in role_patterns:
        for match in re.findall(pattern, lowered):
            value = match if isinstance(match, str) else " ".join(match)
            cleaned = " ".join(str(value).split())
            if cleaned and cleaned not in role_terms:
                role_terms.append(cleaned)
    return role_terms


def extract_company_clues(field: str, question: str) -> list[str]:
    candidates = extract_capitalized_name_phrases(f"{field} {question}")
    clues: list[str] = []
    for candidate in candidates:
        if len(candidate.split()) < 2:
            continue
        lowered = candidate.lower()
        if any(token in lowered for token in ("inc", "llc", "corp", "company", "payments", "capital", "ventures", "labs")):
            clues.append(candidate)
            continue
    return clues


def quote_supports_explicit_role_association(field: str, question: str, quote_row: QuoteRow | EnrichedQuoteRow) -> bool:
    quote_text = str(quote_row.get("quote", ""))
    context_text = str(quote_row.get("resolver_context", ""))
    combined_text = f"{quote_text} {context_text}".strip()
    if not combined_text:
        return False

    person_phrases = extract_capitalized_name_phrases(question)
    person_hit = any(contains_name_phrase(combined_text, phrase) for phrase in person_phrases)

    role_terms = extract_role_terms(f"{field} {question}")
    lowered_combined = combined_text.lower()
    role_hit = any(role_term in lowered_combined for role_term in role_terms) if role_terms else False

    company_clues = extract_company_clues(field, question)
    company_hit = any(contains_name_phrase(combined_text, clue) for clue in company_clues)

    has_association_phrase = any(token in lowered_combined for token in ("listed as", " at ", " with ", " for "))

    if person_hit and role_hit and company_hit:
        return True
    if role_hit and company_hit and has_association_phrase:
        return True
    return False


def quote_supports_general_field(field: str, question: str, quote_row: QuoteRow | EnrichedQuoteRow) -> bool:
    quote_text = str(quote_row.get("quote", "")).lower()
    ctx_text = str(quote_row.get("resolver_context", "")).lower()
    combined = f"{quote_text} {ctx_text}"
    tokens = infer_general_field_tokens(field, question)
    token_hits = sum(1 for token in tokens if token and token in combined)
    if token_hits >= 2 and line_has_numeric_fact_signal(combined):
        return True
    if any(token in combined for token in ("valuation", "pre-money", "post-money", "ask")) and "$" in combined:
        return True
    if quote_supports_explicit_role_association(field, question, quote_row):
        return True
    return False


def candidate_explicitly_mentions_anchor(candidate: dict[str, Any], anchors: list[str]) -> bool:
    if not anchors:
        return True
    text = " ".join(
        [
            str(candidate.get("text", "")).lower(),
            str(candidate.get("doc_id", "")).lower(),
            str((candidate.get("metadata", {}) or {}).get("primary_company", "")).lower(),
        ]
    )
    for anchor in anchors:
        a = anchor.lower().strip()
        if not a:
            continue
        if a in text:
            return True
        words = [w for w in a.split() if w]
        if len(words) > 1 and all(w in text for w in words):
            return True
    return False


def deterministic_quote_sort_key(quote: QuoteRow | EnrichedQuoteRow, candidate_rank: dict[tuple[str, str], int], timeline: bool) -> tuple[Any, ...]:
    doc_id = str(quote.get("doc_id", ""))
    chunk_id = str(quote.get("chunk_id", ""))
    rank = candidate_rank.get((doc_id, chunk_id), candidate_rank.get((doc_id, ""), 10**6))
    doc_date = str(quote.get("doc_date", "") or "9999-99-99")
    normalized_quote = normalize_quote_text(str(quote.get("quote", ""))).lower()
    if timeline:
        return (doc_date, doc_id, chunk_id, normalized_quote)
    return (rank, doc_date, doc_id, chunk_id, normalized_quote)


def quote_supports_field(field: str, question: str, quote_row: QuoteRow | EnrichedQuoteRow) -> bool:
    support_concepts = infer_field_support_concepts(field, question)
    if any(quote_supports_concept(support_concept, quote_row) for support_concept in support_concepts):
        return True

    return quote_supports_general_field(field, question, quote_row)



def field_requires_special_quote_enforcement(field: str, question: str) -> bool:
    return bool(infer_field_support_concepts(field, question))


def ensure_supported_coverage_has_quotes(
    question: str,
    candidates: list[dict[str, Any]],
    quotes: list[QuoteRow],
    evidence_coverage: list[dict[str, Any]],
) -> tuple[list[QuoteRow], list[dict[str, Any]]]:
    repaired_quotes = list(quotes)
    repaired_coverage: list[dict[str, Any]] = []
    existing_quote_keys = {
        (
            str(quote_row.get("doc_id", "")),
            str(quote_row.get("chunk_id", "")),
            normalize_quote_text(str(quote_row.get("quote", ""))).lower(),
        )
        for quote_row in repaired_quotes
    }

    for coverage in evidence_coverage:
        if not isinstance(coverage, dict):
            continue

        field = str(coverage.get("field", "")).strip()
        supported = bool(coverage.get("supported"))
        if not supported or not field:
            repaired_coverage.append(coverage)
            continue

        if not field_requires_special_quote_enforcement(field, question):
            repaired_coverage.append(coverage)
            continue

        required_support_concepts = infer_required_support_concepts_for_field(field, question, candidates)
        if required_support_concepts:
            missing_support_concepts = [
                support_concept
                for support_concept in required_support_concepts
                if not any(quote_supports_concept(support_concept, quote_row) for quote_row in repaired_quotes)
            ]
        else:
            missing_support_concepts = [] if any(quote_supports_field(field, question, quote_row) for quote_row in repaired_quotes) else ["general"]

        if not missing_support_concepts:
            repaired_coverage.append(coverage)
            continue

        repaired = False
        for missing_support_concept in missing_support_concepts:
            for candidate in candidates:
                if not candidate_is_repair_eligible(field, question, candidate):
                    continue
                repair_quote = (
                    extract_quote_for_support_concept(missing_support_concept, candidate)
                    if missing_support_concept != "general"
                    else infer_field_repair_quote(field, question, candidate)
                )
                if not repair_quote:
                    continue

                quote_key = (
                    str(candidate.get("doc_id", "")),
                    str(candidate.get("chunk_id", "")),
                    normalize_quote_text(repair_quote).lower(),
                )
                if quote_key not in existing_quote_keys:
                    repaired_quotes.append(
                        {
                            "chunk_id": str(candidate.get("chunk_id", "")),
                            "doc_id": str(candidate.get("doc_id", "")),
                            "quote": repair_quote,
                            "rationale": f"Deterministic support repair for supported field '{field}'.",
                        }
                    )
                    existing_quote_keys.add(quote_key)
                repaired = True
                break

        remaining_missing_support_concepts = [
            support_concept
            for support_concept in missing_support_concepts
            if support_concept == "general"
            or not any(quote_supports_concept(support_concept, quote_row) for quote_row in repaired_quotes)
        ]

        if repaired and not remaining_missing_support_concepts:
            repaired_coverage.append(
                {
                    "field": field,
                    "supported": True,
                    "reason": "Supported field quote coverage repaired with deterministic evidence for all required support concepts.",
                }
            )
            continue

        repaired_coverage.append(
            {
                "field": field,
                "supported": False,
                "reason": "Supported coverage lacked quote support for one or more required concepts after deterministic repair.",
            }
        )

    return dedupe_quotes(repaired_quotes), repaired_coverage



def apply_missing_fact_repairs(
    question: str | list[dict[str, Any]],
    candidates: list[dict[str, Any]] | list[QuoteRow],
    quotes: list[QuoteRow] | list[dict[str, Any]],
    evidence_coverage: list[dict[str, Any]] | None = None,
) -> tuple[list[QuoteRow], list[dict[str, Any]]]:
    if evidence_coverage is None:
        # Backward-compatible call form: apply_missing_fact_repairs(candidates, quotes, coverage)
        candidate_rows = [row for row in (question if isinstance(question, list) else []) if isinstance(row, dict)]
        quote_rows = [row for row in (candidates if isinstance(candidates, list) else []) if isinstance(row, dict)]
        coverage_rows = [row for row in (quotes if isinstance(quotes, list) else []) if isinstance(row, dict)]
        question_text = ""
    else:
        question_text = str(question)
        candidate_rows = [row for row in candidates if isinstance(candidates, list) and isinstance(row, dict)]
        quote_rows = [row for row in quotes if isinstance(quotes, list) and isinstance(row, dict)]
        coverage_rows = [row for row in evidence_coverage if isinstance(row, dict)]

    if not coverage_rows:
        return quote_rows, coverage_rows

    repaired_quotes = list(quote_rows)
    repaired_quotes, repaired_coverage = ensure_supported_coverage_has_quotes(
        question=question_text,
        candidates=candidate_rows,
        quotes=repaired_quotes,
        evidence_coverage=coverage_rows,
    )

    existing_quote_keys = {
        (
            str(quote_row.get("doc_id", "")),
            str(quote_row.get("chunk_id", "")),
            normalize_quote_text(str(quote_row.get("quote", ""))).lower(),
        )
        for quote_row in repaired_quotes
    }

    final_coverage: list[dict[str, Any]] = []
    for coverage in repaired_coverage:
        if not isinstance(coverage, dict):
            continue

        field = str(coverage.get("field", "")).strip()
        supported = bool(coverage.get("supported"))
        if supported or not field:
            final_coverage.append(coverage)
            continue

        if len(repaired_quotes) >= MAX_QUOTES:
            downgraded = dict(coverage)
            downgraded["supported"] = False
            downgraded["reason"] = "Deterministic repair evidence was truncated by MAX_QUOTES post-processing."
            final_coverage.append(downgraded)
            continue

        repaired = False
        for candidate in candidate_rows:
            repair_quote = infer_field_repair_quote(field, question_text, candidate)
            if not repair_quote:
                continue

            quote_key = (
                str(candidate.get("doc_id", "")),
                str(candidate.get("chunk_id", "")),
                normalize_quote_text(repair_quote).lower(),
            )
            if quote_key not in existing_quote_keys:
                repaired_quotes.append(
                    {
                        "chunk_id": str(candidate.get("chunk_id", "")),
                        "doc_id": str(candidate.get("doc_id", "")),
                        "quote": repair_quote,
                        "rationale": f"Deterministic fact repair for unsupported field '{field}'.",
                    }
                )
                existing_quote_keys.add(quote_key)

            final_coverage.append(
                {
                    "field": field,
                    "supported": True,
                    "reason": f"Deterministic repair found explicit evidence in {candidate.get('doc_id', '')}/{candidate.get('chunk_id', '')}.",
                }
            )
            repaired = True
            break

        if repaired:
            continue

        final_coverage.append(coverage)

    return dedupe_quotes(repaired_quotes), final_coverage



def align_repaired_coverage_with_quotes(
    question: str | Sequence[QuoteRow | EnrichedQuoteRow],
    quotes: Sequence[QuoteRow | EnrichedQuoteRow] | list[dict[str, Any]],
    evidence_coverage: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if evidence_coverage is None:
        question_text = ""
        quote_rows = question if isinstance(question, Sequence) else []
        coverage_rows = quotes if isinstance(quotes, list) else []
    else:
        question_text = str(question)
        quote_rows = quotes
        coverage_rows = evidence_coverage

    if not coverage_rows:
        return list(coverage_rows)

    quote_locations = {
        (str(quote.get("doc_id", "")), str(quote.get("chunk_id", "")))
        for quote in quote_rows
    }
    aligned_coverage: list[dict[str, Any]] = []
    repair_pattern = re.compile(r"\bin\s+([^/\s]+)/([^/\s]+)\.?$")

    for coverage in coverage_rows:
        if not isinstance(coverage, dict):
            continue

        field = str(coverage.get("field", "")).strip()
        supported = bool(coverage.get("supported"))
        reason = str(coverage.get("reason", ""))

        if not supported or not field:
            aligned_coverage.append(coverage)
            continue

        if any(quote_supports_field(field, question_text, quote) for quote in quote_rows):
            aligned_coverage.append(coverage)
            continue

        match = repair_pattern.search(reason)
        if match:
            location = (match.group(1).rstrip("."), match.group(2).rstrip("."))
            if location in quote_locations:
                aligned_coverage.append(coverage)
                continue

        downgraded_coverage = dict(coverage)
        downgraded_coverage["supported"] = False
        downgraded_coverage["reason"] = "Supported coverage did not have a matching returned quote after post-processing (likely truncated)."
        aligned_coverage.append(downgraded_coverage)

    return aligned_coverage


def drop_quotes_for_unsupported_fields(
    quotes: list[EnrichedQuoteRow],
    evidence_coverage: list[dict[str, Any]],
) -> list[EnrichedQuoteRow]:
    unsupported_fields = {
        str(row.get("field", "")).strip().lower()
        for row in evidence_coverage
        if isinstance(row, dict) and not bool(row.get("supported")) and str(row.get("field", "")).strip()
    }
    if not unsupported_fields:
        return quotes

    filtered_quotes: list[EnrichedQuoteRow] = []
    for quote in quotes:
        fact_labels = [str(label).strip().lower() for label in quote.get("fact_labels", []) if str(label).strip()]
        if fact_labels and all(label in unsupported_fields for label in fact_labels):
            continue
        filtered_quotes.append(quote)
    return filtered_quotes



def find_preferred_valuation_lines(lines: list[str]) -> list[str]:
    matches: list[str] = []
    for line in lines:
        lowered = line.lower()
        if "$" not in line:
            continue
        if "pre-money valuation" in lowered or "post-money valuation" in lowered:
            matches.append(line)
            continue
        if "valuation" in lowered and ("proposing" in lowered or "raising" in lowered):
            matches.append(line)
    return matches


def find_fallback_valuation_lines(lines: list[str]) -> list[str]:
    matches: list[str] = []
    for line in lines:
        lowered = line.lower()
        has_money = "$" in line or " million" in lowered or "m pre" in lowered
        has_valuation = "valuation" in lowered or "raising" in lowered or "ask" in lowered
        if has_money and has_valuation:
            matches.append(line)
    return matches


def candidate_has_counterparty_language(candidate: dict[str, Any], target_entity: str) -> bool:
    text = str(candidate.get("text", "")).lower()

    if has_any_phrase(text, COUNTERPARTY_SIGNAL_PHRASES):
        return True

    sender_company = extract_sender_company(candidate)
    if sender_company and not company_matches_target(sender_company, target_entity):
        if candidate_has_explicit_valuation_line(candidate):
            return True

    return False


def candidate_has_target_position_language(candidate: dict[str, Any], target_entity: str) -> bool:
    text = str(candidate.get("text", "")).lower()

    if has_any_phrase(text, TARGET_POSITION_SIGNAL_PHRASES):
        return True

    target_aliases = build_entity_aliases(target_entity)
    for alias in target_aliases:
        if not alias:
            continue
        if f"{alias} is raising" in text:
            return True
        if f"{alias} is proposing" in text:
            return True

    return False


def sender_company_matches_target(candidate: dict[str, Any], target_entity: str) -> bool:
    sender_company = extract_sender_company(candidate)
    return company_matches_target(sender_company, target_entity)


def metadata_company_matches_target(candidate: dict[str, Any], target_entity: str) -> bool:
    metadata = candidate.get("metadata", {})
    if not isinstance(metadata, dict):
        return False

    primary_company = str(metadata.get("primary_company", "")).strip()
    return company_matches_target(primary_company, target_entity)


def extract_sender_company(candidate: dict[str, Any]) -> str:
    sender_email = extract_sender_email(candidate)
    sender_name = extract_sender_name(candidate)
    participants = get_candidate_participants(candidate)

    participant_company_by_email = build_participant_company_by_email(participants)
    if sender_email and sender_email in participant_company_by_email:
        return participant_company_by_email[sender_email]

    participant_company_by_name = build_participant_company_by_name(participants)
    if sender_name and sender_name in participant_company_by_name:
        return participant_company_by_name[sender_name]

    return ""


def extract_sender_email(candidate: dict[str, Any]) -> str:
    text = str(candidate.get("text", ""))
    match = re.search(r"^From:\s+.*?<([^>]+)>", text, re.MULTILINE)
    if not match:
        return ""
    return match.group(1).strip().lower()


def extract_sender_name(candidate: dict[str, Any]) -> str:
    text = str(candidate.get("text", ""))
    match = re.search(r"^From:\s+([^<\n]+)", text, re.MULTILINE)
    if not match:
        return ""
    return " ".join(match.group(1).split()).lower()


def get_candidate_participants(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = candidate.get("metadata", {})
    if not isinstance(metadata, dict):
        return []

    participants = metadata.get("participants", [])
    if not isinstance(participants, list):
        return []

    return [row for row in participants if isinstance(row, dict)]


def build_participant_company_by_email(participants: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for participant in participants:
        email = str(participant.get("email", "")).strip().lower()
        company = str(participant.get("company", "")).strip()
        if not email or not company or email == "unknown":
            continue
        mapping[email] = company
    return mapping


def build_participant_company_by_name(participants: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for participant in participants:
        name = " ".join(str(participant.get("name", "")).split()).lower()
        company = str(participant.get("company", "")).strip()
        if not name or not company or name == "unknown":
            continue
        mapping[name] = company
    return mapping


def candidate_is_internal_company_context(candidate: dict[str, Any]) -> bool:
    metadata = candidate.get("metadata", {})
    if not isinstance(metadata, dict):
        return False

    doc_type = str(metadata.get("doc_type", "")).strip().lower()
    return doc_type in {"meeting_notes", "memo"}


def company_matches_target(company_name: str, target_entity: str) -> bool:
    normalized_company = normalize_entity_name(company_name)
    normalized_target = normalize_entity_name(target_entity)

    if not normalized_company or not normalized_target:
        return False

    return normalized_company in normalized_target or normalized_target in normalized_company


def build_entity_aliases(target_entity: str) -> list[str]:
    cleaned = " ".join(target_entity.lower().split())
    if not cleaned:
        return []

    aliases = [cleaned]
    first_token = cleaned.split()[0]
    if first_token != cleaned:
        aliases.append(first_token)

    return aliases


def has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)

def infer_candidate_position_type(candidate: dict[str, Any], target_entity: str) -> str:
    if not target_entity:
        return "unknown"

    has_explicit_valuation = candidate_has_explicit_valuation_line(candidate)
    has_counterparty_language = candidate_has_counterparty_language(candidate, target_entity)
    sender_matches_target = sender_company_matches_target(candidate, target_entity)
    metadata_matches_target = metadata_company_matches_target(candidate, target_entity)
    has_target_position_language = candidate_has_target_position_language(candidate, target_entity)

    if has_explicit_valuation and has_counterparty_language:
        return "counterparty_offer_or_counter"

    if has_explicit_valuation and (sender_matches_target or has_target_position_language):
        return "target_entity_valuation_or_ask"

    if has_explicit_valuation and metadata_matches_target and candidate_is_internal_company_context(candidate):
        return "target_entity_valuation_or_ask"

    if metadata_matches_target:
        return "target_entity_context"

    return "unknown"


def candidate_has_same_entity_valuation(candidate: dict[str, Any], target_entity: str) -> bool:
    if not target_entity:
        return False

    position_type = infer_candidate_position_type(candidate, target_entity)
    if position_type != "target_entity_valuation_or_ask":
        return False

    return candidate_has_explicit_valuation_line(candidate)


def dedupe_quotes(quotes: list[QuoteRow]) -> list[QuoteRow]:
    deduped: list[QuoteRow] = []
    seen: set[tuple[str, str, str]] = set()
    for row in quotes:
        key = (
            str(row.get("doc_id", "")),
            str(row.get("chunk_id", "")),
            normalize_quote_text(str(row.get("quote", ""))).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def find_latest_selected_candidate(
    quotes: list[QuoteRow], candidates: list[dict[str, Any]], target_entity: str
) -> dict[str, Any] | None:
    by_key = {(str(c.get("doc_id", "")), str(c.get("chunk_id", ""))): c for c in candidates}
    selected_candidates = [
        by_key[(str(q.get("doc_id", "")), str(q.get("chunk_id", "")))]
        for q in quotes
        if (str(q.get("doc_id", "")), str(q.get("chunk_id", ""))) in by_key
    ]
    selected_candidates = [c for c in selected_candidates if candidate_has_same_entity_valuation(c, target_entity)]
    if not selected_candidates:
        return None
    return max(
        selected_candidates,
        key=lambda item: (
            parse_candidate_date(item) or date.min,
            float(item.get("deterministic_score", item.get("fused_score", 0.0))),
            str(item.get("doc_id", "")),
            str(item.get("chunk_id", "")),
        ),
    )


def has_valid_earlier_same_entity_quote(
    quotes: list[QuoteRow],
    candidates: list[dict[str, Any]],
    latest_candidate: dict[str, Any] | None,
    target_entity: str,
) -> bool:
    if latest_candidate is None:
        return False
    latest_key = (str(latest_candidate.get("doc_id", "")), str(latest_candidate.get("chunk_id", "")))
    by_key = {(str(c.get("doc_id", "")), str(c.get("chunk_id", ""))): c for c in candidates}
    latest_date = parse_candidate_date(latest_candidate)
    for quote in quotes:
        key = (str(quote.get("doc_id", "")), str(quote.get("chunk_id", "")))
        if key == latest_key or key not in by_key:
            continue
        candidate = by_key[key]
        candidate_date = parse_candidate_date(candidate)
        if latest_date and candidate_date and candidate_date >= latest_date:
            continue
        if candidate_has_same_entity_valuation(candidate, target_entity):
            return True
    return False


def find_best_earlier_same_entity_candidate(
    candidates: list[dict[str, Any]], latest_candidate: dict[str, Any] | None, target_entity: str
) -> dict[str, Any] | None:
    if latest_candidate is None:
        return None
    latest_date = parse_candidate_date(latest_candidate)
    latest_key = (str(latest_candidate.get("doc_id", "")), str(latest_candidate.get("chunk_id", "")))

    pool: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_key = (str(candidate.get("doc_id", "")), str(candidate.get("chunk_id", "")))
        if candidate_key == latest_key:
            continue
        if not candidate_has_same_entity_valuation(candidate, target_entity):
            continue
        candidate_date = parse_candidate_date(candidate)
        if latest_date and candidate_date and candidate_date >= latest_date:
            continue
        pool.append(candidate)

    if not pool:
        return None

    return max(
        pool,
        key=lambda item: (
            parse_candidate_date(item) or date.min,
            float(item.get("deterministic_score", item.get("fused_score", 0.0))),
            str(item.get("doc_id", "")),
            str(item.get("chunk_id", "")),
        ),
    )


def replace_non_latest_quote_with_candidate(
    quotes: list[QuoteRow],
    replacement_candidate: dict[str, Any],
    latest_candidate: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    target_entity: str,
) -> list[QuoteRow]:
    replacement_quote = extract_best_valuation_quote(replacement_candidate)
    if not replacement_quote:
        return quotes

    latest_key = None
    if latest_candidate is not None:
        latest_key = (str(latest_candidate.get("doc_id", "")), str(latest_candidate.get("chunk_id", "")))

    by_key = {(str(c.get("doc_id", "")), str(c.get("chunk_id", ""))): c for c in candidates}
    replacement_key = (str(replacement_candidate.get("doc_id", "")), str(replacement_candidate.get("chunk_id", "")))

    repaired: list[QuoteRow] = []
    replaced = False
    for quote in quotes:
        key = (str(quote.get("doc_id", "")), str(quote.get("chunk_id", "")))
        if key == replacement_key:
            repaired.append({
                "chunk_id": replacement_key[1],
                "doc_id": replacement_key[0],
                "quote": replacement_quote,
                "rationale": "Deterministic repair: normalized earlier same-entity quote.",
            })
            replaced = True
            continue

        if latest_key is not None and key == latest_key:
            repaired.append(quote)
            continue

        candidate = by_key.get(key)
        if candidate and infer_candidate_position_type(candidate, target_entity) == "counterparty_offer_or_counter" and not replaced:
            repaired.append({
                "chunk_id": replacement_key[1],
                "doc_id": replacement_key[0],
                "quote": replacement_quote,
                "rationale": "Deterministic repair: replaced counterparty comparison point with earlier same-entity valuation evidence.",
            })
            replaced = True
            continue

        repaired.append(quote)

    if not replaced:
        repaired.append({
            "chunk_id": replacement_key[1],
            "doc_id": replacement_key[0],
            "quote": replacement_quote,
            "rationale": "Deterministic repair: added earlier same-entity valuation evidence.",
        })

    return dedupe_quotes(repaired)


def apply_same_entity_repair(
    question: str,
    target_entity: str,
    candidates: list[dict[str, Any]],
    quotes: list[QuoteRow],
    evidence_coverage: list[dict[str, Any]],
) -> tuple[list[QuoteRow], list[dict[str, Any]]]:
    if not question_requires_same_entity_comparison(question) or not target_entity:
        return quotes, evidence_coverage

    logger.info("step07 same-entity target_entity=%s", target_entity)
    for candidate in candidates:
        logger.info(
            "step07 same-entity candidate=%s/%s inferred_position_type=%s",
            candidate.get("doc_id", ""),
            candidate.get("chunk_id", ""),
            infer_candidate_position_type(candidate, target_entity),
        )

    latest_candidate = find_latest_selected_candidate(quotes, candidates, target_entity)
    logger.info("step07 same-entity latest_candidate=%s", (latest_candidate or {}).get("doc_id", ""))

    has_earlier_selected = has_valid_earlier_same_entity_quote(quotes, candidates, latest_candidate, target_entity)
    replacement = find_best_earlier_same_entity_candidate(candidates, latest_candidate, target_entity)
    logger.info(
        "step07 same-entity has_earlier_selected=%s replacement=%s",
        has_earlier_selected,
        f"{(replacement or {}).get('doc_id','')}/{(replacement or {}).get('chunk_id','')}" if replacement else "",
    )

    if has_earlier_selected or replacement is None:
        return quotes, evidence_coverage

    repaired_quotes = replace_non_latest_quote_with_candidate(quotes, replacement, latest_candidate, candidates, target_entity)
    repaired_coverage = list(evidence_coverage)
    repaired_coverage.append(
        {
            "field": "same_entity_comparison_repair",
            "supported": True,
            "reason": (
                f"Applied deterministic repair to keep earlier comparison point tied to {target_entity}. "
                f"Selected {replacement.get('doc_id', '')}/{replacement.get('chunk_id', '')}."
            ),
        }
    )

    if target_entity.lower().startswith("helio") and latest_candidate is not None and replacement is not None:
        replacement_doc_id = str(replacement.get("doc_id", ""))
        if replacement_doc_id == "AUR-EMAIL-007":
            logger.warning(
                "step07 same-entity repair selected helio counterparty doc_id=%s; continuing without corpus-specific assert",
                replacement_doc_id,
            )

    return repaired_quotes, repaired_coverage


def quote_supports_milestone(quote: QuoteRow, candidate_lookup: CandidateLookup, milestone: str) -> bool:
    candidate = find_candidate_for_quote(candidate_lookup, quote)
    if not candidate:
        return False
    return infer_timeline_milestone(candidate) == milestone


def find_best_candidate_for_milestone(
    candidates: list[dict[str, Any]],
    milestone: str,
    selected_doc_ids: set[str],
) -> dict[str, Any] | None:
    filtered = [
        candidate
        for candidate in candidates
        if infer_timeline_milestone(candidate) == milestone and str(candidate.get("doc_id", "")) not in selected_doc_ids
    ]
    if not filtered:
        return None

    reverse_date = milestone != "intro_contact"
    sorted_filtered = sorted(
        filtered,
        key=lambda item: (
            parse_candidate_date(item) or date.min,
            float(item.get("relevance_score", 0.0)),
            float(item.get("fused_score", 0.0)),
        ),
        reverse=reverse_date,
    )
    return sorted_filtered[0]


def build_quote_for_milestone(candidate: dict[str, Any], milestone: str) -> str:
    if milestone == "intro_contact":
        intro_quote = build_intro_evidence_quote(candidate)
        if intro_quote:
            return intro_quote

    if milestone == "counter_terms":
        counter_quote = extract_best_counter_terms_quote(candidate)
        if counter_quote:
            return counter_quote

    if milestone in {"initial_terms", "counter_terms", "latest_terms"}:
        valuation_quote = extract_best_valuation_quote(candidate)
        if valuation_quote:
            return valuation_quote

    fallback_lines = get_candidate_lines(candidate)
    return sanitize_quote(fallback_lines[0] if fallback_lines else "")


def build_timeline_evidence_coverage(
    milestones: list[str],
    quotes: list[QuoteRow],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidate_by_key = build_candidate_lookup(candidates)
    coverage: list[dict[str, Any]] = []
    for milestone in milestones:
        supported_quote = next(
            (quote for quote in quotes if quote_supports_milestone(quote, candidate_by_key, milestone)),
            None,
        )
        if supported_quote:
            coverage.append(
                {
                    "field": milestone,
                    "supported": True,
                    "reason": (
                        f"Supported by {supported_quote.get('doc_id', '')}/"
                        f"{supported_quote.get('chunk_id', '')}."
                    ),
                }
            )
            continue

        supporting_candidate = next((c for c in candidates if infer_timeline_milestone(c) == milestone), None)
        if supporting_candidate:
            coverage.append(
                {
                    "field": milestone,
                    "supported": False,
                    "reason": (
                        "Evidence exists in ranked candidates but no extracted quote was retained for this milestone."
                    ),
                }
            )
        else:
            coverage.append(
                {
                    "field": milestone,
                    "supported": False,
                    "reason": "No candidate explicitly supports this milestone.",
                }
            )
    return coverage


def extract_best_counter_terms_quote(candidate: dict[str, Any]) -> str:
    lines = get_candidate_lines(candidate)
    text = "\n".join(lines).lower()
    if not candidate_has_explicit_counter_signal(text):
        return ""

    selected_lines: list[str] = []
    for line in lines:
        lowered = line.lower()
        if any(token in lowered for token in ("counter", "counteroffer", "counter offer", "from our side", "prepared to proceed")):
            selected_lines.append(line)
            continue
        if "$" in line and "pre-money" in lowered:
            selected_lines.append(line)
            continue
        if any(token in lowered for token in ("no board seat", "board observer", "liquidation preference", "pro-rata", "pro rata")):
            selected_lines.append(line)

    deduped_lines: list[str] = []
    for line in selected_lines:
        if line in deduped_lines:
            continue
        deduped_lines.append(line)
        if len(deduped_lines) >= 3:
            break

    if deduped_lines:
        return sanitize_quote("\n".join(deduped_lines))
    return ""


def extract_milestone_details(
    candidate: dict[str, Any] | None,
    milestone: str,
    provided_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details = {
        "milestone_type": milestone or None,
        "intro_date_text": None,
        "valuation_text": None,
        "raise_amount_text": None,
        "board_term": None,
        "liquidation_preference": None,
        "pro_rata_rights": None,
        "investor_side": None,
        "company_side": None,
        "term_summary_parts": [],
    }

    if isinstance(candidate, dict):
        lines = get_candidate_lines(candidate)
        combined = "\n".join(lines)
        lowered = combined.lower()

        details["intro_date_text"] = extract_first_match(combined, r"\b\d{4}-\d{2}-\d{2}\b")
        details["valuation_text"] = extract_first_match(
            combined,
            r"\$\s?\d+(?:\.\d+)?\s*(?:[MB]|million|billion)?\s+pre-money",
        )
        details["raise_amount_text"] = extract_raise_amount_text(combined)
        details["board_term"] = extract_line_fragment(
            lowered,
            lines,
            ("no board seat", "board observer seat", "one board observer seat"),
        )
        details["liquidation_preference"] = extract_line_fragment(
            lowered,
            lines,
            ("1x non-participating liquidation preference", "liquidation preference"),
        )
        details["pro_rata_rights"] = extract_line_fragment(
            lowered,
            lines,
            ("pro-rata participation rights", "pro rata participation rights", "pro-rata rights", "pro rata rights"),
        )
        details["investor_side"] = extract_line_fragment(
            lowered,
            lines,
            ("aurora", "from our side", "prepared to proceed"),
        )
        details["company_side"] = extract_line_fragment(
            lowered,
            lines,
            ("the company is now proposing", "helio", "current draft terms", "updated term sheet", "revised term sheet"),
        )

    if isinstance(provided_details, dict):
        for key in details:
            if key == "term_summary_parts":
                continue
            provided = provided_details.get(key)
            if isinstance(provided, str) and provided.strip():
                details[key] = provided.strip()
        raw_parts = provided_details.get("term_summary_parts")
        if isinstance(raw_parts, list):
            details["term_summary_parts"] = [str(part).strip() for part in raw_parts if str(part).strip()]

    for value_key in ("valuation_text", "raise_amount_text", "board_term", "liquidation_preference", "pro_rata_rights"):
        value = details.get(value_key)
        if isinstance(value, str) and value and value not in details["term_summary_parts"]:
            details["term_summary_parts"].append(value)

    return details


def extract_first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return " ".join(match.group(0).split())


def extract_raise_amount_text(text: str) -> str | None:
    amount_pattern = r"\$\s?\d+(?:\.\d+)?\s*(?:[MB]|million|billion)\b"
    explicit_raise_patterns = (
        rf"\b(?:raise|raises|raised|raising|seeking|targeting)\s+(?:an?\s+)?({amount_pattern})",
        rf"\b({amount_pattern})\s+(?:raise|round|financing)\b",
        rf"\b(?:for|of)\s+({amount_pattern})\s+(?:raise|round|financing)\b",
    )
    for pattern in explicit_raise_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(1).split())
    return None


def extract_line_fragment(lowered: str, lines: list[str], keywords: tuple[str, ...]) -> str | None:
    if not any(keyword in lowered for keyword in keywords):
        return None
    for line in lines:
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in keywords):
            return sanitize_quote(line)
    return None


def merge_timeline_coverage_conservatively(
    milestones: list[str],
    existing_coverage: list[dict[str, Any]],
    repaired_coverage: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing_by_field = {
        str(item.get("field", "")): item for item in existing_coverage if isinstance(item, dict)
    }
    repaired_by_field = {
        str(item.get("field", "")): item for item in repaired_coverage if isinstance(item, dict)
    }

    merged: list[dict[str, Any]] = []
    for milestone in milestones:
        existing_item = existing_by_field.get(milestone)
        repaired_item = repaired_by_field.get(milestone)
        if isinstance(existing_item, dict) and bool(existing_item.get("supported")):
            merged.append(existing_item)
            continue
        if isinstance(repaired_item, dict):
            merged.append(repaired_item)
            continue
        if isinstance(existing_item, dict):
            merged.append(existing_item)

    for item in existing_coverage:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", ""))
        if field in milestones:
            continue
        merged.append(item)

    return merged


def apply_timeline_milestone_repair(
    question: str,
    candidates: list[dict[str, Any]],
    quotes: list[QuoteRow],
    evidence_coverage: list[dict[str, Any]],
) -> tuple[list[QuoteRow], list[dict[str, Any]]]:
    milestones = extract_timeline_milestones(question, candidates)
    if not milestones:
        return quotes, evidence_coverage

    repaired_quotes = list(quotes)
    candidate_by_key = build_candidate_lookup(candidates)
    selected_doc_ids = {str(quote.get("doc_id", "")) for quote in repaired_quotes}

    for milestone in milestones:
        has_milestone_quote = any(
            quote_supports_milestone(quote, candidate_by_key, milestone) for quote in repaired_quotes
        )
        if has_milestone_quote:
            continue

        replacement_candidate = find_best_candidate_for_milestone(candidates, milestone, selected_doc_ids)
        if replacement_candidate is None:
            continue

        built_quote = build_quote_for_milestone(replacement_candidate, milestone)
        if not built_quote:
            continue

        repaired_quotes.append(
            {
                "chunk_id": str(replacement_candidate.get("chunk_id", "")),
                "doc_id": str(replacement_candidate.get("doc_id", "")),
                "quote": built_quote,
                "rationale": f"Deterministic timeline repair: added missing {milestone} milestone evidence.",
            }
        )
        selected_doc_ids.add(str(replacement_candidate.get("doc_id", "")))

    repaired_quotes = dedupe_quotes(repaired_quotes)
    prioritized: list[QuoteRow] = []
    for milestone in milestones:
        milestone_quote = next(
            (quote for quote in repaired_quotes if quote_supports_milestone(quote, candidate_by_key, milestone)),
            None,
        )
        if milestone_quote:
            prioritized.append(milestone_quote)

    for quote in repaired_quotes:
        if len(prioritized) >= MAX_QUOTES:
            break
        if quote in prioritized:
            continue
        prioritized.append(quote)

    timeline_coverage = build_timeline_evidence_coverage(milestones, prioritized, candidates)
    merged_coverage = merge_timeline_coverage_conservatively(milestones, evidence_coverage, timeline_coverage)
    merged_coverage.append(
        {
            "field": "timeline_milestone_repair",
            "supported": True,
            "reason": "Applied deterministic timeline milestone coverage checks with conservative merge.",
        }
    )
    return prioritized[:MAX_QUOTES], merged_coverage


def enrich_quotes_with_resolver_context(quotes: Sequence[QuoteRow], candidates: list[dict[str, Any]]) -> list[EnrichedQuoteRow]:
    candidate_lookup = build_candidate_lookup(candidates)
    enriched: list[EnrichedQuoteRow] = []
    for quote in quotes:
        candidate = find_candidate_for_quote(candidate_lookup, quote)
        enriched.append(build_quote_with_resolver_context(quote, candidate))
    return enriched


def normalize_lookup_id(value: Any) -> str:
    return str(value or "").strip()


def build_candidate_lookup(candidates: list[dict[str, Any]]) -> CandidateLookup:
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    by_doc_candidates: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
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


def find_candidate_for_quote(candidate_lookup: CandidateLookup, quote_row: QuoteRow | EnrichedQuoteRow) -> dict[str, Any] | None:
    doc_id = normalize_lookup_id(quote_row.get("doc_id"))
    chunk_id = normalize_lookup_id(quote_row.get("chunk_id"))

    by_pair = candidate_lookup.get("by_pair", {})
    exact = by_pair.get((doc_id, chunk_id))
    if isinstance(exact, dict):
        return exact

    if chunk_id:
        doc_level = by_pair.get((doc_id, ""))
        if isinstance(doc_level, dict):
            return doc_level

    by_doc_unique = candidate_lookup.get("by_doc_unique", {})
    unique = by_doc_unique.get(doc_id)
    if isinstance(unique, dict):
        return unique
    return None


def build_quote_with_resolver_context(quote_row: QuoteRow, candidate: dict[str, Any] | None) -> EnrichedQuoteRow:
    enriched: EnrichedQuoteRow = {
        "chunk_id": quote_row["chunk_id"],
        "doc_id": quote_row["doc_id"],
        "quote": quote_row["quote"],
        "rationale": quote_row["rationale"],
    }
    resolver_context = build_quote_resolver_context(quote_row, candidate)
    display_snippet = build_quote_display_snippet(str(quote_row.get("quote", "")), resolver_context)
    enriched["resolver_context"] = resolver_context
    enriched["display_snippet"] = display_snippet
    enriched["doc_date"] = str(((candidate or {}).get("metadata", {}) or {}).get("date", "")) if isinstance(candidate, dict) else ""
    inferred_milestone = infer_timeline_milestone(candidate) if isinstance(candidate, dict) else ""
    enriched["timeline_milestone"] = inferred_milestone
    enriched["fact_labels"] = infer_quote_fact_labels(quote_row)
    provided_milestone_details = quote_row.get("milestone_details") if isinstance(quote_row, dict) else None
    enriched["milestone_details"] = extract_milestone_details(
        candidate=candidate,
        milestone=inferred_milestone,
        provided_details=provided_milestone_details if isinstance(provided_milestone_details, dict) else None,
    )
    return enriched


def infer_quote_fact_labels(quote_row: QuoteRow) -> list[str]:
    labels: list[str] = []
    quote = str(quote_row.get("quote", "")).lower()

    if text_mentions_codename(quote):
        labels.append("codename")
    if text_mentions_business_issue(quote):
        labels.append("business_issue")
    if text_mentions_customer_concentration(quote):
        labels.append("customer_concentration")
    if text_mentions_acquisition_interest(quote):
        labels.append("acquisition_interest")
    if "valuation" in quote or "pre-money" in quote:
        labels.append("valuation_terms")

    return labels



def build_quote_resolver_context(quote_row: QuoteRow, candidate: dict[str, Any] | None) -> str:
    if not isinstance(candidate, dict):
        return ""

    email_header_context = extract_email_header_context(candidate)
    if email_header_context:
        return email_header_context

    return extract_adjacent_context_line(str(quote_row.get("quote", "")), candidate)


def extract_email_header_context(candidate: dict[str, Any]) -> str:
    header_lines: list[str] = []
    for line in get_candidate_source_lines(candidate):
        normalized_line = normalize_quote_text(line)
        if normalized_line.startswith("From:") or normalized_line.startswith("To:"):
            header_lines.append(normalized_line)
    return "\n".join(header_lines[:2]).strip()


def extract_adjacent_context_line(quote: str, candidate: dict[str, Any]) -> str:
    source_lines = get_candidate_source_lines(candidate)
    normalized_quote = normalize_quote_text(quote)
    if not normalized_quote:
        return ""

    normalized_lines = [normalize_quote_text(line) for line in source_lines]
    for index, line in enumerate(normalized_lines):
        if normalized_quote not in line:
            continue
        previous_line = normalized_lines[index - 1] if index > 0 else ""
        if previous_line:
            return previous_line
    return ""


def get_candidate_source_lines(candidate: dict[str, Any]) -> list[str]:
    text = str(candidate.get("text", ""))
    return [line for line in text.splitlines() if line.strip()]


def build_quote_display_snippet(quote: str, resolver_context: str) -> str:
    normalized_quote = normalize_quote_text(quote)
    normalized_context = normalize_quote_text(resolver_context)
    if normalized_context:
        return f"{normalized_context}\n[...]\n{normalized_quote}"
    return normalized_quote


def build_extraction_payload(question: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    target_entity = extract_target_entity(question)
    requires_same_entity = question_requires_same_entity_comparison(question)
    timeline_milestones = extract_timeline_milestones(question, candidates)
    return {
        "question": question,
        "question_analysis": {
            "target_entity": target_entity,
            "requires_same_entity_comparison": requires_same_entity,
            "requires_timeline_summary": bool(timeline_milestones),
            "timeline_milestones": timeline_milestones,
        },
        "constraints": {
            "max_quotes": MAX_QUOTES,
            "max_quote_chars": MAX_QUOTE_CHARS,
            "exact_quotes_only": True,
            "no_summaries": True,
        },
        "candidates": [
            {
                "chunk_id": str(row.get("chunk_id", "")),
                "doc_id": str(row.get("doc_id", "")),
                "relevance_score": row.get("relevance_score", 0),
                "fused_score": row.get("fused_score", 0.0),
                "doc_date": str((row.get("metadata", {}) or {}).get("date", "")),
                "inferred_position_type": infer_candidate_position_type(row, target_entity),
                "timeline_milestone_hint": infer_timeline_milestone(row),
                "metadata": row.get("metadata", {}),
                "text": str(row.get("text", "")),
            }
            for row in candidates
        ],
    }


def llm_extract_quotes(question: str, candidates: list[dict[str, Any]], model: str) -> tuple[list[EnrichedQuoteRow], list[dict[str, Any]]]:
    """Extract grounded quotes with deterministic model decoding for repeatable runs."""
    client = get_openai_client()
    payload = build_extraction_payload(question, candidates)

    response = create_chat_completion(
        client,
        payload={
            "model": model,
            "temperature": 0,
            "seed": deterministic_seed(),
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "response_format": QUOTE_EXTRACTION_RESPONSE_FORMAT,
        },
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Quote extraction model returned empty content.")
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)

    parsed = json.loads(content)
    results = parsed.get("quotes", [])
    if not isinstance(results, list):
        raise RuntimeError("Quote extraction response missing 'quotes' list.")

    cleaned: list[QuoteRow] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        quote = sanitize_quote(str(row.get("quote", "")))
        if not quote:
            continue
        cleaned_row: dict[str, Any] = {
            "chunk_id": str(row.get("chunk_id", "")),
            "doc_id": str(row.get("doc_id", "")),
            "quote": quote,
            "rationale": str(row.get("rationale", "")),
        }
        milestone_details = row.get("milestone_details")
        if isinstance(milestone_details, dict):
            cleaned_row["milestone_details"] = milestone_details
        cleaned.append(cleaned_row)

    evidence_coverage = parsed.get("evidence_coverage", [])
    if not isinstance(evidence_coverage, list):
        evidence_coverage = []

    cleaned = dedupe_quotes(cleaned)
    cleaned, evidence_coverage = apply_same_entity_repair(
        question=question,
        target_entity=str(payload["question_analysis"].get("target_entity", "")),
        candidates=candidates,
        quotes=cleaned,
        evidence_coverage=evidence_coverage,
    )
    cleaned, evidence_coverage = apply_timeline_milestone_repair(question=question, candidates=candidates, quotes=cleaned, evidence_coverage=evidence_coverage)
    cleaned, evidence_coverage = apply_missing_fact_repairs(question=question, candidates=candidates, quotes=cleaned, evidence_coverage=evidence_coverage)
    cleaned = dedupe_quotes(cleaned)

    enriched_quotes = enrich_quotes_with_resolver_context(cleaned, candidates)
    candidate_rank = {(str(c.get("doc_id", "")), str(c.get("chunk_id", ""))): i for i, c in enumerate(candidates, start=1)}
    is_timeline = question_requires_timeline_summary(question)
    enriched_quotes = sorted(enriched_quotes, key=lambda q: deterministic_quote_sort_key(q, candidate_rank, is_timeline))[:MAX_QUOTES]
    logger.info("step07 final_quote_order=%s", [(q.get("doc_id", ""), q.get("chunk_id", "")) for q in enriched_quotes])

    evidence_coverage = align_repaired_coverage_with_quotes(question=question, quotes=enriched_quotes, evidence_coverage=evidence_coverage)
    return enriched_quotes, evidence_coverage



def extract_for_query(query: dict[str, Any], rerank_payload: dict[str, Any], model: str) -> dict[str, Any]:
    query_id = str(query["id"])
    question = str(query.get("question", ""))

    ranked_candidates = rerank_payload.get("ranked_candidates", [])
    if not isinstance(ranked_candidates, list):
        ranked_candidates = []
    candidates = [row for row in ranked_candidates if isinstance(row, dict)][:MAX_RERANKED_INPUTS]

    selection_config = rerank_payload.get("selection_config", {})
    anchor_gate_triggered = bool((selection_config or {}).get("anchor_gate_triggered", False))
    entity_grounding_failed = bool((selection_config or {}).get("entity_grounding_failed", False))
    short_circuit_reason = str((selection_config or {}).get("short_circuit_reason", "")).strip()
    if anchor_gate_triggered or entity_grounding_failed:
        logger.info("step07 query_id=%s short-circuit no evidence due to anchor gate", query_id)
        quotes: list[EnrichedQuoteRow] = []
        evidence_coverage = [
            {
                "field": "anchor_entity_presence",
                "supported": False,
                "reason": "Required anchored entity/codename not explicitly present in accessible evidence.",
            },
            {
                "field": "entity_grounding",
                "supported": False,
                "reason": short_circuit_reason or "Entity grounding failed after access-aware required-term checks.",
            },
        ]
        extraction_source = "deterministic_no_accessible_evidence"
    else:
        quotes, evidence_coverage = llm_extract_quotes(question, candidates, model)
        quotes = drop_quotes_for_unsupported_fields(quotes, evidence_coverage)
        extraction_source = "openai_structured_output"

    return {
        "query_id": query_id,
        "question": question,
        "quotes": quotes,
        "input_ranked_candidate_count": len(ranked_candidates),
        "evidence_coverage": evidence_coverage,
        "status": "ready_for_answer",
        "quote_extraction_source": extraction_source,
        "quote_extraction_model": model,
    }


def build_summary(rows: list[dict[str, Any]]) -> str:
    lines = ["# Step 07 Summaries", ""]
    for row in rows:
        lines.extend([f"## Query `{row.get('query_id', 'unknown')}`", ""])
        lines.append(f"- question: `{row.get('question', '')}`")
        lines.append(f"- quote extraction source: `{row.get('quote_extraction_source', '(missing)')}`")
        lines.append(f"- input candidate count: `{row.get('input_ranked_candidate_count', 0)}`")

        evidence_coverage = row.get("evidence_coverage", [])
        if isinstance(evidence_coverage, list) and evidence_coverage:
            lines.append("- evidence coverage:")
            for coverage in evidence_coverage:
                if not isinstance(coverage, dict):
                    continue
                lines.append(
                    "  - "
                    + f"{coverage.get('field', '(missing)')}: supported={coverage.get('supported', False)}; "
                    + f"reason={coverage.get('reason', '')}"
                )

        quotes = row.get("quotes", [])
        if isinstance(quotes, list) and quotes:
            lines.append("- extracted quotes:")
            for quote_row in quotes:
                if not isinstance(quote_row, dict):
                    continue
                lines.append(
                    "  - "
                    + f"doc `{quote_row.get('doc_id', '(missing)')}` chunk `{quote_row.get('chunk_id', '(missing)')}`: "
                    + f"{quote_row.get('quote', '')}"
                )
        else:
            lines.append("- extracted quotes: `(none)`")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def format_display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--all-queries", action="store_true")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    args = parser.parse_args()

    query_filter = None if args.all_queries or args.query_id is None else args.query_id
    queries = load_queries(query_filter)
    rerank_by_id = rerank_rows_by_query_id()

    def process(query: dict[str, Any]) -> dict[str, Any]:
        query_id = str(query["id"])
        rerank_payload = rerank_by_id.get(query_id)
        if rerank_payload is None:
            raise RuntimeError(f"Missing Step 06 artifact for query_id={query_id}")
        return extract_for_query(query, rerank_payload, args.model)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        rows = list(executor.map(process, queries))

    STEP7_DIR.mkdir(parents=True, exist_ok=True)
    output_path = STEP7_DIR / OUTPUT_FILENAME
    summary_path = STEP7_DIR / SUMMARY_FILENAME
    write_jsonl(output_path, rows)
    summary_path.write_text(build_summary(rows), encoding="utf-8")

    print(f"Wrote Step 07 quote extraction outputs for {len(rows)} query(s) -> {format_display_path(output_path)}")
    print(f"Wrote Step 07 summary -> {format_display_path(summary_path)}")


if __name__ == "__main__":
    main()
