import importlib.util
import sys
from pathlib import Path


def load_step_module():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "steps" / "06-rerank" / "run_step_06_rerank.py"
    spec = importlib.util.spec_from_file_location("step06_run", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_step03_module():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "steps" / "03-query-rewrite-and-sparse-query" / "run_step_03_query_rewrite_and_sparse_query.py"
    spec = importlib.util.spec_from_file_location("step03_run", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_rerank_flow_prioritizes_company_matching_evidence():
    module = load_step_module()

    query_plan = {
        "original_query": "Is SOC2 Type II completed for Kestrel? If yes, when was it confirmed?",
        "sparse_query": {"required_terms": ["kestrel"]},
        "company_scope_terms": ["kestrel"],
    }
    semantic_candidates = [
        {
            "chunk_id": "A::chunk_0000",
            "doc_id": "BIR-EMAIL-005",
            "text": "Kestrel SOC2 Type II completed and confirmed on 2026-02-10.",
            "metadata": {"date": "2026-02-10"},
            "semantic_rank": 2,
        },
        {
            "chunk_id": "B::chunk_0000",
            "doc_id": "BIR-EMAIL-008",
            "text": "QuantaGrid follow-up planned for next week.",
            "metadata": {"date": "2026-02-12"},
            "semantic_rank": 1,
        },
    ]
    sparse_candidates = [
        {
            "doc_id": "BIR-EMAIL-005",
            "document_text": "Kestrel SOC2 Type II completed and confirmed on 2026-02-10.",
            "document_metadata": {"date": "2026-02-10"},
            "sparse_rank": 1,
            "sparse_score": 5.0,
        },
        {
            "doc_id": "BIR-EMAIL-008",
            "document_text": "QuantaGrid follow-up planned for next week.",
            "document_metadata": {"date": "2026-02-12"},
            "sparse_rank": 2,
            "sparse_score": 2.0,
        },
    ]

    row = module.rerank_for_query(
        query_id="MVP-RERANK-001",
        semantic_row={"input_query_plan": query_plan, "candidates": semantic_candidates},
        sparse_row={"candidates": sparse_candidates},
    )

    ranked = row["ranked_candidates"]
    assert ranked[0]["doc_id"] == "BIR-EMAIL-005"
    assert ranked[0]["company_match"] is True
    assert ranked[0]["parent_sparse_rank"] == 1
    assert ranked[0]["deterministic_score"] >= ranked[1]["deterministic_score"]


def test_rerank_flow_recency_promotes_latest_term_sheet():
    module = load_step_module()

    query_plan = {
        "original_query": "What is Helio's latest term sheet valuation and board rights?",
        "sparse_query": {"required_terms": ["helio"]},
    }
    semantic_candidates = [
        {
            "chunk_id": "A::chunk_0000",
            "doc_id": "AUR-EMAIL-008",
            "text": "Helio latest term sheet valuation is $82M with board observer rights.",
            "metadata": {"date": "2026-01-15"},
            "semantic_rank": 2,
        },
        {
            "chunk_id": "B::chunk_0000",
            "doc_id": "AUR-EMAIL-004",
            "text": "Helio most recent ARR is $4.8M and gross churn is 2.1%.",
            "metadata": {"date": "2025-10-30"},
            "semantic_rank": 1,
        },
    ]
    sparse_candidates = [
        {
            "doc_id": "AUR-EMAIL-008",
            "document_text": "Helio latest term sheet valuation is $82M with board observer rights.",
            "document_metadata": {"date": "2026-01-15"},
            "sparse_rank": 1,
            "sparse_score": 4.0,
        },
        {
            "doc_id": "AUR-EMAIL-004",
            "document_text": "Helio most recent ARR is $4.8M and gross churn is 2.1%.",
            "document_metadata": {"date": "2025-10-30"},
            "sparse_rank": 2,
            "sparse_score": 1.0,
        },
    ]

    row = module.rerank_for_query(
        query_id="MVP-RERANK-002",
        semantic_row={"input_query_plan": query_plan, "candidates": semantic_candidates},
        sparse_row={"candidates": sparse_candidates},
    )

    ranked = row["ranked_candidates"]
    assert ranked[0]["doc_id"] == "AUR-EMAIL-008"
    assert ranked[0]["recency_score"] == 1.0
    assert ranked[0]["parent_sparse_rank"] == 1
    assert ranked[0]["deterministic_score"] >= ranked[1]["deterministic_score"]


def test_rerank_flow_accepts_legacy_dense_candidates_without_dense_candidate_id():
    module = load_step_module()

    query_plan = {
        "original_query": "What did Kestrel announce?",
        "sparse_query": {"required_terms": ["kestrel"]},
    }
    semantic_candidates = [
        {
            "chunk_id": "A::chunk_0000",
            "doc_id": "BIR-EMAIL-005",
            "text": "Kestrel announced SOC2 completion.",
            "metadata": {"date": "2026-02-10"},
            "semantic_rank": 1,
        }
    ]
    sparse_candidates = [
        {
            "doc_id": "BIR-EMAIL-005",
            "document_text": "Kestrel announced SOC2 completion.",
            "document_metadata": {"date": "2026-02-10"},
            "sparse_rank": 1,
            "sparse_score": 3.0,
            "required_terms_match": True,
        }
    ]

    row = module.rerank_for_query(
        query_id="MVP-RERANK-LEGACY-001",
        semantic_row={"input_query_plan": query_plan, "candidates": semantic_candidates},
        sparse_row={"candidates": sparse_candidates},
    )

    ranked = row["ranked_candidates"]
    assert len(ranked) == 1
    assert ranked[0]["dense_candidate_id"].startswith("legacy_densecand_")


def test_provenance_scope_regression_keeps_entity_candidate_even_when_step05_has_zero_required_match():
    step03 = load_step03_module()
    module = load_step_module()

    original_query = "Who is Alex Chen in Birch's records, and what company is he associated with?"
    sanitized_sparse_query = step03.sanitize_sparse_query(
        original_query,
        {
            "required_terms": ["alex chen", "birch"],
            "include_terms": ["alex chen", "birch", "company"],
            "phrases": ["alex chen"],
            "exclude_terms": [],
        },
    )
    assert sanitized_sparse_query["required_terms"] == ["alex chen"]

    query_plan = {
        "original_query": original_query,
        "sparse_query": sanitized_sparse_query,
    }
    semantic_candidates = [
        {
            "chunk_id": "A::chunk_0000",
            "doc_id": "BIR-CRM-001",
            "text": "Alex Chen is associated with QuantaGrid.",
            "metadata": {"date": "2026-01-01"},
            "semantic_rank": 1,
        }
    ]
    sparse_candidates = [
        {
            "doc_id": "BIR-CRM-001",
            "document_text": "Alex Chen is associated with QuantaGrid.",
            "document_metadata": {"date": "2026-01-01"},
            "sparse_rank": 1,
            "sparse_score": 2.9,
            "required_terms_match": True,
        }
    ]

    row = module.rerank_for_query(
        query_id="RAG-004B",
        semantic_row={"input_query_plan": query_plan, "candidates": semantic_candidates},
        sparse_row={
            "candidates": sparse_candidates,
            "access_filter": {"applied": True},
            "required_terms_filter": {"required_terms": ["alex chen"], "required_terms_zero_match": True},
        },
    )

    assert row["status"] == "ready_for_quote_extraction"
    assert row["ranked_candidates"][0]["doc_id"] == "BIR-CRM-001"
    assert row["selection_config"]["anchor_gate_triggered"] is False


def test_rerank_drops_generic_candidate_without_entity_link():
    module = load_step_module()

    query_plan = {
        "original_query": "What are Project Sunflower diligence concerns?",
        "sparse_query": {"required_terms": ["project sunflower"]},
    }
    semantic_candidates = [
        {
            "chunk_id": "A::chunk_0000",
            "doc_id": "AUR-DEAL-013",
            "text": "Diligence concerns and deal issues for Northwind Bio.",
            "metadata": {"date": "2026-01-01"},
            "semantic_rank": 1,
        }
    ]
    sparse_candidates = [
        {
            "doc_id": "AUR-DEAL-013",
            "document_text": "Diligence concerns and deal issues for Northwind Bio.",
            "document_metadata": {"date": "2026-01-01", "primary_company": "Northwind Bio"},
            "sparse_rank": 1,
            "sparse_score": 2.0,
            "required_terms_match": False,
        }
    ]

    row = module.rerank_for_query(
        query_id="RAG-GENERIC-NEG",
        semantic_row={"input_query_plan": query_plan, "candidates": semantic_candidates},
        sparse_row={"candidates": sparse_candidates, "required_terms_filter": {"required_terms": ["project sunflower"]}},
    )

    assert row["ranked_candidates"] == []


def test_rerank_keeps_candidate_when_required_entity_is_explicitly_present():
    module = load_step_module()

    query_plan = {
        "original_query": "What are Project Sunflower diligence concerns?",
        "sparse_query": {"required_terms": ["project sunflower"]},
    }
    semantic_candidates = [
        {
            "chunk_id": "A::chunk_0000",
            "doc_id": "AUR-EMAIL-999",
            "text": "Project Sunflower diligence concern: customer concentration in top two accounts.",
            "metadata": {"date": "2026-01-02"},
            "semantic_rank": 1,
        }
    ]
    sparse_candidates = [
        {
            "doc_id": "AUR-EMAIL-999",
            "document_text": "Project Sunflower diligence concern: customer concentration in top two accounts.",
            "document_metadata": {"date": "2026-01-02"},
            "sparse_rank": 1,
            "sparse_score": 4.4,
            "required_terms_match": True,
        }
    ]

    row = module.rerank_for_query(
        query_id="RAG-GENERIC-POS",
        semantic_row={"input_query_plan": query_plan, "candidates": semantic_candidates},
        sparse_row={"candidates": sparse_candidates},
    )

    assert len(row["ranked_candidates"]) == 1
    assert row["ranked_candidates"][0]["doc_id"] == "AUR-EMAIL-999"
