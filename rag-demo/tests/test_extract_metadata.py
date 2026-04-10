import importlib.util
import json
import sys
from pathlib import Path


def load_step_module():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "steps" / "01-extract-metadata" / "run_step_01_extract_metadata.py"
    spec = importlib.util.spec_from_file_location("step01_run", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_extract_all_metadata_with_mock_llm_uses_gold_schema():
    module = load_step_module()
    repo_root = Path(__file__).resolve().parents[1]
    expected_path = repo_root / "data" / "evals" / "expected_metadata.json"
    expected_rows = json.loads(expected_path.read_text(encoding="utf-8"))
    expected_by_doc_id = {row["doc_id"]: row for row in expected_rows}

    def mock_llm(relative_path: str, metadata_block: dict[str, str], document_text: str) -> dict:
        assert relative_path
        assert document_text
        doc_id = metadata_block.get("doc_id")
        assert doc_id in expected_by_doc_id
        return expected_by_doc_id[doc_id]

    rows, summary_lines = module.extract_all_metadata(llm_caller=mock_llm)

    assert len(rows) == len(expected_rows)
    assert summary_lines[0] == "# Step 01 Summary"
    assert any(line.startswith("- processing source file `") for line in summary_lines)
    assert any("sent the document text to the OpenAI LLM" in line for line in summary_lines)
    assert any(line.startswith("- extracted metadata: doc_id=") for line in summary_lines)
    assert any("appended one extraction record to `" in line and "extractions.jsonl" in line for line in summary_lines)
    assert any("removed explicit `[METADATA]...[/METADATA]` tags" in line for line in summary_lines)
    required_keys = {
        "doc_id",
        "tenant_id",
        "sensitivity",
        "doc_type",
        "date",
        "primary_company",
        "participants",
    }

    for row in rows:
        assert required_keys == set(row.keys())
        assert isinstance(row["participants"], list)
        for participant in row["participants"]:
            assert set(participant.keys()) == {"name", "email", "company", "role"}

    rows_by_doc_id = {row["doc_id"]: row for row in rows}
    for doc_id, row in rows_by_doc_id.items():
        expected = expected_by_doc_id[doc_id]
        assert row["doc_id"] == expected["doc_id"]
        assert row["tenant_id"] == expected["tenant_id"]
        assert row["sensitivity"] == expected["sensitivity"]
        assert row["doc_type"] == expected["doc_type"]
        assert row["date"] == expected["date"]
        assert row["primary_company"] == expected["primary_company"]
        assert row["participants"] == expected["participants"]


def test_remove_metadata_block_returns_clean_copy():
    module = load_step_module()
    text = """[METADATA]
doc_id=AUR-EMAIL-001
tenant_id=t_aurora
sensitivity=internal
[/METADATA]

Body line 1
Body line 2
"""

    cleaned = module.remove_metadata_block(text)

    assert "[METADATA]" not in cleaned
    assert "doc_id=AUR-EMAIL-001" not in cleaned
    assert cleaned.startswith("Body line 1")


def test_format_metadata_summary_compact_readable_line():
    module = load_step_module()
    row = {
        "doc_id": "AUR-EMAIL-001",
        "tenant_id": "t_aurora",
        "sensitivity": "internal",
        "doc_type": "email",
        "date": "2025-02-03",
        "primary_company": "Aurora",
        "participants": [{"name": "A", "email": "a@x", "company": "Aurora", "role": "mgr"}],
    }

    summary = module.format_metadata_summary(row)

    assert "doc_id=AUR-EMAIL-001" in summary
    assert "participants=1" in summary


def test_remove_metadata_block_without_metadata_preserves_leading_newlines():
    module = load_step_module()
    text = """

Title
Body
"""

    cleaned = module.remove_metadata_block(text)

    assert cleaned == text


def test_extract_all_metadata_clears_stale_cleaned_documents(tmp_path, monkeypatch):
    module = load_step_module()

    fake_input_dir = tmp_path / "inputs"
    fake_input_dir.mkdir()
    source_file = fake_input_dir / "doc.txt"
    source_file.write_text("""[METADATA]
doc_id=DOC-1
[/METADATA]

Body
""", encoding="utf-8")

    fake_extractions_path = tmp_path / "outputs" / "extractions.jsonl"
    cleaned_docs_dir = fake_extractions_path.parent / "cleaned_documents"
    cleaned_docs_dir.mkdir(parents=True, exist_ok=True)
    stale_file = cleaned_docs_dir / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    monkeypatch.setattr(module, "UNSTRUCTURED_DIR", fake_input_dir)
    monkeypatch.setattr(module, "EXTRACTIONS_PATH", fake_extractions_path)
    monkeypatch.setattr(module, "ROOT", tmp_path)

    rows, _summary = module.extract_all_metadata(
        llm_caller=lambda _relative_path, _metadata_block, _document_text: {
            "doc_id": "DOC-1",
            "tenant_id": "t",
            "sensitivity": "internal",
            "doc_type": "email",
            "date": "2025-01-01",
            "primary_company": "Aurora",
            "participants": [],
        }
    )

    assert len(rows) == 1
    assert not stale_file.exists()
    assert (cleaned_docs_dir / "doc.txt").exists()


def test_extract_all_metadata_sorts_rows_by_doc_id(tmp_path, monkeypatch):
    module = load_step_module()

    fake_input_dir = tmp_path / "inputs"
    fake_input_dir.mkdir()
    (fake_input_dir / "b_doc.txt").write_text("[METADATA]\ndoc_id=B\n[/METADATA]\nBody", encoding="utf-8")
    (fake_input_dir / "a_doc.txt").write_text("[METADATA]\ndoc_id=A\n[/METADATA]\nBody", encoding="utf-8")

    fake_root = tmp_path / "root"
    (fake_root / "data" / "evals").mkdir(parents=True, exist_ok=True)
    (fake_root / "data" / "evals" / "expected_metadata.json").write_text("[]", encoding="utf-8")
    fake_extractions_path = fake_root / "data" / "outputs" / "01-extract-metadata" / "extractions.jsonl"

    monkeypatch.setattr(module, "UNSTRUCTURED_DIR", fake_input_dir)
    monkeypatch.setattr(module, "EXTRACTIONS_PATH", fake_extractions_path)
    monkeypatch.setattr(module, "ROOT", fake_root)

    rows, _summary = module.extract_all_metadata(
        llm_caller=lambda relative_path, _metadata_block, _document_text: {
            "doc_id": "B" if relative_path == "b_doc.txt" else "A",
            "tenant_id": "t",
            "sensitivity": "internal",
            "doc_type": "email",
            "date": "2025-01-01",
            "primary_company": "Aurora",
            "participants": [],
        }
    )

    assert [row["doc_id"] for row in rows] == ["A", "B"]


def test_build_eval_section_reports_mismatch(tmp_path, monkeypatch):
    module = load_step_module()
    fake_root = tmp_path / "root"
    expected_path = fake_root / "data" / "evals" / "expected_metadata.json"
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.write_text(
        json.dumps(
            [
                {
                    "doc_id": "DOC-1",
                    "tenant_id": "t",
                    "sensitivity": "internal",
                    "doc_type": "email",
                    "date": "2025-01-01",
                    "primary_company": "Aurora",
                    "participants": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", fake_root)

    lines = module.build_eval_section(
        rows=[
            {
                "doc_id": "DOC-1",
                "tenant_id": "t",
                "sensitivity": "confidential",
                "doc_type": "email",
                "date": "2025-01-01",
                "primary_company": "Aurora",
                "participants": [],
            }
        ]
    )
    combined = "\n".join(lines)
    assert "metadata comparison failed" in combined
    assert "failed aspects" in combined
    assert "sensitivity" in combined
    assert "```json" in combined


def test_build_eval_section_reports_duplicate_doc_ids_in_output(tmp_path, monkeypatch):
    module = load_step_module()
    fake_root = tmp_path / "root"
    expected_path = fake_root / "data" / "evals" / "expected_metadata.json"
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.write_text(
        json.dumps(
            [
                {
                    "doc_id": "DOC-1",
                    "tenant_id": "t",
                    "sensitivity": "internal",
                    "doc_type": "email",
                    "date": "2025-01-01",
                    "primary_company": "Aurora",
                    "participants": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", fake_root)

    lines = module.build_eval_section(
        rows=[
            {
                "doc_id": "DOC-1",
                "tenant_id": "t",
                "sensitivity": "confidential",
                "doc_type": "email",
                "date": "2025-01-01",
                "primary_company": "Aurora",
                "participants": [],
            },
            {
                "doc_id": "DOC-1",
                "tenant_id": "t",
                "sensitivity": "internal",
                "doc_type": "email",
                "date": "2025-01-01",
                "primary_company": "Aurora",
                "participants": [],
            },
        ]
    )
    combined = "\n".join(lines)
    assert "metadata comparison failed" in combined
    assert "duplicate_doc_id_in_output" in combined
    assert "unexpected_doc_in_output[1]" in combined
    json_report = json.loads(combined.split("```json\n", 1)[1].split("\n```", 1)[0])
    doc_report = json_report["docs"][0]
    assert any(failed_aspect["aspect"] == "duplicate_doc_id_in_output" for failed_aspect in doc_report["failed_aspects"])


def test_build_eval_section_reports_participant_level_mismatch_details(tmp_path, monkeypatch):
    module = load_step_module()
    fake_root = tmp_path / "root"
    expected_path = fake_root / "data" / "evals" / "expected_metadata.json"
    expected_path.parent.mkdir(parents=True, exist_ok=True)
    expected_path.write_text(
        json.dumps(
            [
                {
                    "doc_id": "DOC-1",
                    "tenant_id": "t",
                    "sensitivity": "internal",
                    "doc_type": "email",
                    "date": "2025-01-01",
                    "primary_company": "Aurora",
                    "participants": [
                        {"name": "Alex", "company": "A", "email": "alex@example.com", "role": "CFO"},
                        {"name": "Priya", "company": "unknown", "email": "priya@example.com", "role": "unknown"},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", fake_root)

    lines = module.build_eval_section(
        rows=[
            {
                "doc_id": "DOC-1",
                "tenant_id": "t",
                "sensitivity": "internal",
                "doc_type": "email",
                "date": "2025-01-01",
                "primary_company": "Aurora",
                "participants": [
                    {"name": "Alex", "company": "A", "email": "alex@example.com", "role": "CFO"},
                    {"name": "Priya", "company": "Aurora", "email": "priya@example.com", "role": "unknown"},
                ],
            }
        ]
    )
    combined = "\n".join(lines)
    assert "participants[0]" in combined
    assert "participant_mismatches" in combined
    assert "\"participant_index\": 1" in combined
