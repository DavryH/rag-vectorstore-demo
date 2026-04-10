import importlib.util
import sys
from pathlib import Path



def load_step5_module():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "steps" / "05-sparse-keyword-retrieval" / "run_step_05_sparse_keyword_retrieval.py"
    spec = importlib.util.spec_from_file_location("step05_run", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_required_terms_filter_blocks_cross_company_candidates(monkeypatch):
    module = load_step5_module()
    from shared.retrieval_pipeline import Chunk

    quantagrid_chunk = Chunk(
        chunk_id="quantagrid::chunk_0001",
        doc_id="quantagrid_q4_update",
        text="QuantaGrid ARR update and renewal metrics.",
        token_start=0,
        token_end=10,
        metadata={"tenant_id": "demo"},
    )
    kestrel_chunk = Chunk(
        chunk_id="kestrel::chunk_0001",
        doc_id="kestrel_soc2_email",
        text="Kestrel SOC2 certification email and compliance notes.",
        token_start=0,
        token_end=10,
        metadata={"tenant_id": "demo"},
    )

    monkeypatch.setattr(module, "load_chunks_for_tenant", lambda _tenant: [quantagrid_chunk, kestrel_chunk])

    quantagrid_plan = {
        "tenant_id": "demo",
        "original_query": "What did QuantaGrid say about SOC2?",
        "sparse_query": {
            "required_terms": ["quantagrid"],
            "include_terms": ["soc2"],
            "phrases": [],
            "exclude_terms": [],
        },
    }
    quantagrid_payload = module.build_sparse_retrieval_payload("Q-QUANTA", quantagrid_plan)

    assert [candidate["doc_id"] for candidate in quantagrid_payload["candidates"]][:1] == ["quantagrid_q4_update"]
    assert quantagrid_payload["candidates"][0]["required_terms_match"] is True
    assert "document_text" in quantagrid_payload["candidates"][0]
    assert "document_metadata" in quantagrid_payload["candidates"][0]

    kestrel_plan = {
        "tenant_id": "demo",
        "original_query": "What is Kestrel's SOC2 status?",
        "sparse_query": {
            "required_terms": ["kestrel"],
            "include_terms": ["soc2"],
            "phrases": [],
            "exclude_terms": [],
        },
    }
    kestrel_payload = module.build_sparse_retrieval_payload("Q-KESTREL", kestrel_plan)

    assert [candidate["doc_id"] for candidate in kestrel_payload["candidates"]][:1] == ["kestrel_soc2_email"]
    assert kestrel_payload["candidates"][0]["required_terms_match"] is True


def test_required_terms_zero_match_marks_entity_grounding_failure(monkeypatch):
    module = load_step5_module()
    from shared.retrieval_pipeline import Chunk

    unrelated_chunk = Chunk(
        chunk_id="other::chunk_0001",
        doc_id="other_doc",
        text="No company name appears in this chunk.",
        token_start=0,
        token_end=10,
        metadata={"tenant_id": "demo"},
    )

    monkeypatch.setattr(module, "load_chunks_for_tenant", lambda _tenant: [unrelated_chunk])

    query_plan = {
        "tenant_id": "demo",
        "original_query": "QuantaGrid update",
        "sparse_query": {
            "required_terms": ["quantagrid"],
            "include_terms": ["update"],
            "phrases": [],
            "exclude_terms": [],
        },
    }

    payload = module.build_sparse_retrieval_payload("Q-EMPTY", query_plan)

    assert payload["status"] == "ready_for_rerank"
    assert payload["required_terms_filter"]["required_terms_zero_match"] is True
    assert payload["required_terms_filter"]["no_accessible_required_term_match"] is True
    assert payload["entity_grounding"]["entity_grounding_failed"] is True
    assert payload["entity_grounding"]["short_circuit_reason"] == "required_terms_zero_match_after_access_filter"


def test_required_terms_zero_match_after_access_filter_with_confidential_excluded(monkeypatch):
    module = load_step5_module()
    from shared.retrieval_pipeline import Chunk

    accessible_chunk = Chunk(
        chunk_id="aur-deal::chunk_0001",
        doc_id="AUR-DEAL-013",
        text="Northwind Bio diligence concerns include concentration risk.",
        token_start=0,
        token_end=10,
        metadata={"tenant_id": "t_aurora", "sensitivity": "internal"},
    )
    confidential_chunk = Chunk(
        chunk_id="aur-secret::chunk_0001",
        doc_id="AUR-SECRET-001",
        text="Project Sunflower is an internal codename with diligence details.",
        token_start=0,
        token_end=10,
        metadata={"tenant_id": "t_aurora", "sensitivity": "confidential"},
    )

    monkeypatch.setattr(module, "load_chunks_for_tenant", lambda _tenant: [accessible_chunk, confidential_chunk])

    query_plan = {
        "tenant_id": "t_aurora",
        "role": "analyst",
        "original_query": "What is Project Sunflower and related diligence concerns?",
        "sparse_query": {
            "required_terms": ["project sunflower"],
            "include_terms": ["diligence", "concerns"],
            "phrases": [],
            "exclude_terms": [],
        },
    }

    payload = module.build_sparse_retrieval_payload("RAG-004B", query_plan)

    assert payload["access_filter"]["excluded_doc_ids"] == ["AUR-SECRET-001"]
    assert payload["required_terms_filter"]["required_terms_zero_match"] is True
    assert payload["entity_grounding"]["entity_grounding_failed"] is True


def test_required_terms_boundary_aware_single_token_does_not_match_substring():
    module = load_step5_module()
    annotated, _ = module.annotate_documents_with_required_terms(
        ranked_documents=[{"doc_id": "d1", "document_text": "We should concatenate these values.", "sparse_score": 1.0}],
        required_terms=["cat"],
    )
    assert annotated[0]["required_terms_match"] is False
    assert annotated[0]["required_terms_missing"] == ["cat"]


def test_required_terms_multi_word_phrase_exact_and_near_exact_behavior():
    module = load_step5_module()
    exact_match_docs = [{"doc_id": "d1", "document_text": "The PROJECT   sunflower initiative is active.", "sparse_score": 1.0}]
    exact_annotated, _ = module.annotate_documents_with_required_terms(
        ranked_documents=exact_match_docs,
        required_terms=["project sunflower"],
    )
    assert exact_annotated[0]["required_terms_match"] is True
    assert exact_annotated[0]["required_terms_missing"] == []

    near_exact_docs = [{"doc_id": "d2", "document_text": "The project sunflowers initiative is active.", "sparse_score": 1.0}]
    near_exact_annotated, _ = module.annotate_documents_with_required_terms(
        ranked_documents=near_exact_docs,
        required_terms=["project sunflower"],
    )
    assert near_exact_annotated[0]["required_terms_match"] is False
    assert near_exact_annotated[0]["required_terms_missing"] == ["project sunflower"]


def test_required_terms_punctuation_boundaries_match_single_token():
    module = load_step5_module()
    annotated, _ = module.annotate_documents_with_required_terms(
        ranked_documents=[{"doc_id": "d1", "document_text": "Kestrel, SOC2 controls are documented.", "sparse_score": 1.0}],
        required_terms=["kestrel"],
    )
    assert annotated[0]["required_terms_match"] is True
    assert annotated[0]["required_terms_missing"] == []


def test_required_terms_negative_control_substring_would_have_passed():
    module = load_step5_module()
    annotated, _ = module.annotate_documents_with_required_terms(
        ranked_documents=[{"doc_id": "d1", "document_text": "Sunflower diligence notes.", "sparse_score": 1.0}],
        required_terms=["sun"],
    )
    assert annotated[0]["required_terms_match"] is False
    assert annotated[0]["required_terms_missing"] == ["sun"]
