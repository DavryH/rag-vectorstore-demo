import importlib.util
import json
import sys
from pathlib import Path


def load_step_module():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "steps" / "08-answer" / "run_step_08_answer.py"
    spec = importlib.util.spec_from_file_location("step08_run", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_main_processes_all_queries_and_calls_llm_per_query(tmp_path, monkeypatch):
    module = load_step_module()

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(
        json.dumps(
            [
                {"id": "MVP-001", "question": "q1", "expected_citations": ["DOC-1"]},
                {"id": "MVP-002", "question": "q2", "expected_citations": ["DOC-2"]},
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)
    monkeypatch.setattr(module, "STEP7_DIR", tmp_path / "07-extract-quotes")
    monkeypatch.setattr(module, "STEP8_DIR", tmp_path / "08-answer")

    (tmp_path / "07-extract-quotes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "07-extract-quotes" / "quote-extraction.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"query_id": "MVP-001", "quotes": [{"doc_id": "DOC-1", "chunk_id": "c1", "quote": "q1"}]}),
                json.dumps({"query_id": "MVP-002", "quotes": [{"doc_id": "DOC-2", "chunk_id": "c2", "quote": "q2"}]}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    call_count = {"n": 0}

    def fake_answer(*, model, question, documents, expected_facts, evidence_coverage, requires_timeline_summary):
        call_count["n"] += 1
        return {"answer": f"answer for {question}", "citations": [documents[0]["document_id"]], "supported_facts": [{"field": "query_answer", "value": f"answer for {question}", "supported": True, "missing_reason": "", "citations": [documents[0]["document_id"]]}]}

    monkeypatch.setattr(module, "answer_query_with_llm", fake_answer)
    monkeypatch.setattr(sys, "argv", ["run_step.py", "--all-queries", "--model", "gpt-test"])

    module.main()

    assert call_count["n"] == 2
    rows = [json.loads(line) for line in (tmp_path / "08-answer" / "answer.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2


def test_resolve_answer_model_prefers_openai_answer_model(monkeypatch, caplog):
    module = load_step_module()
    monkeypatch.setenv("OPENAI_ANSWER_MODEL", "gpt-4.1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")

    with caplog.at_level("ERROR"):
        model = module.resolve_answer_model(None)

    assert model == "gpt-4.1"
    assert caplog.records == []


def test_resolve_answer_model_falls_back_to_openai_model_with_error_log(monkeypatch, caplog):
    module = load_step_module()
    monkeypatch.delenv("OPENAI_ANSWER_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")

    with caplog.at_level("ERROR"):
        model = module.resolve_answer_model(None)

    assert model == "gpt-4.1-mini"
    assert any("falling back to OPENAI_MODEL" in record.message for record in caplog.records)


def test_normalize_placeholder_documents_returns_empty_when_no_quotes():
    module = load_step_module()

    query = {"id": "MVP-001", "question": "What is ARR?", "expected_citations": ["AUR-EMAIL-004"]}

    docs = module.normalize_placeholder_documents(query=query, quote_payload={"quotes": []}, rerank_payload=None)

    assert docs == []


def test_answer_query_dry_run_handles_no_documents():
    module = load_step_module()

    payload = module.answer_query_dry_run("What is ARR?", [])

    assert payload == {
        "answer": "Placeholder final answer for: What is ARR?",
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


def test_ensure_answer_shape_rejects_unknown_citation():
    module = load_step_module()

    documents = [
        {"document_id": "DOC-1", "file_name": "doc-1.txt", "content": "x"},
    ]

    try:
        module.ensure_answer_shape({"answer": "ok", "citations": ["UNKNOWN"], "supported_facts": [{"field": "x", "value": "ok", "supported": True, "missing_reason": "", "citations": ["DOC-1"]}]}, documents)
        raise AssertionError("Expected RuntimeError for invalid citation")
    except RuntimeError as exc:
        assert "not present in source documents" in str(exc)


def test_ensure_answer_shape_rejects_empty_citations():
    module = load_step_module()

    documents = [
        {"document_id": "DOC-1", "file_name": "doc-1.txt", "content": "x"},
    ]

    try:
        module.ensure_answer_shape({"answer": "ok", "citations": [], "supported_facts": [{"field": "x", "value": "ok", "supported": True, "missing_reason": "", "citations": ["DOC-1"]}]}, documents)
        raise AssertionError("Expected RuntimeError for empty citations")
    except RuntimeError as exc:
        assert "at least one citation when evidence documents exist" in str(exc)


def test_ensure_answer_shape_rejects_citations_without_documents():
    module = load_step_module()

    try:
        module.ensure_answer_shape(
            {
                "answer": "No accessible documents mention Project Sunflower.",
                "citations": ["placeholder-doc-1"],
                "supported_facts": [
                    {
                        "field": "project_sunflower_description",
                        "value": "",
                        "supported": False,
                        "missing_reason": "No evidence mentions Project Sunflower.",
                        "citations": [],
                    }
                ],
            },
            [],
        )
        raise AssertionError("Expected RuntimeError for citations when no documents exist")
    except RuntimeError as exc:
        assert "must not include citations when no evidence documents were provided" in str(exc)


def test_main_fails_for_unknown_query_id(tmp_path, monkeypatch):
    module = load_step_module()

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(json.dumps([{"id": "MVP-001", "question": "q1"}]), encoding="utf-8")

    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)
    monkeypatch.setattr(module, "STEP7_DIR", tmp_path / "07-extract-quotes")
    monkeypatch.setattr(module, "STEP8_DIR", tmp_path / "08-answer")
    monkeypatch.setattr(sys, "argv", ["run_step.py", "--query-id", "MVP-999", "--dry-run"])

    try:
        module.main()
        raise AssertionError("Expected RuntimeError for unknown query_id")
    except RuntimeError as exc:
        assert "Unknown query_id=MVP-999" in str(exc)


def test_filtered_rerun_preserves_existing_answers(tmp_path, monkeypatch):
    module = load_step_module()

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(
        json.dumps(
            [
                {"id": "MVP-001", "question": "q1", "expected_citations": ["DOC-1"]},
                {"id": "MVP-002", "question": "q2", "expected_citations": ["DOC-2"]},
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)
    monkeypatch.setattr(module, "STEP7_DIR", tmp_path / "07-extract-quotes")
    monkeypatch.setattr(module, "STEP8_DIR", tmp_path / "08-answer")

    (tmp_path / "07-extract-quotes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "07-extract-quotes" / "quote-extraction.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"query_id": "MVP-001", "quotes": [{"doc_id": "DOC-1", "chunk_id": "c1", "quote": "t1"}]}),
                json.dumps({"query_id": "MVP-002", "quotes": [{"doc_id": "DOC-2", "chunk_id": "c2", "quote": "t2"}]}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (tmp_path / "08-answer").mkdir(parents=True, exist_ok=True)
    (tmp_path / "08-answer" / "answer.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"query_id": "MVP-001", "question": "q1", "answer": "old 1", "citations": ["DOC-1"], "supporting_quotes": [], "status": "ready_for_eval", "answer_model": "x", "answer_source": "y"}),
                json.dumps({"query_id": "MVP-002", "question": "q2", "answer": "old 2", "citations": ["DOC-2"], "supporting_quotes": [], "status": "ready_for_eval", "answer_model": "x", "answer_source": "y"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["run_step.py", "--query-id", "MVP-001", "--dry-run"])

    module.main()

    rows = [json.loads(line) for line in (tmp_path / "08-answer" / "answer.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["query_id"] for row in rows] == ["MVP-001", "MVP-002"]
    assert rows[0]["answer"].startswith("Placeholder final answer for")
    assert rows[1]["answer"] == "old 2"

def test_ensure_answer_shape_requires_missing_reason_for_unsupported_fact():
    module = load_step_module()

    documents = [{"document_id": "DOC-1", "file_name": "doc-1.txt", "content": "x"}]
    payload = {
        "answer": "Name is Priya; role not stated.",
        "citations": ["DOC-1"],
        "supported_facts": [
            {
                "field": "primary_contact_name",
                "value": "Priya Singh",
                "supported": True,
                "missing_reason": "",
                "citations": ["DOC-1"],
            },
            {
                "field": "primary_contact_role_title",
                "value": "",
                "supported": False,
                "missing_reason": "",
                "citations": ["DOC-1"],
            },
        ],
    }

    try:
        module.ensure_answer_shape(payload, documents)
        raise AssertionError("Expected RuntimeError for missing missing_reason")
    except RuntimeError as exc:
        assert "must include missing_reason" in str(exc)


def test_ensure_answer_shape_requires_value_for_supported_fact():
    module = load_step_module()

    documents = [{"document_id": "DOC-1", "file_name": "doc-1.txt", "content": "x"}]
    payload = {
        "answer": "Name is known.",
        "citations": ["DOC-1"],
        "supported_facts": [
            {
                "field": "primary_contact_name",
                "value": "",
                "supported": True,
                "missing_reason": "",
                "citations": ["DOC-1"],
            }
        ],
    }

    try:
        module.ensure_answer_shape(payload, documents)
        raise AssertionError("Expected RuntimeError for missing supported value")
    except RuntimeError as exc:
        assert "must include non-empty value when supported=true" in str(exc)


def test_repair_supported_fact_citations_repairs_when_single_answer_citation():
    module = load_step_module()

    payload = {
        "answer": "Name is Priya.",
        "citations": ["DOC-1"],
        "supported_facts": [
            {
                "field": "primary_contact_name",
                "value": "Priya Singh",
                "supported": True,
                "missing_reason": "",
                "citations": [],
            }
        ],
    }

    module.repair_supported_fact_citations(payload)

    assert payload["supported_facts"][0]["citations"] == ["DOC-1"]


def test_run_for_query_returns_entity_no_evidence_answer_when_grounding_failed():
    module = load_step_module()

    query = {
        "id": "RAG-004B",
        "question": "What is Project Sunflower and what are the related diligence concerns?",
        "expected_facts": ["project_sunflower_description", "related_diligence_concerns"],
    }
    quote_payload = {
        "quotes": [],
        "evidence_coverage": [
            {"field": "entity_grounding", "supported": False, "reason": "required_terms_zero_match_after_access_filter"}
        ],
    }

    row = module.run_for_query(query, quote_payload, rerank_payload=None, model="gpt-test", dry_run=False)

    assert row["answer"] == "No accessible documents at the requester's permission level mention Project Sunflower or its related diligence details."
    assert row["citations"] == []
    assert row["document_count"] == 0
    assert all(fact["supported"] is False for fact in row["supported_facts"])


def test_run_for_query_uses_role_aware_no_evidence_wording_for_real_role():
    module = load_step_module()

    query = {
        "id": "RAG-004B",
        "question": "What is Project Sunflower and what are the related diligence concerns?",
        "role": "Analyst",
        "expected_facts": ["project_sunflower_description", "related_diligence_concerns"],
    }
    quote_payload = {
        "quotes": [],
        "evidence_coverage": [
            {"field": "entity_grounding", "supported": False, "reason": "required_terms_zero_match_after_access_filter"}
        ],
    }

    row = module.run_for_query(query, quote_payload, rerank_payload=None, model="gpt-test", dry_run=False)

    assert row["answer"] == "No accessible documents at the analyst permission level mention Project Sunflower or its related diligence details."


def test_run_for_query_falls_back_when_role_is_placeholder_value():
    module = load_step_module()

    query = {
        "id": "RAG-004B",
        "question": "What is Project Sunflower and what are the related diligence concerns?",
        "role": "unknown",
        "expected_facts": ["project_sunflower_description", "related_diligence_concerns"],
    }
    quote_payload = {
        "quotes": [],
        "evidence_coverage": [
            {"field": "entity_grounding", "supported": False, "reason": "required_terms_zero_match_after_access_filter"}
        ],
    }

    row = module.run_for_query(query, quote_payload, rerank_payload=None, model="gpt-test", dry_run=False)

    assert row["answer"] == "No accessible documents at the requester's permission level mention Project Sunflower or its related diligence details."


def test_run_for_query_document_count_uses_unique_grounded_citations(monkeypatch):
    module = load_step_module()

    query = {"id": "MVP-COUNT", "question": "q"}
    quote_payload = {
        "quotes": [
            {"doc_id": "DOC-1", "chunk_id": "c1", "quote": "a"},
            {"doc_id": "DOC-1", "chunk_id": "c2", "quote": "b"},
        ],
        "evidence_coverage": [{"field": "query_answer", "supported": True, "reason": "explicit"}],
    }

    def fake_answer(**_kwargs):
        return {
            "answer": "ok",
            "citations": ["DOC-1", "DOC-1"],
            "supported_facts": [
                {"field": "query_answer", "value": "ok", "supported": True, "missing_reason": "", "citations": ["DOC-1"]}
            ],
        }

    monkeypatch.setattr(module, "answer_query_with_llm", fake_answer)
    row = module.run_for_query(query, quote_payload, rerank_payload=None, model="gpt-test", dry_run=False)
    assert row["document_count"] == 1


def test_repair_supported_fact_citations_does_not_guess_when_multiple_answer_citations():
    module = load_step_module()

    payload = {
        "answer": "Name is Priya.",
        "citations": ["DOC-1", "DOC-2"],
        "supported_facts": [
            {
                "field": "primary_contact_name",
                "value": "Priya Singh",
                "supported": True,
                "missing_reason": "",
                "citations": [],
            }
        ],
    }

    module.repair_supported_fact_citations(payload)

    assert payload["supported_facts"][0]["citations"] == []


def test_answer_query_with_llm_fails_fast_without_retry(monkeypatch):
    module = load_step_module()
    calls: list[dict[str, object]] = []

    def fake_request_answer_payload(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("shape validation failed")

    monkeypatch.setattr(module, "request_answer_payload", fake_request_answer_payload)

    try:
        module.answer_query_with_llm(
            model="gpt-test",
            question="Who is the contact?",
            documents=[{"document_id": "DOC-1", "file_name": "", "chunk_id": "c1", "exact_quote": "Priya", "resolver_context": "", "display_snippet": "", "doc_date": "", "timeline_milestone": "", "fact_labels": [], "quote_rationale": ""}],
            expected_facts=["primary_contact_name"],
            evidence_coverage=[{"field": "primary_contact_name", "supported": True, "reason": "quoted"}],
            requires_timeline_summary=False,
        )
        raise AssertionError("Expected RuntimeError")
    except RuntimeError as exc:
        assert str(exc) == "shape validation failed"

    assert len(calls) == 1
    assert "correction_note" not in calls[0]


def test_normalize_placeholder_documents_sorts_timeline_docs_by_date():
    module = load_step_module()

    query = {"id": "RAG-005", "question": "In 4 bullets, summarize the timeline from intro to latest terms."}
    quote_payload = {
        "quotes": [
            {"doc_id": "DOC-2", "chunk_id": "c2", "quote": "latest terms", "doc_date": "2026-02-12"},
            {"doc_id": "DOC-1", "chunk_id": "c1", "quote": "intro", "doc_date": "2025-11-12"},
        ]
    }

    docs = module.normalize_placeholder_documents(query, quote_payload, rerank_payload=None)

    assert [doc["document_id"] for doc in docs] == ["DOC-1", "DOC-2"]


def test_ordered_supported_fact_fields_prefers_evidence_coverage_over_expected_facts():
    module = load_step_module()

    query = {"expected_facts": ["fallback_field"]}
    quote_payload = {
        "evidence_coverage": [
            {"field": "codename", "supported": True, "reason": "x"},
            {"field": "business_issue", "supported": True, "reason": "y"},
        ]
    }

    fields = module.ordered_supported_fact_fields(query, quote_payload)

    assert fields == ["codename", "business_issue"]


def test_build_answer_user_prompt_includes_no_documents_instruction():
    module = load_step_module()

    prompt = module.build_answer_user_prompt(
        original_query="What is Project Sunflower?",
        documents=[],
        expected_facts=[],
        evidence_coverage=[],
        requires_timeline_summary=False,
    )

    assert "If documents is empty, explicitly answer that no accessible documents at the requester's permission level provide the requested information." in prompt


def test_build_answer_user_prompt_includes_structured_timeline_hints():
    module = load_step_module()

    prompt = module.build_answer_user_prompt(
        original_query="In 4 bullets, summarize the Helio deal from intro to latest terms.",
        documents=[
            {
                "document_id": "AUR-EMAIL-008",
                "file_name": "",
                "chunk_id": "c1",
                "exact_quote": "The company is now proposing an $82M pre-money valuation.",
                "resolver_context": "",
                "display_snippet": "",
                "doc_date": "2026-02-12",
                "timeline_milestone": "latest_terms",
                "fact_labels": ["valuation_terms"],
                "milestone_details": {
                    "milestone_type": "latest_terms",
                    "intro_date_text": "",
                    "valuation_text": "$82M pre-money",
                    "raise_amount_text": "",
                    "board_term": "one board observer seat",
                    "liquidation_preference": "1x non-participating liquidation preference",
                    "pro_rata_rights": "pro-rata participation rights",
                    "investor_side": "",
                    "company_side": "The company is now proposing",
                    "term_summary_parts": ["$82M pre-money", "one board observer seat"],
                },
                "quote_rationale": "latest",
            }
        ],
        expected_facts=[],
        evidence_coverage=[],
        requires_timeline_summary=True,
    )

    assert "structured_timeline_hints:" in prompt
    assert "latest_terms: Latest Terms: $82M pre-money" in prompt


def test_build_summary_omits_default_ready_for_eval_status_line():
    module = load_step_module()

    summary = module.build_summary(
        [
            {
                "query_id": "MVP-001",
                "question": "q1",
                "answer": "a1",
                "citations": ["DOC-1"],
                "supported_facts": [],
                "status": "ready_for_eval",
                "answer_source": "openai",
                "answer_model": "gpt-test",
                "supporting_quotes": [],
            }
        ]
    )

    assert "- status: `ready_for_eval`" not in summary
    assert "- query halted: `true`" not in summary


def test_build_summary_keeps_status_for_halted_queries():
    module = load_step_module()

    summary = module.build_summary(
        [
            {
                "query_id": "MVP-001",
                "question": "q1",
                "answer": "",
                "citations": [],
                "supported_facts": [],
                "status": "halted_error",
                "error_type": "RuntimeError",
                "error_message": "boom",
                "answer_source": "halted_before_eval",
                "answer_model": "gpt-test",
                "supporting_quotes": [],
            }
        ]
    )

    assert "- query halted: `true`" in summary
    assert "- status: `halted_error`" in summary


def test_build_summary_flags_missing_status_as_halted():
    module = load_step_module()

    summary = module.build_summary(
        [
            {
                "query_id": "MVP-001",
                "question": "q1",
                "answer": "",
                "citations": [],
                "supported_facts": [],
                "error_type": "RuntimeError",
                "error_message": "boom",
                "answer_source": "openai",
                "answer_model": "gpt-test",
                "supporting_quotes": [],
            }
        ]
    )

    assert "- query halted: `true`" in summary
    assert "- status: `(missing)`" in summary
