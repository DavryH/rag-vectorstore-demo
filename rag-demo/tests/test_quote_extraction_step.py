import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


def load_step_module():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "steps" / "07-extract-quotes" / "run_step_07_extract_quotes.py"
    spec = importlib.util.spec_from_file_location("step07_extract_quotes_run", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_main_writes_quote_extraction_outputs(tmp_path, monkeypatch):
    module = load_step_module()

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(json.dumps([{"id": "MVP-001", "question": "most recent next step"}]), encoding="utf-8")

    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)
    monkeypatch.setattr(module, "STEP6_DIR", tmp_path / "06-rerank")
    monkeypatch.setattr(module, "STEP7_DIR", tmp_path / "07-extract-quotes")

    (tmp_path / "06-rerank").mkdir(parents=True, exist_ok=True)
    (tmp_path / "06-rerank" / "rerank.jsonl").write_text(
        json.dumps(
            {
                "query_id": "MVP-001",
                "ranked_candidates": [
                    {"chunk_id": "c1", "doc_id": "DOC-1", "text": "Date: 2026-02-22 Next step: schedule a call."}
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"quotes":[{"chunk_id":"c1","doc_id":"DOC-1","quote":"Next step: schedule a call.","rationale":"direct support"}],"evidence_coverage":[]}'
                )
            )
        ]
    )
    create = lambda **_kwargs: response
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(module, "get_openai_client", lambda: fake_client)

    monkeypatch.setattr(sys, "argv", ["run_step.py", "--all-queries"])
    module.main()

    output = tmp_path / "07-extract-quotes" / "quote-extraction.jsonl"
    assert output.exists()
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["query_id"] == "MVP-001"
    assert rows[0]["status"] == "ready_for_answer"
    assert rows[0]["quote_extraction_source"] == "openai_structured_output"


def test_llm_extract_quotes_parses_content_parts_list(monkeypatch):
    module = load_step_module()

    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=[
                        {"text": '{"quotes":[{"chunk_id":"c1","doc_id":"DOC-1","quote":"'},
                        {"text": 'Quoted line","rationale":"signal"}],"evidence_coverage":[{"field":"f1","supported":true,"reason":"explicit"}]}'},
                    ]
                )
            )
        ]
    )

    create = lambda **_kwargs: response
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(module, "get_openai_client", lambda: fake_client)

    quotes, evidence = module.llm_extract_quotes(
        "question",
        [{"chunk_id": "c1", "doc_id": "DOC-1", "text": "Quoted line"}],
        "gpt-test",
    )

    assert quotes[0]["chunk_id"] == "c1"
    assert quotes[0]["doc_id"] == "DOC-1"
    assert quotes[0]["quote"] == "Quoted line"
    assert quotes[0]["rationale"] == "signal"
    assert evidence == [
        {
            "field": "f1",
            "supported": False,
            "reason": "Supported coverage did not have a matching returned quote after post-processing (likely truncated).",
        }
    ]


def test_extract_for_query_includes_evidence_coverage(monkeypatch):
    module = load_step_module()

    monkeypatch.setattr(
        module,
        "llm_extract_quotes",
        lambda _question, _candidates, _model: (
            [{"chunk_id": "c1", "doc_id": "DOC-1", "quote": "q", "rationale": "r"}],
            [{"field": "x", "supported": False, "reason": "missing"}],
        ),
    )

    query = {"id": "MVP-003", "question": "Who is the point of contact and what is their role?"}
    rerank_payload = {
        "ranked_candidates": [
            {
                "chunk_id": "c1",
                "doc_id": "AUR-EMAIL-001",
                "text": "Priya Singh will be Aurora's primary point of contact.",
            }
        ]
    }

    result = module.extract_for_query(query, rerank_payload, model="gpt-test")

    assert isinstance(result.get("evidence_coverage"), list)
    assert result["evidence_coverage"][0]["field"] == "x"
    assert result["quote_extraction_source"] == "openai_structured_output"


def test_extract_for_query_short_circuits_on_entity_grounding_failure():
    module = load_step_module()

    query = {"id": "RAG-004B", "question": "What is Project Sunflower and what are the related diligence concerns?"}
    rerank_payload = {
        "ranked_candidates": [
            {"chunk_id": "c1", "doc_id": "AUR-DEAL-013", "text": "Northwind Bio diligence concerns only."}
        ],
        "selection_config": {
            "anchor_gate_triggered": True,
            "entity_grounding_failed": True,
            "short_circuit_reason": "required_terms_zero_match_after_access_filter",
        },
    }

    result = module.extract_for_query(query, rerank_payload, model="gpt-test")

    assert result["quotes"] == []
    assert result["quote_extraction_source"] == "deterministic_no_accessible_evidence"
    assert any(row["field"] == "entity_grounding" and row["supported"] is False for row in result["evidence_coverage"])


def test_find_latest_selected_candidate_ignores_non_valuation_noise():
    module = load_step_module()

    target_entity = "Acme"
    quotes = [
        {"doc_id": "DOC-LATEST", "chunk_id": "noise", "quote": "latest status update", "rationale": "r"},
        {"doc_id": "DOC-VAL", "chunk_id": "valuation", "quote": "Acme now asking $90M pre", "rationale": "r"},
    ]
    candidates = [
        {
            "doc_id": "DOC-LATEST",
            "chunk_id": "noise",
            "fused_score": 0.95,
            "metadata": {
                "date": "2026-05-01",
                "primary_company": "Acme",
                "doc_type": "memo",
            },
            "text": "Status update only, no valuation amount present.",
        },
        {
            "doc_id": "DOC-VAL",
            "chunk_id": "valuation",
            "fused_score": 0.40,
            "metadata": {
                "date": "2026-04-25",
                "primary_company": "Acme",
                "doc_type": "meeting_notes",
            },
            "text": "Acme is raising at a $90M pre-money valuation.",
        },
    ]

    latest = module.find_latest_selected_candidate(quotes, candidates, target_entity)

    assert latest is not None
    assert latest["doc_id"] == "DOC-VAL"
    assert latest["chunk_id"] == "valuation"



def test_question_requires_timeline_summary_detects_intro_to_latest_prompt():
    module = load_step_module()

    question = "In 4 bullets, summarize the Helio deal from intro to latest terms."

    assert module.question_requires_timeline_summary(question) is True


def test_question_requires_timeline_summary_does_not_trigger_on_plain_from_phrase():
    module = load_step_module()

    question = "Summarize this email from Aurora."

    assert module.question_requires_timeline_summary(question) is False


def test_build_intro_evidence_quote_includes_header_and_body_line():
    module = load_step_module()

    candidate = {
        "doc_id": "AUR-EMAIL-001",
        "chunk_id": "AUR-EMAIL-001::chunk_0000",
        "text": (
            "From: Jordan Lee <jordan.lee@auroracap.example>\n"
            "Date: 2025-11-12\n"
            "Subject: Intro: Aurora Capital <> Helio Robotics\n\n"
            "Great to meet you virtually.\n"
        ),
    }

    quote = module.build_intro_evidence_quote(candidate)

    assert "Date: 2025-11-12" in quote
    assert "Subject: Intro: Aurora Capital <> Helio Robotics" in quote
    assert "Great to meet you virtually." in quote


def test_apply_timeline_milestone_repair_adds_missing_intro_quote_and_coverage():
    module = load_step_module()

    question = "In 4 bullets, summarize the Helio deal from intro to latest terms."
    candidates = [
        {
            "doc_id": "AUR-EMAIL-001",
            "chunk_id": "AUR-EMAIL-001::chunk_0000",
            "relevance_score": 0.61,
            "fused_score": 0.40,
            "metadata": {"date": "2025-11-12"},
            "text": (
                "Date: 2025-11-12\n"
                "Subject: Intro: Aurora Capital <> Helio Robotics\n"
                "Great to meet you virtually.\n"
            ),
        },
        {
            "doc_id": "AUR-MEET-002",
            "chunk_id": "AUR-MEET-002::chunk_0000",
            "relevance_score": 0.75,
            "fused_score": 0.70,
            "metadata": {"date": "2025-11-15"},
            "text": "Helio is raising $18M in its Series A at a $90M pre-money valuation.",
        },
        {
            "doc_id": "AUR-EMAIL-007",
            "chunk_id": "AUR-EMAIL-007::chunk_0000",
            "relevance_score": 0.80,
            "fused_score": 0.72,
            "metadata": {"date": "2026-02-07"},
            "text": "Aurora would be prepared to proceed at a $78M pre-money valuation. no board seat",
        },
        {
            "doc_id": "AUR-EMAIL-008",
            "chunk_id": "AUR-EMAIL-008::chunk_0000",
            "relevance_score": 0.85,
            "fused_score": 0.82,
            "metadata": {"date": "2026-02-12"},
            "text": (
                "The company is now proposing an $82M pre-money valuation.\n"
                "Current draft terms: one board observer seat; 1x non-participating liquidation preference; pro-rata participation rights."
            ),
        },
    ]
    quotes = [
        {
            "doc_id": "AUR-MEET-002",
            "chunk_id": "AUR-MEET-002::chunk_0000",
            "quote": "Helio is raising $18M in its Series A at a $90M pre-money valuation.",
            "rationale": "initial",
        },
        {
            "doc_id": "AUR-EMAIL-007",
            "chunk_id": "AUR-EMAIL-007::chunk_0000",
            "quote": "Aurora would be prepared to proceed at a $78M pre-money valuation.",
            "rationale": "counter",
        },
        {
            "doc_id": "AUR-EMAIL-008",
            "chunk_id": "AUR-EMAIL-008::chunk_0000",
            "quote": "The company is now proposing an $82M pre-money valuation.",
            "rationale": "latest",
        },
    ]

    repaired_quotes, repaired_coverage = module.apply_timeline_milestone_repair(
        question=question,
        candidates=candidates,
        quotes=quotes,
        evidence_coverage=[],
    )

    repaired_doc_ids = [row["doc_id"] for row in repaired_quotes]
    assert "AUR-EMAIL-001" in repaired_doc_ids
    fields = {row["field"] for row in repaired_coverage}
    assert "intro_contact" in fields
    assert "initial_terms" in fields
    assert "counter_terms" in fields
    assert "latest_terms" in fields


def test_build_extraction_payload_adds_timeline_analysis_and_candidate_hints():
    module = load_step_module()

    question = "In 4 bullets, summarize the Helio deal from intro to latest terms."
    candidates = [
        {
            "doc_id": "AUR-EMAIL-001",
            "chunk_id": "AUR-EMAIL-001::chunk_0000",
            "metadata": {"date": "2025-11-12"},
            "text": "Date: 2025-11-12\nSubject: Intro: Aurora Capital <> Helio Robotics\nGreat to meet you virtually.",
        }
    ]

    payload = module.build_extraction_payload(question, candidates)

    assert payload["question_analysis"]["requires_timeline_summary"] is True
    assert "intro_contact" in payload["question_analysis"]["timeline_milestones"]
    assert payload["candidates"][0]["timeline_milestone_hint"] == "intro_contact"


def test_infer_timeline_milestone_prefers_initial_terms_when_valuation_is_explicit():
    module = load_step_module()

    candidate = {
        "doc_id": "AUR-MEET-002",
        "chunk_id": "AUR-MEET-002::chunk_0000",
        "metadata": {"date": "2025-11-15"},
        "text": (
            "Date: 2025-11-15\n"
            "Subject: Introductory diligence call follow-up\n"
            "Helio is raising $18M in its Series A at a $90M pre-money valuation."
        ),
    }

    assert module.infer_timeline_milestone(candidate) == "initial_terms"


def test_build_quote_with_resolver_context_includes_structured_milestone_details():
    module = load_step_module()

    quote = {
        "doc_id": "AUR-EMAIL-008",
        "chunk_id": "AUR-EMAIL-008::chunk_0000",
        "quote": "The company is now proposing an $82M pre-money valuation.",
        "rationale": "latest",
    }
    candidate = {
        "doc_id": "AUR-EMAIL-008",
        "chunk_id": "AUR-EMAIL-008::chunk_0000",
        "metadata": {"date": "2026-02-12"},
        "text": (
            "The company is now proposing an $82M pre-money valuation.\n"
            "Current draft terms: one board observer seat; 1x non-participating liquidation preference; pro-rata participation rights."
        ),
    }

    enriched = module.build_quote_with_resolver_context(quote, candidate)
    details = enriched["milestone_details"]

    assert enriched["timeline_milestone"] == "latest_terms"
    assert details["valuation_text"] == "$82M pre-money"
    assert details["raise_amount_text"] is None
    assert "board observer seat" in details["board_term"].lower()
    assert "non-participating liquidation preference" in details["liquidation_preference"].lower()
    assert "pro-rata participation rights" in details["pro_rata_rights"].lower()


def test_extract_milestone_details_keeps_raise_amount_only_when_explicit():
    module = load_step_module()

    valuation_only_candidate = {
        "doc_id": "AUR-EMAIL-008",
        "chunk_id": "AUR-EMAIL-008::chunk_0000",
        "metadata": {"date": "2026-02-12"},
        "text": "The company is now proposing an $82M pre-money valuation.",
    }
    explicit_raise_candidate = {
        "doc_id": "AUR-MEET-002",
        "chunk_id": "AUR-MEET-002::chunk_0000",
        "metadata": {"date": "2025-11-15"},
        "text": "Helio is raising $18M in its Series A at a $90M pre-money valuation.",
    }

    valuation_only_details = module.extract_milestone_details(valuation_only_candidate, "latest_terms")
    explicit_raise_details = module.extract_milestone_details(explicit_raise_candidate, "initial_terms")

    assert valuation_only_details["raise_amount_text"] is None
    assert explicit_raise_details["raise_amount_text"] == "$18M"


def test_apply_missing_fact_repairs_adds_multiple_quotes_from_same_candidate():
    module = load_step_module()

    candidates = [
        {
            "doc_id": "AUR-MEMO-005",
            "chunk_id": "AUR-MEMO-005::chunk_0000",
            "text": (
                "Internal codename: Project Sunflower.\n"
                "Possible acquisition interest from OmniDynamics has surfaced.\n"
                "Key diligence concern: customer concentration; top 2 customers are 38% of revenue."
            ),
        }
    ]
    quotes = []
    coverage = [
        {"field": "codename", "supported": False, "reason": "missing"},
        {"field": "acquisition_interest", "supported": False, "reason": "missing"},
        {"field": "customer_concentration", "supported": False, "reason": "missing"},
    ]

    repaired_quotes, repaired_coverage = module.apply_missing_fact_repairs(candidates, quotes, coverage)

    assert len(repaired_quotes) == 3
    assert all(row["doc_id"] == "AUR-MEMO-005" for row in repaired_quotes)
    assert all(row["supported"] is True for row in repaired_coverage)


def test_align_repaired_coverage_with_quotes_marks_truncated_repairs_unsupported():
    module = load_step_module()

    quotes = [
        {"doc_id": "DOC-1", "chunk_id": "c1", "quote": "q1", "rationale": "r"},
    ]
    coverage = [
        {"field": "codename", "supported": True, "reason": "Deterministic repair found explicit evidence in DOC-1/c1."},
        {"field": "acquisition_interest", "supported": True, "reason": "Deterministic repair found explicit evidence in DOC-2/c2."},
    ]

    aligned = module.align_repaired_coverage_with_quotes(quotes, coverage)

    assert aligned[0]["supported"] is True
    assert aligned[1]["supported"] is False
    assert "truncated" in aligned[1]["reason"].lower()


def test_llm_extract_quotes_downgrades_repair_coverage_when_repair_quote_is_truncated(monkeypatch):
    module = load_step_module()

    original_quotes = [
        {"chunk_id": f"c{i}", "doc_id": f"DOC-{i}", "quote": f"quote {i}", "rationale": "original"}
        for i in range(1, module.MAX_QUOTES + 1)
    ]
    parsed_payload = {
        "quotes": original_quotes,
        "evidence_coverage": [
            {"field": "codename", "supported": False, "reason": "missing"},
        ],
    }
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(parsed_payload)))]
    )

    create = lambda **_kwargs: response
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(module, "get_openai_client", lambda: fake_client)

    candidates = [
        {
            "doc_id": "DOC-REPAIR",
            "chunk_id": "repair-chunk",
            "text": "Internal codename: Project Sunflower.",
        }
    ]

    quotes, evidence = module.llm_extract_quotes("question", candidates, "gpt-test")

    assert len(quotes) == module.MAX_QUOTES
    assert all(row["doc_id"] != "DOC-REPAIR" for row in quotes)
    assert evidence[0]["field"] == "codename"
    assert evidence[0]["supported"] is False
    assert "truncated" in evidence[0]["reason"].lower()

def test_ensure_supported_coverage_adds_missing_acquisition_context_for_project_definition_field():
    module = load_step_module()

    question = "What is Project Sunflower and what are the related diligence concerns?"
    candidates = [
        {
            "doc_id": "AUR-MEMO-005",
            "chunk_id": "AUR-MEMO-005::chunk_0000",
            "text": (
                "Project Sunflower is the internal codename being used for the Helio Robotics situation.\n"
                "Separate from the financing discussion, there may be potential acquisition interest from OmniDynamics.\n"
                "Key diligence concern: Customer concentration remains elevated. Helio's top 2 customers account for 38% of revenue."
            ),
        }
    ]
    quotes = [
        {
            "doc_id": "AUR-MEMO-005",
            "chunk_id": "AUR-MEMO-005::chunk_0000",
            "quote": "Project Sunflower is the internal codename being used for the Helio Robotics situation.",
            "rationale": "codename",
        },
        {
            "doc_id": "AUR-MEMO-005",
            "chunk_id": "AUR-MEMO-005::chunk_0000",
            "quote": "Key diligence concern: Customer concentration remains elevated. Helio's top 2 customers account for 38% of revenue.",
            "rationale": "customer concentration",
        },
    ]
    evidence_coverage = [
        {"field": "What is Project Sunflower", "supported": True, "reason": "explicit"},
        {"field": "related diligence concerns", "supported": True, "reason": "explicit"},
    ]

    repaired_quotes, repaired_coverage = module.ensure_supported_coverage_has_quotes(
        question=question,
        candidates=candidates,
        quotes=quotes,
        evidence_coverage=evidence_coverage,
    )

    assert any("acquisition interest from omnidynamics" in row["quote"].lower() for row in repaired_quotes)
    assert all(row["supported"] is True for row in repaired_coverage)


def test_ensure_supported_coverage_repair_respects_anchor_eligibility_for_concepts():
    module = load_step_module()

    question = "What is Project Sunflower and what are the related diligence concerns?"
    candidates = [
        {
            "doc_id": "AUR-MEMO-005",
            "chunk_id": "AUR-MEMO-005::chunk_0000",
            "text": "Project Sunflower is the internal codename for the Helio Robotics process.",
        },
        {
            "doc_id": "OTHER-CO-001",
            "chunk_id": "OTHER-CO-001::chunk_0000",
            "text": "There may be potential acquisition interest from OmniDynamics in a different company.",
        },
    ]
    quotes = [
        {
            "doc_id": "AUR-MEMO-005",
            "chunk_id": "AUR-MEMO-005::chunk_0000",
            "quote": "Project Sunflower is the internal codename for the Helio Robotics process.",
            "rationale": "codename",
        },
    ]
    evidence_coverage = [
        {"field": "What is Project Sunflower", "supported": True, "reason": "explicit"},
    ]

    repaired_quotes, repaired_coverage = module.ensure_supported_coverage_has_quotes(
        question=question,
        candidates=candidates,
        quotes=quotes,
        evidence_coverage=evidence_coverage,
    )

    assert not any(row["doc_id"] == "OTHER-CO-001" for row in repaired_quotes)
    assert repaired_coverage[0]["supported"] is False
    assert "required concepts" in repaired_coverage[0]["reason"].lower()


def test_extract_for_query_keeps_analyst_entity_grounding_short_circuit_unchanged():
    module = load_step_module()

    query = {"id": "RAG-004B", "question": "What is Project Sunflower and what are the related diligence concerns?"}
    rerank_payload = {
        "ranked_candidates": [
            {
                "chunk_id": "c1",
                "doc_id": "AUR-DEAL-013",
                "text": "Diligence concerns discussed without mentioning the required project entity.",
            }
        ],
        "selection_config": {
            "anchor_gate_triggered": True,
            "entity_grounding_failed": True,
            "short_circuit_reason": "required_terms_zero_match_after_access_filter",
        },
    }

    result = module.extract_for_query(query, rerank_payload, model="gpt-test")

    assert result["quotes"] == []
    assert result["quote_extraction_source"] == "deterministic_no_accessible_evidence"
    assert any(row["field"] == "entity_grounding" and row["supported"] is False for row in result["evidence_coverage"])
