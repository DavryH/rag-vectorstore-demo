import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

RUN_FILENAMES = {
    "04-semantic-retrieval": "run_step_04_semantic_retrieval.py",
    "05-sparse-keyword-retrieval": "run_step_05_sparse_keyword_retrieval.py",
}

def load_step_module(step_dir: str, module_name: str):
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "steps" / step_dir / RUN_FILENAMES[step_dir]
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

def build_fake_vector_search_client(results: list[dict]):
    response = SimpleNamespace(data=[SimpleNamespace(**result) for result in results])
    search = lambda **_kwargs: response
    return SimpleNamespace(vector_stores=SimpleNamespace(search=search))

def test_step4_writes_jsonl_and_summary(tmp_path, monkeypatch):
    module = load_step_module("04-semantic-retrieval", "step04_run")

    query_plan = {
        "query_id": "MVP-001",
        "original_query": "What is Helio ARR?",
        "rewritten_query": "helio arr latest",
        "sparse_query": {"required_terms": ["helio"], "include_terms": ["helio", "arr"], "phrases": [], "exclude_terms": []},
    }

    monkeypatch.setattr(module, "STEP4_DIR", tmp_path / "04")
    monkeypatch.setattr(module, "load_query_ids", lambda _query_id: ["MVP-001"])
    monkeypatch.setattr(module, "find_query_plan", lambda _query_id: query_plan)
    monkeypatch.setattr(module, "resolve_vector_store_id", lambda: "vs_123")
    monkeypatch.setattr(module, "get_openai_client", lambda: build_fake_vector_search_client([
        {
            "score": 0.91,
            "attributes": {"doc_id": "doc-1", "chunk_id": "c1", "tenant_id": "unknown", "sensitivity": "internal"},
            "content": [{"text": "Helio ARR details"}],
        }
    ]))
    monkeypatch.setattr(sys, "argv", ["run_step.py", "--query-id", "MVP-001"])

    module.main()

    rows = [json.loads(line) for line in (tmp_path / "04" / "semantic-retrieval.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = (tmp_path / "04" / "04-semantic-retrieval-summary.md").read_text(encoding="utf-8")

    assert rows[0]["retrieval_query"] == "helio arr latest"
    assert "# Step 04 Summaries" in summary

def test_step5_writes_jsonl_and_summary(tmp_path, monkeypatch):
    module = load_step_module("05-sparse-keyword-retrieval", "step05_run")

    sparse_query = {
        "required_terms": ["helio"],
        "include_terms": ["helio", "arr", "revenue"],
        "phrases": ["gross churn"],
        "exclude_terms": [],
    }
    query_plan = {
        "query_id": "MVP-001",
        "original_query": "What is Helio ARR?",
        "rewritten_query": "helio arr latest",
        "sparse_query": sparse_query,
    }

    monkeypatch.setattr(module, "STEP5_DIR", tmp_path / "05")
    monkeypatch.setattr(module, "load_query_ids", lambda _query_id: ["MVP-001"])
    monkeypatch.setattr(module, "find_query_plan", lambda _query_id: query_plan)
    monkeypatch.setattr(sys, "argv", ["run_step.py", "--query-id", "MVP-001"])

    module.main()

    rows = [json.loads(line) for line in (tmp_path / "05" / "sparse-keyword-retrieval.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = (tmp_path / "05" / "05-sparse-keyword-retrieval-summary.md").read_text(encoding="utf-8")

    assert rows[0]["sparse_query"] == sparse_query
    assert "# Step 05 Summaries" in summary

def test_step4_requires_query_id():
    module = load_step_module("04-semantic-retrieval", "step04_run_missing_id")

    try:
        module.load_query_ids(None)
        raise AssertionError("Expected RuntimeError when query_id is missing")
    except RuntimeError as exc:
        assert "requires --query-id" in str(exc)

def test_step4_requires_any_query_text():
    module = load_step_module("04-semantic-retrieval", "step04_run_missing_query")

    try:
        module.build_semantic_retrieval_payload("MVP-001", {"tenant_id": "t1", "role": "analyst"})
        raise AssertionError("Expected RuntimeError when query text is missing")
    except RuntimeError as exc:
        assert "requires rewritten_query or original_query" in str(exc)

def test_step4_merges_single_query_output_into_existing_file(tmp_path, monkeypatch):
    module = load_step_module("04-semantic-retrieval", "step04_run_merge")

    step4_dir = tmp_path / "04"
    step4_dir.mkdir(parents=True, exist_ok=True)
    existing_row = {
        "query_id": "MVP-000",
        "retrieval_query": "existing",
        "embedding_model": "text-embedding-3-small",
        "retrieval_mode": "openai_embeddings",
        "access_filter": {"role": "analyst", "applied": True, "total_chunk_count": 0, "accessible_chunk_count": 0, "excluded_chunk_count": 0, "excluded_doc_ids": []},
        "candidates": [],
        "status": "ready_for_rerank",
    }
    (step4_dir / "semantic-retrieval.jsonl").write_text(json.dumps(existing_row) + "\n", encoding="utf-8")

    query_plan = {
        "query_id": "MVP-001",
        "tenant_id": "t1",
        "role": "analyst",
        "original_query": "What is Helio ARR?",
        "rewritten_query": "helio arr latest",
        "sparse_query": {"required_terms": ["helio"], "include_terms": ["helio", "arr"], "phrases": [], "exclude_terms": []},
    }

    monkeypatch.setattr(module, "STEP4_DIR", step4_dir)
    monkeypatch.setattr(module, "load_query_ids", lambda _query_id: ["MVP-001"])
    monkeypatch.setattr(module, "find_query_plan", lambda _query_id: query_plan)
    monkeypatch.setattr(module, "resolve_vector_store_id", lambda: "vs_123")
    monkeypatch.setattr(module, "get_openai_client", lambda: build_fake_vector_search_client([
        {
            "score": 0.91,
            "attributes": {"doc_id": "doc-1", "chunk_id": "c1", "tenant_id": "t1", "sensitivity": "internal"},
            "content": [{"text": "Helio ARR details"}],
        }
    ]))
    monkeypatch.setattr(sys, "argv", ["run_step.py", "--query-id", "MVP-001"])

    module.main()

    rows = [json.loads(line) for line in (step4_dir / "semantic-retrieval.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["query_id"] for row in rows] == ["MVP-000", "MVP-001"]

def test_step4_uses_rewritten_query_when_original_query_missing(monkeypatch):
    module = load_step_module("04-semantic-retrieval", "step04_run_rewrite_first")

    monkeypatch.setattr(module, "resolve_vector_store_id", lambda: "vs_123")
    captured_queries: list[str] = []
    monkeypatch.setattr(
        module,
        "search_vector_store",
        lambda **kwargs: captured_queries.append(kwargs["query"]) or [],
    )

    payload = module.build_semantic_retrieval_payload(
        "MVP-001",
        {"tenant_id": "t1", "role": "analyst", "original_query": "   ", "rewritten_query": "dense query"},
    )

    assert payload["retrieval_query"] == "dense query"
    assert captured_queries == ["dense query"]
