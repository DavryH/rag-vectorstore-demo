import importlib.util
import hashlib
import json
import sys
from types import SimpleNamespace
from pathlib import Path


def load_step_module():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "steps" / "09-eval" / "run_step_09_eval.py"
    spec = importlib.util.spec_from_file_location("step09_run", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_deterministic_verdict_hard_fail_on_unsupported_claim():
    module = load_step_module()
    findings = {
        "query_requirements": [{"requirement_id": "r1", "text": "Give key fact", "critical": True}],
        "answer_claims": [{"claim_id": "c1", "text": "Unsupported fact", "substantive": True}],
        "requirement_results": [{"requirement_id": "r1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "ok"}],
        "claim_results": [{"claim_id": "c1", "status": "unsupported_inference", "evidence_quote_ids": [], "reason": "missing evidence"}],
        "hard_issues": [],
        "soft_issues": [],
    }

    verdict = module.deterministic_verdict(findings)

    assert verdict["verdict"] == "hard_fail"
    assert "no_unsupported_inference_claims" in verdict["reasons"]


def test_deterministic_verdict_pass_with_soft_warnings():
    module = load_step_module()
    findings = {
        "query_requirements": [{"requirement_id": "r1", "text": "Answer question", "critical": True}],
        "answer_claims": [{"claim_id": "c1", "text": "Correct answer", "substantive": True}],
        "requirement_results": [{"requirement_id": "r1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "semantically correct"}],
        "claim_results": [{"claim_id": "c1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "supported"}],
        "hard_issues": [],
        "soft_issues": [{"issue_type": "style", "detail": "Verbose but grounded", "related_ids": []}],
    }

    verdict = module.deterministic_verdict(findings)

    assert verdict["verdict"] == "pass"
    assert verdict["failed_tests"] == []


def test_deterministic_verdict_soft_fail_missing_central_expected_fact():
    module = load_step_module()
    findings = {
        "query_requirements": [{"requirement_id": "r1", "text": "Include central fact", "critical": True}],
        "answer_claims": [{"claim_id": "c1", "text": "Partially correct answer", "substantive": True}],
        "requirement_results": [{"requirement_id": "r1", "status": "unsupported_inference", "evidence_quote_ids": [], "reason": "central fact omitted"}],
        "claim_results": [{"claim_id": "c1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "supported"}],
        "hard_issues": [],
        "soft_issues": [{"issue_type": "material_incompleteness", "detail": "Missing central expected fact", "related_ids": ["r1"]}],
    }

    verdict = module.deterministic_verdict(findings)

    assert verdict["verdict"] == "soft_fail"
    assert "answer_materially_complete" in verdict["reasons"]


def test_deterministic_verdict_passes_no_evidence_absence_mode_on_unsupported_requirement():
    module = load_step_module()
    findings = {
        "query_requirements": [{"requirement_id": "r1", "text": "Confirm whether any docs are available", "critical": True}],
        "answer_claims": [{"claim_id": "c1", "text": "No accessible documents are available", "substantive": True}],
        "requirement_results": [{"requirement_id": "r1", "status": "unsupported_inference", "evidence_quote_ids": [], "reason": "No evidence available by design"}],
        "claim_results": [{"claim_id": "c1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "supported by absence-mode policy"}],
        "hard_issues": [],
        "soft_issues": [],
    }

    verdict = module.deterministic_verdict(findings, allow_no_evidence_absence_claims=True)

    assert verdict["verdict"] == "pass"
    assert verdict["failed_tests"] == []


def test_deterministic_verdict_hard_fail_when_supported_claim_missing_evidence():
    module = load_step_module()
    findings = {
        "query_requirements": [],
        "answer_claims": [],
        "requirement_results": [{"requirement_id": "r1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "ok"}],
        "claim_results": [{"claim_id": "c1", "status": "explicitly_supported", "evidence_quote_ids": [], "reason": "unsupported"}],
        "hard_issues": [],
        "soft_issues": [],
    }

    verdict = module.deterministic_verdict(findings)

    assert verdict["verdict"] == "hard_fail"
    assert "supported_claims_have_evidence" in verdict["reasons"]


def test_assess_citation_policy_subset_extra_citation_only_warns():
    module = load_step_module()
    query = {"id": "RAG-003A", "tenant_id": "t_aurora", "role": "analyst"}
    result = module.assess_citation_policy(
        citation_policy="subset",
        query=query,
        returned_citations=["AUR-MEET-002", "AUR-EMAIL-001"],
        expected_citations=["AUR-MEET-002"],
        supporting_quotes=[
            {"quote_id": "q1", "doc_id": "AUR-MEET-002", "text": "...", "resolver_context": "", "display_snippet": ""},
            {"quote_id": "q2", "doc_id": "AUR-EMAIL-001", "text": "...", "resolver_context": "", "display_snippet": ""},
        ],
        doc_metadata={
            "AUR-MEET-002": {"tenant_id": "t_aurora", "sensitivity": "internal"},
            "AUR-EMAIL-001": {"tenant_id": "t_aurora", "sensitivity": "internal"},
        },
        rerank_payload={"ranked_candidates": [{"doc_id": "AUR-MEET-002"}, {"doc_id": "AUR-EMAIL-001"}]},
    )

    assert result["hard_issues"] == []
    assert any(issue["issue_type"] == "unexpected_returned_citations" for issue in result["soft_issues"])


def test_deterministic_verdict_rejects_empty_result_arrays():
    module = load_step_module()
    findings = {
        "query_requirements": [],
        "answer_claims": [],
        "requirement_results": [],
        "claim_results": [],
        "hard_issues": [],
        "soft_issues": [],
    }

    try:
        module.deterministic_verdict(findings)
        assert False, "Expected RuntimeError for empty arrays"
    except RuntimeError as exc:
        assert "must not be empty" in str(exc)


def test_main_dry_run_writes_eval_rows(tmp_path, monkeypatch):
    module = load_step_module()

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(
        json.dumps([{"id": "MVP-001", "question": "q1"}]),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)
    monkeypatch.setattr(module, "STEP7_DIR", tmp_path / "07-extract-quotes")
    monkeypatch.setattr(module, "STEP8_DIR", tmp_path / "08-answer")
    monkeypatch.setattr(module, "STEP9_DIR", tmp_path / "09-eval")

    (tmp_path / "07-extract-quotes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "07-extract-quotes" / "quote-extraction.jsonl").write_text(
        json.dumps({"query_id": "MVP-001", "quotes": [{"doc_id": "DOC-1", "quote": "quoted text"}]}) + "\n",
        encoding="utf-8",
    )

    (tmp_path / "08-answer").mkdir(parents=True, exist_ok=True)
    (tmp_path / "08-answer" / "answer.jsonl").write_text(
        json.dumps({"query_id": "MVP-001", "answer": "answer text"}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["run_step.py", "--all-queries", "--dry-run"])

    module.main()

    out_path = tmp_path / "09-eval" / "answer-eval.jsonl"
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["query_id"] == "MVP-001"
    assert rows[0]["verdict"] == "pass"
    assert isinstance(rows[0]["hard_tests"], list)
    assert isinstance(rows[0]["soft_tests"], list)


def test_main_dry_run_skips_explicitly_halted_step08_rows(tmp_path, monkeypatch):
    module = load_step_module()

    query_eval_path = tmp_path / "query_eval.json"
    query_eval_path.write_text(
        json.dumps([{"id": "MVP-001", "question": "q1"}]),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "QUERY_EVAL_PATH", query_eval_path)
    monkeypatch.setattr(module, "STEP7_DIR", tmp_path / "07-extract-quotes")
    monkeypatch.setattr(module, "STEP8_DIR", tmp_path / "08-answer")
    monkeypatch.setattr(module, "STEP9_DIR", tmp_path / "09-eval")

    (tmp_path / "07-extract-quotes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "07-extract-quotes" / "quote-extraction.jsonl").write_text(
        json.dumps({"query_id": "MVP-001", "quotes": [{"doc_id": "DOC-1", "quote": "quoted text"}]}) + "\n",
        encoding="utf-8",
    )

    (tmp_path / "08-answer").mkdir(parents=True, exist_ok=True)
    (tmp_path / "08-answer" / "answer.jsonl").write_text(
        json.dumps(
            {
                "query_id": "MVP-001",
                "answer": "",
                "status": "halted_error",
                "error_type": "RuntimeError",
                "error_message": "synthetic failure",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["run_step.py", "--all-queries", "--dry-run"])

    module.main()

    out_path = tmp_path / "09-eval" / "answer-eval.jsonl"
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["query_id"] == "MVP-001"
    assert rows[0]["verdict"] == "hard_fail"
    assert rows[0]["eval_source"] == "skipped_due_to_upstream_error"
    assert rows[0]["failed_tests"] == ["upstream_query_halted"]


def test_is_step08_halted_defaults_missing_status_to_ready_for_eval():
    module = load_step_module()

    assert module.is_step08_halted({"query_id": "MVP-001", "answer": "ok"}) is False
    assert module.is_step08_halted({"status": ""}) is False
    assert module.is_step08_halted({"status": "ready_for_eval"}) is False
    assert module.is_step08_halted({"status": "halted_error"}) is True


def test_build_supporting_quotes_payload_drops_placeholder_rows():
    module = load_step_module()
    payload = module.build_supporting_quotes_payload(
        [
            {"quote_id": "q1", "doc_id": "DOC-1", "text": "quoted", "resolver_context": "", "display_snippet": ""},
            {"quote_id": "", "doc_id": "DOC-2", "text": "quoted", "resolver_context": "", "display_snippet": ""},
            {"quote_id": "q3", "doc_id": "", "text": "quoted", "resolver_context": "", "display_snippet": ""},
            {"quote_id": "q4", "doc_id": "DOC-4", "text": "   ", "resolver_context": "", "display_snippet": ""},
        ]
    )

    assert payload == [
        {
            "quote_id": "q1",
            "doc_id": "DOC-1",
            "quote_text": "quoted",
            "resolver_context": "",
            "display_snippet": "",
            "doc_date": "",
            "timeline_milestone": "",
        }
    ]


def test_evaluate_with_llm_uses_filtered_quote_ids_for_evidence_normalization(monkeypatch):
    module = load_step_module()

    structured_payload = {
        "query_requirements": [{"requirement_id": "r1", "text": "Answer directly", "critical": True}],
        "answer_claims": [{"claim_id": "c1", "text": "Generated answer", "substantive": True}],
        "requirement_results": [
            {"requirement_id": "r1", "status": "explicitly_supported", "evidence_quote_ids": ["q2"], "reason": "model cited q2"}
        ],
        "claim_results": [
            {"claim_id": "c1", "status": "explicitly_supported", "evidence_quote_ids": ["q2"], "reason": "model cited q2"}
        ],
        "hard_issues": [],
        "soft_issues": [],
    }

    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(structured_payload)))]
    )

    monkeypatch.setattr(module, "get_openai_client", lambda: object())
    monkeypatch.setattr(module, "create_chat_completion", lambda client, payload: fake_response)

    findings = module.evaluate_with_llm(
        model="gpt-4o-mini",
        query_id="Q-1",
        original_query="What happened?",
        expected_answer="Expected",
        generated_answer="Generated",
        supporting_quotes=[
            {"quote_id": "q1", "doc_id": "DOC-1", "text": "valid quote"},
            {"quote_id": "q2", "doc_id": "", "text": "missing doc id should be filtered"},
        ],
        expected_facts=[],
        forbidden_claims=[],
    )

    requirement_row = findings["requirement_results"][0]
    claim_row = findings["claim_results"][0]

    assert requirement_row["status"] == "unsupported_inference"
    assert requirement_row["evidence_quote_ids"] == []
    assert claim_row["status"] == "unsupported_inference"
    assert claim_row["evidence_quote_ids"] == []


def test_build_summary_humanizes_reasons_and_lists_issue_details():
    module = load_step_module()
    rows = [
        {
            "query_id": "MVP-003",
            "verdict": "soft_fail",
            "verdict_reasons": ["answer_materially_complete"],
            "findings": {
                "hard_issues": [],
                "soft_issues": [
                    {
                        "issue_type": "minor_ambiguity",
                        "detail": "The document states Priya Singh will coordinate next steps and can be treated as the primary point of contact, but does not explicitly label her role or title.",
                        "related_ids": ["r2", "c2"],
                    }
                ],
            },
            "hard_tests": [],
            "soft_tests": [
                {"test": "answer_materially_complete", "status": "fail", "detail": "Critical query requirements should be sufficiently answered, allowing semantic paraphrase."}
            ],
        }
    ]

    summary = module.build_summary(rows)

    assert "- verdict reasons: `Answer is materially incomplete for the question (fail)`" in summary
    assert "- summary:" in summary
    assert "soft issue details" in summary
    assert "Minor ambiguity: The document states Priya Singh will coordinate next steps" in summary
    assert "[related: r2, c2]" in summary


def test_readable_test_reason_keeps_na_status_humanized():
    module = load_step_module()

    readable = module.readable_test_reason("soft_issues_present", "n/a")

    assert readable == "Soft issues present"


def test_write_failure_traces_creates_step_chain_markdown(tmp_path, monkeypatch):
    module = load_step_module()
    monkeypatch.setattr(module, "STEP9_DIR", tmp_path / "09-eval")

    rows = [
        {
            "query_id": "MVP-404",
            "verdict": "hard_fail",
            "verdict_reasons": ["no_contradicted_claims"],
            "expected_citations": ["DOC-EXPECTED"],
            "returned_citations": ["DOC-OTHER"],
            "findings": {
                "hard_issues": [
                    {
                        "issue_type": "citation_mismatch",
                        "detail": "Expected DOC-EXPECTED but got DOC-OTHER",
                        "related_ids": ["DOC-EXPECTED", "DOC-OTHER"],
                    }
                ],
                "soft_issues": [],
            },
            "hard_tests": [{"test": "no_contradicted_claims", "status": "fail", "detail": "..."}],
            "soft_tests": [],
        }
    ]

    module.write_failure_traces(
        rows=rows,
        step3_by_id={"MVP-404": {"query_id": "MVP-404", "rewritten_query": "r"}},
        step4_by_id={"MVP-404": {"query_id": "MVP-404", "candidates": [{"doc_id": "DOC-ALT"}]}},
        step5_by_id={"MVP-404": {"query_id": "MVP-404", "candidates": [{"doc_id": "DOC-ALT"}]}},
        step6_by_id={"MVP-404": {"query_id": "MVP-404", "ranked_candidates": [{"doc_id": "DOC-ALT"}]}},
        step7_by_id={"MVP-404": {"query_id": "MVP-404", "quotes": [{"doc_id": "DOC-ALT", "quote": "q"}]}},
        step8_by_id={"MVP-404": {"query_id": "MVP-404", "answer": "a", "citations": ["DOC-OTHER"]}},
    )

    expected_name = f"MVP-404-{hashlib.sha1('MVP-404'.encode('utf-8')).hexdigest()[:8]}.md"
    assert rows[0]["failure_trace_path"] == f"failure-traces/{expected_name}"
    trace_path = tmp_path / "09-eval" / "failure-traces" / expected_name
    assert trace_path.exists()
    trace_text = trace_path.read_text(encoding="utf-8")
    assert "## Step 03 — Query Rewrite + Sparse Plan" in trace_text
    assert "## Step 08 — Answer" in trace_text
    assert "## Deviation Analysis (Step 03 → Step 08)" in trace_text
    assert "## Suspected Source of Failure" in trace_text
    assert "fault likely occurs by Step 06" in trace_text


def test_write_failure_traces_sanitizes_query_id_for_trace_filename(tmp_path, monkeypatch):
    module = load_step_module()
    monkeypatch.setattr(module, "STEP9_DIR", tmp_path / "09-eval")

    rows = [
        {
            "query_id": "../unsafe/path",
            "verdict": "hard_fail",
            "verdict_reasons": ["no_contradicted_claims"],
            "expected_citations": [],
            "returned_citations": [],
            "findings": {"hard_issues": [], "soft_issues": []},
            "hard_tests": [],
            "soft_tests": [],
        }
    ]

    module.write_failure_traces(
        rows=rows,
        step3_by_id={},
        step4_by_id={},
        step5_by_id={},
        step6_by_id={},
        step7_by_id={},
        step8_by_id={},
    )

    expected_name = f"unsafe_path-{hashlib.sha1('../unsafe/path'.encode('utf-8')).hexdigest()[:8]}.md"
    assert rows[0]["failure_trace_path"] == f"failure-traces/{expected_name}"
    assert (tmp_path / "09-eval" / "failure-traces" / expected_name).exists()


def test_deterministic_verdict_passes_no_evidence_absence_mode_on_unsupported_claim():
    module = load_step_module()
    findings = {
        "query_requirements": [{"requirement_id": "r1", "text": "Confirm no accessible docs", "critical": True}],
        "answer_claims": [{"claim_id": "c1", "text": "No accessible documents mention Project Sunflower", "substantive": True}],
        "requirement_results": [{"requirement_id": "r1", "status": "unsupported_inference", "evidence_quote_ids": [], "reason": "No evidence available by design"}],
        "claim_results": [{"claim_id": "c1", "status": "unsupported_inference", "evidence_quote_ids": [], "reason": "No evidence available by design"}],
        "hard_issues": [],
        "soft_issues": [],
    }

    verdict = module.deterministic_verdict(findings, allow_no_evidence_absence_claims=True)

    assert verdict["verdict"] == "pass"
    assert verdict["failed_tests"] == []


def test_deterministic_verdict_no_evidence_absence_mode_still_fails_non_absence_unsupported_claim():
    module = load_step_module()
    findings = {
        "query_requirements": [{"requirement_id": "r1", "text": "Confirm whether any docs are available", "critical": True}],
        "answer_claims": [
            {"claim_id": "c1", "text": "No accessible documents are available", "substantive": True},
            {"claim_id": "c2", "text": "Project Sunflower launched in 2024", "substantive": True},
        ],
        "requirement_results": [{"requirement_id": "r1", "status": "unsupported_inference", "evidence_quote_ids": [], "reason": "No evidence available by design"}],
        "claim_results": [
            {"claim_id": "c1", "status": "unsupported_inference", "evidence_quote_ids": [], "reason": "No evidence available by design"},
            {"claim_id": "c2", "status": "unsupported_inference", "evidence_quote_ids": [], "reason": "missing evidence"},
        ],
        "hard_issues": [],
        "soft_issues": [],
    }

    verdict = module.deterministic_verdict(findings, allow_no_evidence_absence_claims=True)

    assert verdict["verdict"] == "hard_fail"
    assert "no_unsupported_inference_claims" in verdict["failed_tests"]


def test_merge_forbidden_claim_aliases_includes_forbidden_facts():
    module = load_step_module()

    merged = module.merge_forbidden_claim_aliases(
        {
            "forbidden_claims": ["OmniDynamics", "customer concentration of 38%"],
            "forbidden_facts": ["customer concentration of 38%", "Project Sunflower is an internal codename"],
        }
    )

    assert merged == [
        "OmniDynamics",
        "customer concentration of 38%",
        "Project Sunflower is an internal codename",
    ]


def test_normalize_supporting_quotes_preserves_timeline_metadata():
    module = load_step_module()

    normalized = module.normalize_supporting_quotes(
        {
            "quotes": [
                {
                    "quote_id": "q1",
                    "doc_id": "DOC-1",
                    "quote": "Intro happened.",
                    "resolver_context": "ctx",
                    "display_snippet": "snippet",
                    "doc_date": "2025-11-12",
                    "timeline_milestone": "intro_contact",
                }
            ]
        }
    )

    assert normalized == [
        {
            "quote_id": "q1",
            "doc_id": "DOC-1",
            "text": "Intro happened.",
            "resolver_context": "ctx",
            "display_snippet": "snippet",
            "doc_date": "2025-11-12",
            "timeline_milestone": "intro_contact",
        }
    ]


def test_remove_hallucinated_hard_issues_discards_issue_not_tied_to_generated_claim():
    module = load_step_module()

    filtered, discarded_reasons = module.remove_hallucinated_hard_issues(
        answer_claims=[
            {"claim_id": "c1", "text": "A concise timeline summary without any exact intro date.", "substantive": True}
        ],
        hard_issues=[
            {
                "issue_type": "unsupported_substantive_claim",
                "detail": "Claim c2 says the intro occurred on 2025-11-12.",
                "related_ids": ["c2"],
            }
        ],
    )

    assert filtered == []
    assert discarded_reasons == ["referenced claim ID does not exist"]


def test_remove_hallucinated_hard_issues_keeps_valid_unsupported_claim_issue():
    module = load_step_module()

    filtered, discarded_reasons = module.remove_hallucinated_hard_issues(
        answer_claims=[
            {"claim_id": "c1", "text": "The intro occurred on 2025-11-12.", "substantive": True}
        ],
        hard_issues=[
            {
                "issue_type": "unsupported_substantive_claim",
                "detail": "Claim c1 is unsupported.",
                "related_ids": ["c1"],
            }
        ],
    )

    assert filtered == [
        {
            "issue_type": "unsupported_substantive_claim",
            "detail": "Claim c1 is unsupported.",
            "related_ids": ["c1"],
        }
    ]
    assert discarded_reasons == []


def test_remove_hallucinated_hard_issues_does_not_use_detail_overlap_without_claim_mapping():
    module = load_step_module()

    filtered, discarded_reasons = module.remove_hallucinated_hard_issues(
        answer_claims=[
            {"claim_id": "c1", "text": "Revenue was $2M in 2025.", "substantive": True}
        ],
        hard_issues=[
            {
                "issue_type": "unsupported_substantive_claim",
                "detail": "Revenue was $2M in 2025.",
                "related_ids": [],
            }
        ],
    )

    assert filtered == []
    assert discarded_reasons == ["missing related claim IDs"]


def test_deterministic_verdict_ignores_non_blocking_hard_issue_when_claims_are_supported():
    module = load_step_module()
    findings = {
        "query_requirements": [{"requirement_id": "r1", "text": "Summarize timeline", "critical": True}],
        "answer_claims": [{"claim_id": "c1", "text": "Supported summary", "substantive": True}],
        "requirement_results": [{"requirement_id": "r1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "ok"}],
        "claim_results": [{"claim_id": "c1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "ok"}],
        "hard_issues": [{"issue_type": "unsupported_substantive_claim", "detail": "Bad LLM row", "related_ids": ["c1"]}],
        "soft_issues": [],
    }

    verdict = module.deterministic_verdict(findings)

    assert verdict["verdict"] == "pass"
    no_hard_issues = next(test for test in verdict["hard_tests"] if test["test"] == "no_hard_issues")
    assert no_hard_issues["status"] == "pass"




def test_deterministic_verdict_fails_unknown_hard_issue_type():
    module = load_step_module()
    findings = {
        "query_requirements": [{"requirement_id": "r1", "text": "Summarize timeline", "critical": True}],
        "answer_claims": [{"claim_id": "c1", "text": "Supported summary", "substantive": True}],
        "requirement_results": [{"requirement_id": "r1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "ok"}],
        "claim_results": [{"claim_id": "c1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "ok"}],
        "hard_issues": [{"issue_type": "forbidden_claim_policy_violation", "detail": "Policy violation", "related_ids": ["c1"]}],
        "soft_issues": [],
    }

    verdict = module.deterministic_verdict(findings)

    assert verdict["verdict"] == "hard_fail"
    no_hard_issues = next(test for test in verdict["hard_tests"] if test["test"] == "no_hard_issues")
    assert no_hard_issues["status"] == "fail"


def test_run_for_query_preserves_deterministic_citation_hard_issues(monkeypatch):
    module = load_step_module()

    monkeypatch.setattr(
        module,
        "evaluate_with_llm",
        lambda **_: {
            "query_requirements": [{"requirement_id": "r1", "text": "Answer", "critical": True}],
            "answer_claims": [{"claim_id": "c1", "text": "Summary from DOC-A.", "substantive": True}],
            "requirement_results": [{"requirement_id": "r1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "ok"}],
            "claim_results": [{"claim_id": "c1", "status": "explicitly_supported", "evidence_quote_ids": ["q1"], "reason": "ok"}],
            "hard_issues": [{"issue_type": "unsupported_substantive_claim", "detail": "Hallucinated c2", "related_ids": ["c2"]}],
            "soft_issues": [],
        },
    )

    result = module.run_for_query(
        query={
            "id": "Q1",
            "question": "What happened?",
            "expected_answer": "Summary.",
            "citations": ["DOC-B"],
            "citation_policy": "exact",
            "tenant_id": "tenant-a",
            "role": "analyst",
        },
        answer_payload={"answer": "Summary from DOC-A.", "citations": ["DOC-A"]},
        quote_payload={"quotes": [{"quote_id": "q1", "doc_id": "DOC-A", "quote": "Summary from DOC-A."}]},
        rerank_payload={"ranked_candidates": [{"doc_id": "DOC-A"}, {"doc_id": "DOC-B"}]},
        doc_metadata={"DOC-A": {"tenant_id": "tenant-a", "acl": ["analyst"]}, "DOC-B": {"tenant_id": "tenant-a", "acl": ["analyst"]}},
        model="gpt-4o-mini",
        dry_run=False,
        default_citation_policy="exact",
    )

    hard_types = {issue["issue_type"] for issue in result["findings"]["hard_issues"]}
    assert hard_types.intersection({
        "missing_expected_citation_not_retrieved",
        "missing_expected_citation_not_used",
        "returned_citation_not_in_supporting_quotes",
        "exact_policy_extra_citations",
    })
    assert "unsupported_substantive_claim" not in hard_types
    assert result["verdict"] == "hard_fail"

def test_build_summary_includes_question_line():
    module = load_step_module()
    rows = [
        {
            "query_id": "MVP-010",
            "question": "What is Project Sunflower and what are the diligence concerns?",
            "verdict": "pass",
            "verdict_reasons": [],
            "failed_tests": [],
            "expected_answer": "No accessible documents at the analyst permission level mention Project Sunflower.",
            "answer": "No accessible documents at the analyst permission level mention Project Sunflower.",
            "findings": {"hard_issues": [], "soft_issues": []},
            "hard_tests": [],
            "soft_tests": [],
        }
    ]

    summary = module.build_summary(rows)

    assert "- question: `What is Project Sunflower and what are the diligence concerns?`" in summary


def test_build_failure_trace_includes_question_line():
    module = load_step_module()
    row = {
        "query_id": "MVP-011",
        "question": "Who is the point of contact?",
        "verdict": "hard_fail",
        "failed_tests": ["no_hard_issues"],
        "expected_answer": "Priya Singh.",
        "answer": "No answer.",
        "expected_citations": [],
        "returned_citations": [],
        "missing_expected_citations": [],
        "unexpected_returned_citations": [],
        "findings": {"hard_issues": [], "soft_issues": []},
        "hard_tests": [{"test": "no_hard_issues", "status": "fail", "detail": "x"}],
        "soft_tests": [],
    }

    trace = module.build_failure_trace_markdown(
        row=row,
        step3_payload=None,
        step4_payload=None,
        step5_payload=None,
        step6_payload=None,
        step7_payload=None,
        step8_payload=None,
    )

    assert "- question: `Who is the point of contact?`" in trace
