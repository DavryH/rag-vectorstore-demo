import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

def load_step_module():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "steps" / "03-query-rewrite-and-sparse-query" / "run_step_03_query_rewrite_and_sparse_query.py"
    spec = importlib.util.spec_from_file_location("step03_run", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

def build_fake_client(payload: str):
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=payload)
            )
        ]
    )
    create = lambda **_kwargs: response
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

def test_load_query_reads_query_eval_json(tmp_path, monkeypatch):
    module = load_step_module()

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(
        json.dumps(
            [
                {"id": "MVP-001", "question": "q1", "tenant_id": "t1", "role": "analyst"},
                {"id": "MVP-002", "question": "q2", "tenant_id": "t2", "role": "analyst"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)

    row = module.load_query("MVP-002")

    assert row["question"] == "q2"
    assert row["tenant_id"] == "t2"

def test_build_query_plan_and_summary_shape():
    module = load_step_module()

    payload = {
        "rewritten_query": "helio term sheet valuation board rights",
        "sparse_query": {
            "required_terms": ["helio"],
            "include_terms": ["helio", "valuation", "board rights"],
            "phrases": ["term sheet", "board rights"],
            "exclude_terms": [],
        },
    }
    module.ensure_schema_shape(payload)

    query_plan = module.build_query_plan(
        {"id": "MVP-001", "tenant_id": "t_aurora", "role": "analyst", "question": "q"},
        payload,
        model="gpt-4.1-mini",
        source="openai_structured_output",
    )
    summary_lines = module.build_summary_lines(query_plan)
    summary_text = "\n".join(summary_lines)

    assert summary_lines[0] == "## Query `MVP-001`"
    assert "required sparse terms" in summary_text
    assert "provenance/scope terms" in summary_text
    assert "sanitized required sparse terms" in summary_text
    assert "rewrite source" in summary_text

def test_build_query_plan_falls_back_to_original_query_when_rewrite_is_empty():
    module = load_step_module()

    query_plan = module.build_query_plan(
        {"id": "MVP-001", "tenant_id": "t_aurora", "role": "analyst", "question": "Original customer question"},
        {
            "rewritten_query": "   ",
            "sparse_query": {
                "required_terms": [],
                "include_terms": [],
                "phrases": [],
                "exclude_terms": [],
            },
        },
        model="gpt-4.1-mini",
        source="openai_structured_output",
    )

    assert query_plan["rewritten_query"] == "Original customer question"
    assert query_plan["rewrite_source"] == "openai_structured_output:original_query_fallback"

def test_rewrite_query_parses_content_parts_list(monkeypatch):
    module = load_step_module()

    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=[
                        {
                            "text": '{"rewritten_query":"helio term sheet","sparse_query":'
                        },
                        {
                            "text": '{"required_terms":["helio"],"include_terms":["helio","term","sheet"],"phrases":["term sheet"],"exclude_terms":[]}}'
                        },
                    ]
                )
            )
        ]
    )

    create = lambda **_kwargs: response
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(module, "get_openai_client", lambda: fake_client)

    payload = module.rewrite_query_and_build_sparse_query("gpt-4.1-mini", "Helio term sheet")

    assert payload["rewritten_query"] == "helio term sheet"
    assert payload["sparse_query"]["required_terms"] == ["helio"]

def test_main_processes_all_queries_when_query_id_not_provided(tmp_path, monkeypatch):
    module = load_step_module()

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(
        json.dumps(
            [
                {"id": "MVP-001", "question": "What is Helio ARR?", "tenant_id": "t1", "role": "analyst"},
                {"id": "MVP-002", "question": "Who is the contact?", "tenant_id": "t1", "role": "analyst"},
            ]
        ),
        encoding="utf-8",
    )

    outputs_root = tmp_path / "data" / "outputs" / "03-query-rewrite-and-sparse-query"
    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)
    monkeypatch.setattr(module, "STEP3_DIR", outputs_root)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "load_dotenv", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(module, "get_openai_client", lambda: build_fake_client('{"rewritten_query":"helio arr","sparse_query":{"required_terms":["helio"],"include_terms":["helio","arr"],"phrases":[],"exclude_terms":[]}}'))
    monkeypatch.setattr(sys, "argv", ["run_step.py"])

    module.main()

    query_plans = json.loads((outputs_root / "query-plans.json").read_text(encoding="utf-8"))
    summaries = (outputs_root / "summaries.md").read_text(encoding="utf-8")

    assert len(query_plans) == 2
    assert {row["query_id"] for row in query_plans} == {"MVP-001", "MVP-002"}
    assert "## Query `MVP-001`" in summaries
    assert "## Query `MVP-002`" in summaries
    assert all(row["rewrite_source"] == "openai_structured_output" for row in query_plans)

def test_main_rejects_empty_query_id(tmp_path, monkeypatch):
    module = load_step_module()

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(
        json.dumps(
            [
                {"id": "MVP-001", "question": "What is Helio ARR?", "tenant_id": "t1", "role": "analyst"},
            ]
        ),
        encoding="utf-8",
    )

    outputs_root = tmp_path / "data" / "outputs" / "03-query-rewrite-and-sparse-query"
    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)
    monkeypatch.setattr(module, "STEP3_DIR", outputs_root)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "load_dotenv", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(sys, "argv", ["run_step.py", "--query-id", ""])

    try:
        module.main()
        raise AssertionError("Expected SystemExit for empty query id")
    except SystemExit as exc:
        assert exc.code == 2

    assert not outputs_root.exists()

def test_main_preserves_existing_query_plans_on_single_query_rerun(tmp_path, monkeypatch):
    module = load_step_module()

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(
        json.dumps(
            [
                {"id": "MVP-001", "question": "What is Helio ARR?", "tenant_id": "t1", "role": "analyst"},
                {"id": "MVP-002", "question": "Who is the contact?", "tenant_id": "t1", "role": "analyst"},
            ]
        ),
        encoding="utf-8",
    )

    outputs_root = tmp_path / "data" / "outputs" / "03-query-rewrite-and-sparse-query"
    outputs_root.mkdir(parents=True, exist_ok=True)
    (outputs_root / "query-plans.json").write_text(
        json.dumps(
            [
                {
                    "query_id": "MVP-001",
                    "tenant_id": "t1",
                    "role": "analyst",
                    "original_query": "What is Helio ARR?",
                    "rewritten_query": "old plan one",
                    "sparse_query": {
                        "required_terms": ["helio"],
                        "include_terms": ["helio", "arr"],
                        "phrases": [],
                        "exclude_terms": [],
                    },
                    "notes": "old",
                    "status": "ready_for_retrieval",
                    "rewrite_model": "gpt-4.1-mini",
                    "rewrite_source": "openai_structured_output",
                },
                {
                    "query_id": "MVP-002",
                    "tenant_id": "t1",
                    "role": "analyst",
                    "original_query": "Who is the contact?",
                    "rewritten_query": "old plan two",
                    "sparse_query": {
                        "required_terms": ["contact"],
                        "include_terms": ["contact"],
                        "phrases": [],
                        "exclude_terms": [],
                    },
                    "notes": "old",
                    "status": "ready_for_retrieval",
                    "rewrite_model": "gpt-4.1-mini",
                    "rewrite_source": "openai_structured_output",
                },
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)
    monkeypatch.setattr(module, "STEP3_DIR", outputs_root)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "load_dotenv", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(module, "get_openai_client", lambda: build_fake_client('{"rewritten_query":"updated plan","sparse_query":{"required_terms":["helio"],"include_terms":["helio","arr"],"phrases":[],"exclude_terms":[]}}'))
    monkeypatch.setattr(sys, "argv", ["run_step.py", "--query-id", "MVP-001"])

    module.main()

    query_plans = json.loads((outputs_root / "query-plans.json").read_text(encoding="utf-8"))
    by_query_id = {row["query_id"]: row for row in query_plans}

    assert set(by_query_id) == {"MVP-001", "MVP-002"}
    assert by_query_id["MVP-001"]["rewritten_query"] == "updated plan"
    assert by_query_id["MVP-002"]["rewritten_query"] == "old plan two"


def test_sanitize_sparse_query_removes_provenance_scope_term_but_keeps_person_anchor():
    module = load_step_module()

    original_query = "Who is Alex Chen in Birch's records, and what company is he associated with?"
    sparse_query = {
        "required_terms": ["alex chen", "birch"],
        "include_terms": ["alex chen", "birch", "company"],
        "phrases": ["alex chen"],
        "exclude_terms": [],
    }

    provenance_scope_terms = module.extract_provenance_scope_terms(original_query)
    sanitized = module.sanitize_sparse_query(original_query, sparse_query)

    assert provenance_scope_terms == ["birch"]
    assert sanitized["required_terms"] == ["alex chen"]
    assert "birch" in sanitized["include_terms"]


def test_build_query_plan_exposes_provenance_scope_and_sanitized_required_terms():
    module = load_step_module()

    query_plan = module.build_query_plan(
        {"id": "MVP-003", "tenant_id": "t_aurora", "role": "analyst", "question": "Who is Alex Chen in Birch's records?"},
        {
            "rewritten_query": "alex chen company association",
            "sparse_query": {
                "required_terms": ["alex chen", "birch"],
                "include_terms": ["alex chen", "birch"],
                "phrases": [],
                "exclude_terms": [],
            },
        },
        model="gpt-4.1-mini",
        source="openai_structured_output",
    )

    assert query_plan["provenance_scope_terms"] == ["birch"]
    assert query_plan["sanitized_required_terms"] == ["alex chen"]
    assert query_plan["sparse_query"]["required_terms"] == ["alex chen"]


def test_sanitize_sparse_query_removes_generic_provenance_anchor_terms():
    module = load_step_module()

    original_query = "Show me opportunities from our CRM and notes in the database."
    sparse_query = {
        "required_terms": ["crm", "database", "opportunities"],
        "include_terms": ["crm", "database", "opportunities", "notes"],
        "phrases": [],
        "exclude_terms": [],
    }

    provenance_scope_terms = module.extract_provenance_scope_terms(original_query)
    sanitized = module.sanitize_sparse_query(original_query, sparse_query)

    assert provenance_scope_terms == ["crm", "database"]
    assert sanitized["required_terms"] == ["opportunities"]
    assert "crm" in sanitized["include_terms"]
    assert "database" in sanitized["include_terms"]


def test_run_query_pipeline_runs_step4_per_query_and_later_steps_once(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "run_query_pipeline.py"
    spec = importlib.util.spec_from_file_location("step03_ask_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(
        json.dumps([
            {"id": "RAG-001"},
            {"id": "RAG-002"},
        ]),
        encoding="utf-8",
    )
    commands: list[list[str]] = []

    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)
    monkeypatch.setattr(module, "run_command", lambda command: commands.append(command))

    result = module.main()

    assert result == 0
    assert commands == [
        ["steps/03-query-rewrite-and-sparse-query/run_step_03_query_rewrite_and_sparse_query.py", "--all-queries"],
        ["steps/04-semantic-retrieval/run_step_04_semantic_retrieval.py", "--query-id", "RAG-001"],
        ["steps/04-semantic-retrieval/run_step_04_semantic_retrieval.py", "--query-id", "RAG-002"],
        ["steps/05-sparse-keyword-retrieval/run_step_05_sparse_keyword_retrieval.py"],
        ["steps/06-rerank/run_step_06_rerank.py"],
        ["steps/07-extract-quotes/run_step_07_extract_quotes.py", "--all-queries"],
        ["steps/08-answer/run_step_08_answer.py", "--all-queries"],
        ["steps/09-eval/run_step_09_eval.py"],
    ]
