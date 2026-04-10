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
from shared.paths import EXTRACTIONS_PATH, ROOT, UNSTRUCTURED_DIR

UNKNOWN_STRING = "unknown"
SENSITIVITY_ENUM_VALUES = ["public", "internal", "confidential", "restricted", UNKNOWN_STRING]
DOC_TYPE_ENUM_VALUES = [
    "email",
    "meeting_notes",
    "contract",
    "report",
    "memo",
    "internal_memo",
    "chat_log",
    "policy",
    "invoice",
    "proposal",
    "deal_note",
    "other",
    UNKNOWN_STRING,
]

METADATA_RESPONSE_FORMAT: "ResponseFormatJSONSchema" = {
    "type": "json_schema",
    "json_schema": {
        "name": "document_metadata",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "doc_id",
                "tenant_id",
                "sensitivity",
                "doc_type",
                "date",
                "primary_company",
                "participants",
            ],
            "properties": {
                "doc_id": {"type": "string"},
                "tenant_id": {"type": "string"},
                "sensitivity": {"type": "string", "enum": SENSITIVITY_ENUM_VALUES},
                "doc_type": {"type": "string", "enum": DOC_TYPE_ENUM_VALUES},
                "date": {"type": "string"},
                "primary_company": {"type": "string"},
                "participants": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "email", "company", "role"],
                        "properties": {
                            "name": {"type": "string"},
                            "email": {"type": "string"},
                            "company": {"type": "string"},
                            "role": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}

REQUIRED_METADATA_KEYS = {
    "doc_id",
    "tenant_id",
    "sensitivity",
    "doc_type",
    "date",
    "primary_company",
    "participants",
}

METADATA_SYSTEM_PROMPT = f"""
You extract document metadata into the exact JSON shape required by the schema.

Hard rules:
- Use ONLY evidence in the provided document text and the provided [METADATA] block (if any).
- Do NOT guess. If a value is not explicitly supported, output "{UNKNOWN_STRING}".
- Output MUST match the JSON schema exactly. No extra keys, no explanations.

Field rules:
- doc_id: Prefer [METADATA] doc_id. Else "{UNKNOWN_STRING}".
- tenant_id: Prefer [METADATA] tenant_id. Else "{UNKNOWN_STRING}".
- sensitivity: one of {SENSITIVITY_ENUM_VALUES}.
- doc_type: one of {DOC_TYPE_ENUM_VALUES}.
- date: ISO YYYY-MM-DD if explicitly present; otherwise "{UNKNOWN_STRING}".
- primary_company: the main company being discussed (often the target company) if explicitly named; else "{UNKNOWN_STRING}".
- participants: include people explicitly listed in headers (From/To/Cc) and/or clearly named in the text.
  - name: required string
  - email: required string (or "{UNKNOWN_STRING}" if not present)
  - company: required string (only if explicitly stated in the document text or trusted [METADATA] block; do NOT infer company from email domain alone; else "{UNKNOWN_STRING}")
  - role: required string (explicit title/role if present; else "{UNKNOWN_STRING}"; document owner, author, etc. does not indicate role)
""".strip()


def parse_metadata_block(document_text: str) -> dict[str, str]:
    match = re.search(r"\[METADATA\](.*?)\[/METADATA\]", document_text, re.DOTALL)
    if not match:
        return {}

    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        clean_line = line.strip()
        if not clean_line or "=" not in clean_line:
            continue
        key, value = clean_line.split("=", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def remove_metadata_block(document_text: str) -> str:
    metadata_pattern = r"\[METADATA\].*?\[/METADATA\]\n?"
    if not re.search(metadata_pattern, document_text, flags=re.DOTALL):
        return document_text

    text_without_metadata = re.sub(metadata_pattern, "", document_text, flags=re.DOTALL)
    return text_without_metadata.lstrip("\n")


def build_metadata_user_prompt(relative_path: str, metadata_block: dict[str, str], document_text: str) -> str:
    metadata_block_json = json.dumps(metadata_block or {}, ensure_ascii=False, indent=2)
    return f"""Source file:
{relative_path}

Parsed [METADATA] block (trusted hints; may be empty):
{metadata_block_json}

Document text:
<<<BEGIN DOCUMENT>>>
{document_text}
<<<END DOCUMENT>>>

Return the metadata JSON now.
"""


def normalize_metadata_values(metadata: dict) -> dict:
    normalized = {
        key: metadata.get(key)
        for key in REQUIRED_METADATA_KEYS
    }
    normalized["doc_id"] = normalize_required_string(normalized.get("doc_id"))
    normalized["tenant_id"] = normalize_required_string(normalized.get("tenant_id"))
    normalized["primary_company"] = normalize_required_string(normalized.get("primary_company"))
    normalized["sensitivity"] = normalize_enum(normalized.get("sensitivity"), SENSITIVITY_ENUM_VALUES)
    normalized["doc_type"] = normalize_enum(normalized.get("doc_type"), DOC_TYPE_ENUM_VALUES)
    normalized["date"] = normalize_date_string(normalized.get("date"))
    normalized["participants"] = normalize_participants(normalized.get("participants"))
    return normalized


def normalize_required_string(value: object) -> str:
    text = str(value or "").strip()
    return text if text else UNKNOWN_STRING


def normalize_enum(value: object, allowed_values: list[str]) -> str:
    text = str(value or "").strip()
    return text if text in allowed_values else UNKNOWN_STRING


def normalize_date_string(value: object) -> str:
    text = str(value or "").strip()
    if text == UNKNOWN_STRING:
        return UNKNOWN_STRING
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    return UNKNOWN_STRING


def normalize_participants(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    participants: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        participants.append(
            {
                "name": normalize_required_string(item.get("name")),
                "email": normalize_required_string(item.get("email")),
                "company": normalize_required_string(item.get("company")),
                "role": normalize_required_string(item.get("role")),
            }
        )
    return participants


def extract_document_metadata_via_llm(
    relative_path: str,
    metadata_block: dict[str, str],
    document_text: str,
    llm_client=None,
) -> dict:
    """Extract metadata with deterministic decoding and normalize to the required schema."""
    client = llm_client or get_openai_client()
    user_prompt = build_metadata_user_prompt(relative_path, metadata_block, document_text)

    response = create_chat_completion(
        client,
        payload={
            "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            "temperature": 0,
            "seed": deterministic_seed(),
            "messages": [
                {"role": "system", "content": METADATA_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": METADATA_RESPONSE_FORMAT,
        },
    )
    content_text = response.choices[0].message.content
    if not content_text:
        raise RuntimeError(f"Model returned no content for {relative_path}.")
    if isinstance(content_text, list):
        content_text = "".join(part.get("text", "") for part in content_text if isinstance(part, dict))

    normalized_metadata = normalize_metadata_values(json.loads(content_text))

    trusted_doc_id = metadata_block.get("doc_id")
    if trusted_doc_id:
        normalized_metadata["doc_id"] = normalize_required_string(trusted_doc_id)

    trusted_tenant_id = metadata_block.get("tenant_id")
    if trusted_tenant_id:
        normalized_metadata["tenant_id"] = normalize_required_string(trusted_tenant_id)

    return normalized_metadata


def format_metadata_summary(metadata: dict) -> str:
    participants = metadata.get("participants")
    participant_count = len(participants) if isinstance(participants, list) else 0
    summary_parts = [
        f"doc_id={metadata.get('doc_id', UNKNOWN_STRING)}",
        f"tenant_id={metadata.get('tenant_id', UNKNOWN_STRING)}",
        f"sensitivity={metadata.get('sensitivity', UNKNOWN_STRING)}",
        f"doc_type={metadata.get('doc_type', UNKNOWN_STRING)}",
        f"date={metadata.get('date', UNKNOWN_STRING)}",
        f"primary_company={metadata.get('primary_company', UNKNOWN_STRING)}",
        f"participants={participant_count}",
    ]
    return ", ".join(summary_parts)


def process_single_document(path: Path, llm_caller=extract_document_metadata_via_llm) -> tuple[dict, list[str]]:
    document_text = path.read_text(encoding="utf-8")
    summary_lines = [f"## {path.name}", f"- processing source file `{path.name}`"]

    metadata_block = parse_metadata_block(document_text)
    summary_lines.append(
        "- detected in-document metadata tags in the source document"
        if metadata_block
        else "- no in-document metadata tags were detected"
    )

    cleaned_text = remove_metadata_block(document_text)
    cleaned_docs_dir = EXTRACTIONS_PATH.parent / "cleaned_documents"
    cleaned_path = cleaned_docs_dir / path.name
    cleaned_path.write_text(cleaned_text, encoding="utf-8")
    cleaned_path_display = cleaned_path.relative_to(ROOT).as_posix()
    summary_lines.append(
        f"- removed explicit `[METADATA]...[/METADATA]` tags and saved a cleaned copy to `{cleaned_path_display}` for vector-store ingestion"
    )

    summary_lines.append("- sent the document text to the OpenAI LLM to extract structured metadata")
    metadata = normalize_metadata_values(llm_caller(path.name, metadata_block, document_text))

    summary_lines.append(f"- extracted metadata: {format_metadata_summary(metadata)}")
    summary_lines.append(f"- appended one extraction record to `{EXTRACTIONS_PATH.relative_to(ROOT).as_posix()}`")
    summary_lines.append("")
    return metadata, summary_lines


def extract_all_metadata(llm_caller=extract_document_metadata_via_llm) -> tuple[list[dict], list[str]]:
    summary_lines = ["# Step 01 Summary", ""]
    source_paths = sorted(UNSTRUCTURED_DIR.glob("*.txt")) + sorted(UNSTRUCTURED_DIR.glob("*.md"))
    cleaned_docs_dir = EXTRACTIONS_PATH.parent / "cleaned_documents"
    cleaned_docs_dir.mkdir(parents=True, exist_ok=True)
    for existing_cleaned_path in sorted(cleaned_docs_dir.glob("*")):
        if existing_cleaned_path.is_file():
            existing_cleaned_path.unlink()

    rows: list[dict] = []
    max_workers = min(32, max(1, len(source_paths)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_single_document, source_paths, [llm_caller] * len(source_paths)))

    for metadata, document_summary_lines in results:
        rows.append(metadata)
        summary_lines.extend(document_summary_lines)

    rows = sorted(rows, key=lambda row: str(row.get("doc_id", "")))
    summary_lines.extend(build_eval_section(rows))
    return rows, summary_lines


def build_eval_section(rows: list[dict]) -> list[str]:
    eval_lines = ["## Eval", ""]
    expected_path = ROOT / "data" / "evals" / "expected_metadata.json"
    if not expected_path.exists():
        eval_lines.append(f"- skipped: expected metadata file not found at `{expected_path.relative_to(ROOT).as_posix()}`")
        eval_lines.append("")
        return eval_lines

    expected_rows = json.loads(expected_path.read_text(encoding="utf-8"))
    normalized_expected_rows = [normalize_metadata_values(row) for row in expected_rows if isinstance(row, dict)]
    expected_rows_by_doc_id = group_rows_by_doc_id(normalized_expected_rows)
    actual_rows_by_doc_id = group_rows_by_doc_id(rows)

    mismatches: list[tuple[str, list[str]]] = []
    for doc_id in sorted(set(expected_rows_by_doc_id.keys()) | set(actual_rows_by_doc_id.keys())):
        failed_aspects = collect_failed_aspects_for_doc_id(
            expected_rows_by_doc_id.get(doc_id, []),
            actual_rows_by_doc_id.get(doc_id, []),
        )
        if failed_aspects:
            mismatches.append((doc_id, failed_aspects))

    if mismatches:
        failed_aspect_count = sum(len(failed_aspects) for _doc_id, failed_aspects in mismatches)
        eval_lines.append(
            f"- metadata comparison failed against `data/evals/expected_metadata.json` with `{failed_aspect_count}` failed aspects across `{len(mismatches)}` docs"
        )
        mismatch_report: dict[str, Any] = {
            "status": "failed",
            "expected_file": "data/evals/expected_metadata.json",
            "failed_aspect_count": failed_aspect_count,
            "failed_doc_count": len(mismatches),
            "docs": [],
        }
        for doc_id, failed_aspects in mismatches:
            eval_lines.append(f"  - doc_id `{doc_id}` failed aspects (`{len(failed_aspects)}`): {', '.join(failed_aspects)}")
            expected_rows_for_doc = expected_rows_by_doc_id.get(doc_id, [])
            actual_rows_for_doc = actual_rows_by_doc_id.get(doc_id, [])
            max_len = max(len(expected_rows_for_doc), len(actual_rows_for_doc), 1)
            doc_report: dict[str, Any] = {
                "doc_id": doc_id,
                "failed_aspects": [],
            }
            unindexed_failed_aspects = [aspect for aspect in failed_aspects if extract_failed_aspect_row_index(aspect) is None]
            for failed_aspect in unindexed_failed_aspects:
                expected_value = expected_rows_for_doc if expected_rows_for_doc else None
                actual_value = actual_rows_for_doc if actual_rows_for_doc else None
                doc_report["failed_aspects"].append(
                    {
                        "aspect": failed_aspect,
                        "mismatch": summarize_mismatch(expected_value, actual_value, failed_aspect),
                    }
                )
            for index in range(max_len):
                expected_row = expected_rows_for_doc[index] if index < len(expected_rows_for_doc) else None
                actual_row = actual_rows_for_doc[index] if index < len(actual_rows_for_doc) else None
                failed_aspects_for_index = [
                    strip_failed_aspect_index(aspect)
                    for aspect in failed_aspects
                    if extract_failed_aspect_row_index(aspect) == index
                ]
                for failed_aspect in failed_aspects_for_index:
                    expected_value, actual_value = get_failed_aspect_values(expected_row, actual_row, failed_aspect)
                    doc_report["failed_aspects"].append(
                        {
                            "aspect": f"{failed_aspect}[{index}]",
                            "mismatch": summarize_mismatch(expected_value, actual_value, failed_aspect),
                        }
                    )
            mismatch_report["docs"].append(doc_report)
        eval_lines.append("```json")
        eval_lines.extend(json.dumps(mismatch_report, ensure_ascii=False, indent=2, sort_keys=True).splitlines())
        eval_lines.append("```")
    else:
        eval_lines.append("- metadata comparison matched `data/evals/expected_metadata.json`")
        match_report = {
            "status": "matched",
            "expected_file": "data/evals/expected_metadata.json",
        }
        eval_lines.append("```json")
        eval_lines.extend(json.dumps(match_report, ensure_ascii=False, indent=2, sort_keys=True).splitlines())
        eval_lines.append("```")
    eval_lines.append("")
    return eval_lines


def group_rows_by_doc_id(rows: list[dict]) -> dict[str, list[dict]]:
    grouped_rows: dict[str, list[dict]] = {}
    for row in rows:
        doc_id = str(row.get("doc_id", "")).strip()
        grouped_rows.setdefault(doc_id, []).append(row)
    return grouped_rows


def collect_failed_aspects(expected_row: dict | None, actual_row: dict | None) -> list[str]:
    if expected_row is None and actual_row is None:
        return []
    if expected_row is None:
        return ["unexpected_doc_in_output"]
    if actual_row is None:
        return ["missing_doc_in_output"]

    failed_aspects: list[str] = []
    for key in sorted(REQUIRED_METADATA_KEYS):
        if expected_row.get(key) != actual_row.get(key):
            failed_aspects.append(key)
    return failed_aspects


def collect_failed_aspects_for_doc_id(expected_rows: list[dict], actual_rows: list[dict]) -> list[str]:
    failed_aspects: list[str] = []

    if len(expected_rows) > 1:
        failed_aspects.append("duplicate_doc_id_in_expected")
    if len(actual_rows) > 1:
        failed_aspects.append("duplicate_doc_id_in_output")

    max_len = max(len(expected_rows), len(actual_rows))
    for index in range(max_len):
        expected_row = expected_rows[index] if index < len(expected_rows) else None
        actual_row = actual_rows[index] if index < len(actual_rows) else None
        for aspect in collect_failed_aspects(expected_row, actual_row):
            failed_aspects.append(f"{aspect}[{index}]")

    return failed_aspects


def format_eval_row(row: dict | None) -> str:
    if row is None:
        return "null"
    return json.dumps(row, ensure_ascii=False, sort_keys=True)


def extract_failed_aspect_row_index(failed_aspect: str) -> int | None:
    if not failed_aspect.endswith("]") or "[" not in failed_aspect:
        return None
    _, _, suffix = failed_aspect.rpartition("[")
    raw_index = suffix[:-1]
    if not raw_index.isdigit():
        return None
    return int(raw_index)


def strip_failed_aspect_index(failed_aspect: str) -> str:
    row_index = extract_failed_aspect_row_index(failed_aspect)
    if row_index is None:
        return failed_aspect
    return failed_aspect.rsplit("[", 1)[0]


def get_failed_aspect_values(expected_row: dict | None, actual_row: dict | None, failed_aspect: str) -> tuple[Any, Any]:
    if failed_aspect == "unexpected_doc_in_output":
        return None, actual_row
    if failed_aspect == "missing_doc_in_output":
        return expected_row, None
    if failed_aspect == "duplicate_doc_id_in_expected":
        return expected_row, actual_row
    if failed_aspect == "duplicate_doc_id_in_output":
        return expected_row, actual_row

    expected_value = expected_row.get(failed_aspect) if isinstance(expected_row, dict) else None
    actual_value = actual_row.get(failed_aspect) if isinstance(actual_row, dict) else None
    return expected_value, actual_value


def summarize_mismatch(expected_value: Any, actual_value: Any, failed_aspect: str) -> dict[str, Any]:
    if failed_aspect == "participants" and isinstance(expected_value, list) and isinstance(actual_value, list):
        participant_mismatches: list[dict[str, Any]] = []
        max_len = max(len(expected_value), len(actual_value))
        for participant_index in range(max_len):
            expected_participant = expected_value[participant_index] if participant_index < len(expected_value) else None
            actual_participant = actual_value[participant_index] if participant_index < len(actual_value) else None
            if expected_participant != actual_participant:
                participant_mismatches.append(
                    {
                        "participant_index": participant_index,
                        "expected": expected_participant,
                        "generated": actual_participant,
                    }
                )
        return {"participant_mismatches": participant_mismatches}

    return {
        "expected": expected_value,
        "generated": actual_value,
    }


def main() -> None:
    load_dotenv(ROOT / ".env")
    rows, summary_lines = extract_all_metadata()

    EXTRACTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EXTRACTIONS_PATH.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary_path = EXTRACTIONS_PATH.parent / "01-extract-metadata-summary.md"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote {len(rows)} extraction rows -> {EXTRACTIONS_PATH}")
    print(f"Wrote summary -> {summary_path}")


if __name__ == "__main__":
    main()
