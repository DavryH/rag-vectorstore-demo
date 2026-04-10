import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.io_utils import read_jsonl, write_json
from shared.openai_client import get_openai_client
from shared.paths import EXTRACTIONS_PATH, ROOT, STEP2_DIR, UNSTRUCTURED_DIR, VECTOR_STORE_MANIFEST_PATH

SUPPORTED_SUFFIXES = {".txt", ".md", ".pdf", ".html"}
UNKNOWN_STRING = "unknown"
CHUNK_SIZE_TOKENS = 450
CHUNK_OVERLAP_TOKENS = 75
DETERMINISTIC_CREATED_AT_ENV = "RAG_DETERMINISTIC_CREATED_AT"


def main() -> None:
    """Build the vector store index manifest and upload corpus files deterministically."""
    vector_store_id = os.getenv("RAG_VECTOR_STORE_ID")
    vector_store_name = os.getenv("RAG_VECTOR_STORE_NAME", "rag-demo")
    file_purpose = os.getenv("RAG_VECTOR_FILE_PURPOSE", "assistants")
    max_files_per_batch = int(os.getenv("RAG_VECTOR_MAX_FILES_PER_BATCH", "100"))
    skip_files_without_metadata = env_flag("RAG_VECTOR_SKIP_FILES_WITHOUT_METADATA", default=True)
    summary_lines = ["# Step 02 Summary", ""]

    records = read_jsonl(EXTRACTIONS_PATH)
    doc_id_to_metadata = {
        str(record.get("doc_id", "")).strip(): record for record in records if str(record.get("doc_id", "")).strip()
    }

    cleaned_docs_dir = EXTRACTIONS_PATH.parent / "cleaned_documents"
    documents_dir = cleaned_docs_dir if cleaned_docs_dir.exists() else UNSTRUCTURED_DIR

    client = get_openai_client()

    vector_store = resolve_target_vector_store(
        client=client,
        vector_store_id=vector_store_id,
        vector_store_name=vector_store_name,
    )
    summary_lines.append(f"- target vector store: `{vector_store.name}`")
    summary_lines.append(
        "- explicit chunking strategy: 450-token chunks with 75-token overlap"
    )

    # Demo-specific choice: always reset the target vector store so each run re-indexes a fresh corpus.
    # Keep this behavior deterministic for the walkthrough; do not treat it as production guidance.
    clear_result = clear_vector_store(
        client=client,
        vector_store_id=vector_store.id,
    )
    summary_lines.extend(format_clear_summary(clear_result))

    uploaded_file_count = upload_folder_to_vector_store(
        client=client,
        vector_store_id=vector_store.id,
        documents_dir=documents_dir,
        doc_id_to_metadata=doc_id_to_metadata,
        file_purpose=file_purpose,
        max_files_per_batch=max_files_per_batch,
        skip_files_without_metadata=skip_files_without_metadata,
    )
    summary_lines.append(f"- uploaded `{uploaded_file_count}` files from `{to_posix_relative(documents_dir)}`")

    manifest = {
        "vector_store_id": vector_store.id,
        "vector_store_name": vector_store.name,
        "documents_dir": to_posix_relative(documents_dir),
        "metadata_source": to_posix_relative(EXTRACTIONS_PATH),
        "source_doc_count": len(doc_id_to_metadata),
        "cleared_file_count": clear_result["deleted_from_storage_count"],
        "uploaded_file_count": uploaded_file_count,
        "created_at": deterministic_created_at(vector_store),
    }

    write_json(VECTOR_STORE_MANIFEST_PATH, manifest)
    summary_path = STEP2_DIR / "02-build-vector-store-summary.md"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print(f"Wrote manifest -> {VECTOR_STORE_MANIFEST_PATH}")
    print(f"Wrote summary -> {summary_path}")


def resolve_target_vector_store(client: Any, vector_store_id: str | None, vector_store_name: str):
    """Resolve the vector store to index into, creating it only when missing."""
    if vector_store_id:
        return client.vector_stores.retrieve(vector_store_id=vector_store_id)

    match = find_vector_store_by_name(client=client, vector_store_name=vector_store_name)
    if match is not None:
        return match

    return client.vector_stores.create(name=vector_store_name)


def find_vector_store_by_name(client: Any, vector_store_name: str):
    """Find the deterministically selected vector store whose name matches exactly."""
    after: str | None = None
    matching_items: list[Any] = []
    while True:
        page = client.vector_stores.list(limit=100, after=after)
        for item in page.data:
            if item.name == vector_store_name:
                matching_items.append(item)

        if not getattr(page, "has_more", False):
            break
        after = page.data[-1].id if page.data else None
        if after is None:
            break

    if not matching_items:
        return None
    return sorted(matching_items, key=lambda item: str(item.id))[0]


def clear_vector_store(client: Any, vector_store_id: str) -> dict[str, Any]:
    """Detach and delete all existing files before re-indexing (intentional demo reset behavior)."""
    detached_file_ids: set[str] = set()
    detach_failed_file_ids: set[str] = set()
    deleted_from_storage: set[str] = set()
    detach_failures: list[str] = []
    delete_failures: list[str] = []

    # The vector-store file listing is eventually consistent, so re-check until empty.
    while True:
        file_ids = list_all_vector_store_file_ids(client=client, vector_store_id=vector_store_id)
        if not file_ids:
            break

        handled_file_ids = detached_file_ids | detach_failed_file_ids
        if all(file_id in handled_file_ids for file_id in file_ids):
            break

        for file_id in file_ids:
            if file_id in detached_file_ids or file_id in detach_failed_file_ids:
                continue

            try:
                client.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)
                detached_file_ids.add(file_id)
            except Exception as exc:
                detach_failures.append(f"{file_id}: {exc}")
                detach_failed_file_ids.add(file_id)
                continue

            try:
                client.files.delete(file_id)
                deleted_from_storage.add(file_id)
            except Exception as exc:
                delete_failures.append(f"{file_id}: {exc}")

    return {
        "detached_count": len(detached_file_ids),
        "detach_failed_count": len(detach_failed_file_ids),
        "deleted_from_storage_count": len(deleted_from_storage),
        "detach_failures": detach_failures,
        "delete_failures": delete_failures,
    }


def format_clear_summary(clear_result: dict[str, Any]) -> list[str]:
    """Render markdown bullet lines summarizing vector-store clear behavior."""
    summary_lines = [
        "- intentional demo behavior: Step 02 starts from a clean slate by wiping prior vector-store contents",
        "- this wipe/reset is for deterministic demo reruns and is not a production recommendation",
        f"- detached `{clear_result['detached_count']}` existing file links from the vector store",
        f"- permanently deleted `{clear_result['deleted_from_storage_count']}` underlying files from OpenAI file storage",
    ]

    detach_failures = clear_result.get("detach_failures") or []
    if detach_failures:
        summary_lines.append(f"- detach failures (`{len(detach_failures)}`):")
        summary_lines.extend([f"  - {failure}" for failure in detach_failures])

    delete_failures = clear_result.get("delete_failures") or []
    if delete_failures:
        summary_lines.append(f"- storage delete failures (`{len(delete_failures)}`):")
        summary_lines.extend([f"  - {failure}" for failure in delete_failures])

    return summary_lines


def upload_folder_to_vector_store(
    client: Any,
    vector_store_id: str,
    documents_dir: Path,
    doc_id_to_metadata: dict[str, dict[str, Any]],
    file_purpose: str,
    max_files_per_batch: int,
    skip_files_without_metadata: bool,
) -> int:
    """Upload supported documents with metadata attributes in deterministic path order."""
    entries: list[dict[str, Any]] = []
    uploaded_file_count = 0

    for file_path in iter_document_paths(documents_dir):
        doc_id = infer_doc_id_from_path(file_path)
        metadata = doc_id_to_metadata.get(doc_id)

        if metadata is None:
            if skip_files_without_metadata:
                continue
            raise ValueError(f"Missing extraction row for doc_id={doc_id} (file={file_path.name})")

        with file_path.open("rb") as f:
            uploaded_file = client.files.create(file=f, purpose=file_purpose)

        attributes = build_vector_store_attributes(metadata)
        entries.append(
            {
                "file_id": uploaded_file.id,
                "attributes": attributes,
                "chunking_strategy": explicit_chunking_strategy(),
            }
        )
        uploaded_file_count += 1

        if len(entries) >= max_files_per_batch:
            create_batch_and_poll(client=client, vector_store_id=vector_store_id, entries=entries)
            entries = []

    if entries:
        create_batch_and_poll(client=client, vector_store_id=vector_store_id, entries=entries)

    return uploaded_file_count


def create_batch_and_poll(client: Any, vector_store_id: str, entries: list[dict[str, Any]]) -> None:
    """Create one upload batch and block until ingestion completes."""
    for index, entry in enumerate(entries):
        if "chunking_strategy" not in entry:
            raise RuntimeError(
                f"Step 02 upload entry at index={index} is missing required per-file chunking_strategy."
            )

    create_and_poll = client.vector_stores.file_batches.create_and_poll
    create_and_poll(vector_store_id=vector_store_id, files=entries)


def explicit_chunking_strategy() -> dict[str, Any]:
    return {
        "type": "static",
        "static": {
            "max_chunk_size_tokens": CHUNK_SIZE_TOKENS,
            "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS,
        },
    }


def list_all_vector_store_file_ids(client: Any, vector_store_id: str) -> list[str]:
    """List all linked vector-store file IDs via pagination."""
    file_ids: list[str] = []
    after: str | None = None

    while True:
        page = client.vector_stores.files.list(vector_store_id=vector_store_id, limit=100, after=after)
        page_file_ids = [item.id for item in page.data]
        file_ids.extend(page_file_ids)

        if not getattr(page, "has_more", False):
            break

        after = page.data[-1].id if page.data else None
        if after is None:
            break

    return sorted(file_ids)


def iter_document_paths(documents_dir: Path) -> Iterator[Path]:
    """Yield supported document paths in deterministic sorted order."""
    for path in sorted(documents_dir.rglob("*")):
        if path.is_file() and is_supported_document(path):
            yield path


def deterministic_created_at(vector_store: Any) -> str:
    """Return manifest timestamp, allowing override via environment variable."""
    value = os.getenv(DETERMINISTIC_CREATED_AT_ENV, "").strip()
    if value:
        return value

    created_at = getattr(vector_store, "created_at", None)
    if isinstance(created_at, (int, float)):
        return datetime.fromtimestamp(created_at, tz=timezone.utc).replace(microsecond=0).isoformat()

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def to_posix_relative(path: Path) -> str:
    """Render project-relative paths using forward slashes on all platforms."""
    return path.relative_to(ROOT).as_posix()


def is_supported_document(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def infer_doc_id_from_path(path: Path) -> str:
    return path.stem


def build_vector_store_attributes(metadata: dict[str, Any]) -> dict[str, Any]:
    doc_id = require_str(metadata.get("doc_id"), "doc_id")
    tenant_id = require_str(metadata.get("tenant_id"), "tenant_id")
    sensitivity = require_str(metadata.get("sensitivity"), "sensitivity")
    doc_type = require_str(metadata.get("doc_type"), "doc_type")
    date = require_str(metadata.get("date"), "date")

    primary_company = metadata.get("primary_company")
    primary_company_str = primary_company if isinstance(primary_company, str) and primary_company.strip() else ""

    participant_names = extract_participant_names(metadata.get("participants"))
    participant_names_compact = compact_string(participant_names, max_len=512)

    attributes: dict[str, Any] = {
        "doc_id": doc_id,
        "tenant_id": tenant_id,
        "sensitivity": sensitivity,
        "doc_type": doc_type,
        "date": date,
    }

    if primary_company_str and primary_company_str != UNKNOWN_STRING:
        attributes["primary_company"] = primary_company_str

    if participant_names_compact:
        attributes["participants"] = participant_names_compact

    return clamp_attributes(attributes, max_keys=16)


def extract_participant_names(participants: Any) -> str:
    if not isinstance(participants, list):
        return ""

    names: list[str] = []
    for item in participants:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip() and name.strip() != UNKNOWN_STRING:
                names.append(name.strip())

    return ", ".join(names)


def clamp_attributes(attributes: dict[str, Any], max_keys: int) -> dict[str, Any]:
    if len(attributes) <= max_keys:
        return attributes
    kept_keys = list(attributes.keys())[:max_keys]
    return {k: attributes[k] for k in kept_keys}


def compact_string(value: str, max_len: int) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:max_len]


def require_str(value: Any, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"Expected non-empty string for field '{field_name}', got: {value!r}")


def env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
