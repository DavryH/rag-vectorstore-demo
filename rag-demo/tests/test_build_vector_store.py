import importlib.util
import sys
from pathlib import Path


def load_step_module():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "steps" / "02-build-vector-store" / "run_step_02_build_vector_store.py"
    spec = importlib.util.spec_from_file_location("step02_run", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_vector_store_attributes_keeps_core_fields_and_participants():
    module = load_step_module()
    metadata = {
        "doc_id": "DOC-1",
        "tenant_id": "t_aurora",
        "sensitivity": "internal",
        "doc_type": "email",
        "date": "2025-01-02",
        "primary_company": "Aurora",
        "participants": [
            {"name": "Ari Stone", "email": "a@example.com", "company": "Aurora", "role": "PM"},
            {"name": module.UNKNOWN_STRING, "email": "u@example.com", "company": "Aurora", "role": "NA"},
        ],
    }

    attrs = module.build_vector_store_attributes(metadata)

    assert attrs["doc_id"] == "DOC-1"
    assert attrs["tenant_id"] == "t_aurora"
    assert attrs["primary_company"] == "Aurora"
    assert attrs["participants"] == "Ari Stone"


def test_upload_folder_to_vector_store_skips_files_without_metadata(tmp_path):
    module = load_step_module()
    docs_dir = tmp_path / "cleaned_documents"
    docs_dir.mkdir()
    (docs_dir / "DOC-1.txt").write_text("one", encoding="utf-8")
    (docs_dir / "DOC-2.txt").write_text("two", encoding="utf-8")

    class FakeFilesAPI:
        def __init__(self):
            self.created = []

        def create(self, file, purpose):
            self.created.append((Path(file.name).name, purpose))

            class Uploaded:
                id = f"file_{Path(file.name).stem}"

            return Uploaded()

    class FakeBatchAPI:
        def __init__(self):
            self.calls = []

        def create_and_poll(self, *, vector_store_id, files):
            self.calls.append({"vector_store_id": vector_store_id, "files": files})

    class FakeClient:
        def __init__(self):
            self.files = FakeFilesAPI()
            self.vector_stores = type("VectorStores", (), {"file_batches": FakeBatchAPI()})()

    metadata = {
        "DOC-1": {
            "doc_id": "DOC-1",
            "tenant_id": "tenant",
            "sensitivity": "internal",
            "doc_type": "email",
            "date": "2025-01-01",
            "primary_company": "Aurora",
            "participants": [],
        }
    }

    client = FakeClient()
    uploaded_count = module.upload_folder_to_vector_store(
        client=client,
        vector_store_id="vs_123",
        documents_dir=docs_dir,
        doc_id_to_metadata=metadata,
        file_purpose="assistants",
        max_files_per_batch=100,
        skip_files_without_metadata=True,
    )

    assert uploaded_count == 1
    assert client.files.created == [("DOC-1.txt", "assistants")]
    assert len(client.vector_stores.file_batches.calls) == 1
    assert "chunking_strategy" not in client.vector_stores.file_batches.calls[0]


def test_create_batch_and_poll_passes_chunking_strategy_when_supported():
    module = load_step_module()

    class FakeBatchAPI:
        def __init__(self):
            self.calls = []

        def create_and_poll(self, *, vector_store_id, files, chunking_strategy):
            self.calls.append(
                {
                    "vector_store_id": vector_store_id,
                    "files": files,
                    "chunking_strategy": chunking_strategy,
                }
            )

    fake_batch_api = FakeBatchAPI()
    client = type("FakeClient", (), {"vector_stores": type("VectorStores", (), {"file_batches": fake_batch_api})()})()

    module.create_batch_and_poll(
        client=client,
        vector_store_id="vs_123",
        entries=[{"file_id": "file_1", "attributes": {"doc_id": "DOC-1"}}],
    )

    assert len(fake_batch_api.calls) == 1
    call = fake_batch_api.calls[0]
    assert call["chunking_strategy"] == {
        "type": "static",
        "static": {
            "max_chunk_size_tokens": module.CHUNK_SIZE_TOKENS,
            "chunk_overlap_tokens": module.CHUNK_OVERLAP_TOKENS,
        },
    }


def test_clear_vector_store_retries_until_listing_is_empty_and_skips_repeated_deletes():
    module = load_step_module()

    class FakeVectorStoreFilesAPI:
        def __init__(self):
            self.delete_calls = []
            self._pages = [
                ["file_a", "file_b"],
                ["file_b"],
                [],
            ]

        def list(self, *, vector_store_id, limit, after):
            ids = self._pages.pop(0)
            items = [type("File", (), {"id": item_id})() for item_id in ids]
            return type("Page", (), {"data": items, "has_more": False})()

        def delete(self, *, vector_store_id, file_id):
            self.delete_calls.append((vector_store_id, file_id))

    class FakeFilesAPI:
        def __init__(self):
            self.delete_calls = []

        def delete(self, file_id):
            self.delete_calls.append(file_id)

    class FakeClient:
        def __init__(self):
            self.files = FakeFilesAPI()
            self.vector_stores = type("VectorStores", (), {"files": FakeVectorStoreFilesAPI()})()

    client = FakeClient()
    clear_result = module.clear_vector_store(
        client=client,
        vector_store_id="vs_123",
    )

    assert clear_result["deleted_from_storage_count"] == 2
    assert client.vector_stores.files.delete_calls == [
        ("vs_123", "file_a"),
        ("vs_123", "file_b"),
    ]
    assert client.files.delete_calls == ["file_a", "file_b"]


def test_clear_vector_store_stops_retrying_when_detach_keeps_failing():
    module = load_step_module()

    class FakeVectorStoreFilesAPI:
        def __init__(self):
            self.delete_calls = []
            self.list_calls = 0

        def list(self, *, vector_store_id, limit, after):
            self.list_calls += 1
            items = [type("File", (), {"id": "file_stuck"})()]
            return type("Page", (), {"data": items, "has_more": False})()

        def delete(self, *, vector_store_id, file_id):
            self.delete_calls.append((vector_store_id, file_id))
            raise RuntimeError("permission denied")

    class FakeFilesAPI:
        def __init__(self):
            self.delete_calls = []

        def delete(self, file_id):
            self.delete_calls.append(file_id)

    class FakeClient:
        def __init__(self):
            self.files = FakeFilesAPI()
            self.vector_stores = type("VectorStores", (), {"files": FakeVectorStoreFilesAPI()})()

    client = FakeClient()
    clear_result = module.clear_vector_store(
        client=client,
        vector_store_id="vs_123",
    )

    assert clear_result["detached_count"] == 0
    assert clear_result["detach_failed_count"] == 1
    assert len(clear_result["detach_failures"]) == 1
    assert client.vector_stores.files.delete_calls == [("vs_123", "file_stuck")]
    assert client.vector_stores.files.list_calls == 2
    assert client.files.delete_calls == []
