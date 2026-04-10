import re
from dataclasses import dataclass
from typing import Any

try:
    import tiktoken
except ModuleNotFoundError:
    tiktoken = None

from shared.io_utils import read_jsonl
from shared.paths import EXTRACTIONS_PATH, UNSTRUCTURED_DIR

CHUNK_TOKENS = 450
CHUNK_OVERLAP_TOKENS = 75
TIKTOKEN_ENCODING = "cl100k_base"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    token_start: int
    token_end: int
    metadata: dict[str, Any]


def load_chunks_for_tenant(tenant_id: str) -> list[Chunk]:
    metadata_by_doc_id = _load_metadata_by_doc_id()
    documents_dir = EXTRACTIONS_PATH.parent / "cleaned_documents"
    if not documents_dir.exists():
        documents_dir = UNSTRUCTURED_DIR

    tokenizer = get_tokenizer()
    chunks: list[Chunk] = []

    document_paths = sorted(path for path in documents_dir.iterdir() if path.suffix.lower() in {".txt", ".md"})
    for file_path in document_paths:
        doc_id = file_path.stem
        metadata = metadata_by_doc_id.get(doc_id)
        if metadata is None or metadata.get("tenant_id") != tenant_id:
            continue
        text = file_path.read_text(encoding="utf-8")
        chunks.extend(chunk_text(doc_id=doc_id, text=text, metadata=metadata, tokenizer=tokenizer))

    return chunks


def chunk_text(doc_id: str, text: str, metadata: dict[str, Any], tokenizer: Any) -> list[Chunk]:
    token_ids = tokenizer.encode(text)
    if len(token_ids) <= CHUNK_TOKENS:
        return [
            Chunk(
                chunk_id=f"{doc_id}::chunk_0000",
                doc_id=doc_id,
                text=tokenizer.decode(token_ids),
                token_start=0,
                token_end=len(token_ids),
                metadata=metadata,
            )
        ]

    stride = max(1, CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS)
    output: list[Chunk] = []
    start = 0
    chunk_idx = 0

    while start < len(token_ids):
        end = min(len(token_ids), start + CHUNK_TOKENS)
        output.append(
            Chunk(
                chunk_id=f"{doc_id}::chunk_{chunk_idx:04d}",
                doc_id=doc_id,
                text=tokenizer.decode(token_ids[start:end]),
                token_start=start,
                token_end=end,
                metadata=metadata,
            )
        )
        chunk_idx += 1
        start += stride

    return output


def get_tokenizer() -> Any:
    if tiktoken is None:
        return WhitespaceTokenizer()

    try:
        return tiktoken.get_encoding(TIKTOKEN_ENCODING)
    except Exception:
        return WhitespaceTokenizer()


class WhitespaceTokenizer:
    def encode(self, text: str) -> list[str]:
        return text.split()

    def decode(self, tokens: list[str]) -> str:
        return " ".join(tokens)


def tokenize_for_bm25(text: str) -> list[str]:
    return re.findall(r"[a-z0-9$%\.]+", text.lower())


def _load_metadata_by_doc_id() -> dict[str, dict[str, Any]]:
    records = read_jsonl(EXTRACTIONS_PATH)
    return {
        str(record.get("doc_id", "")).strip(): record
        for record in records
        if str(record.get("doc_id", "")).strip()
    }
