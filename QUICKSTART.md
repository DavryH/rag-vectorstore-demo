# Quickstart: run and reproduce the RAG demo

This guide describes the intended local workflow. Read the SDK compatibility note and indexing warning before attempting a full run.

## 1) Prerequisites

- Python **3.10+**
- An OpenAI API key

**Known compatibility issue:** `rag-demo/requirements.txt` pins `openai==1.40.0`, but Step 04 calls `client.vector_stores.search()`, which that SDK does not support. A clean installation cannot currently complete the full pipeline. Updating and integration-testing the SDK/API usage is deferred; the commands below document the intended workflow rather than a verified clean end-to-end run.

## 2) Install dependencies

From the repository root, on macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r rag-demo/requirements.txt
```

Or on Windows (PowerShell):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r rag-demo/requirements.txt
```

## 3) Configure environment variables

Copy the example file and add your key:

```bash
cp rag-demo/.env.example rag-demo/.env
```

Windows PowerShell equivalent:

```powershell
Copy-Item rag-demo/.env.example rag-demo/.env
```

Required value:

- `OPENAI_API_KEY`

Optional values:

- `OPENAI_ORG_ID`
- `OPENAI_PROJECT`
- `OPENAI_MODEL` (defaults to `gpt-4.1-mini`)
- `RAG_VECTOR_STORE_NAME` (defaults to `rag-demo`)
- `RAG_VECTOR_STORE_ID` (optional; selects an existing store by ID)

## 4) Reproduce the full pipeline

**Warning: Step 02 destructively resets its target OpenAI vector store.** It detaches and deletes the store's existing files (including the underlying OpenAI file objects) before re-uploading. Without `RAG_VECTOR_STORE_ID`, it reuses an existing store matching `RAG_VECTOR_STORE_NAME` or creates one. Use a new, dedicated demo store name and do not point it at a store containing data you want to keep. There is no confirmation prompt.

Run from `rag-demo/`:

```bash
cd rag-demo
python scripts/run_step_group.py --group upload
python scripts/run_step_group.py --group query
```

This executes all steps in order:

1. `01-extract-metadata`
2. `02-build-vector-store`
3. `03-query-rewrite-and-sparse-query`
4. `04-semantic-retrieval` (per eval query)
5. `05-sparse-keyword-retrieval`
6. `06-rerank`
7. `07-extract-quotes`
8. `08-answer`
9. `09-eval`

## 5) Where outputs are written

All generated artifacts are placed under:

- `rag-demo/data/outputs/`

Per-step folders include machine-readable artifacts (`.json`, `.jsonl`) and summary markdown files. Outputs already committed to the repository are historical example artifacts, not proof that a new clean installation completed successfully.

## 6) Run tests

From `rag-demo/`:

```bash
python -m pytest -q
```

## 7) Run individual stages (optional)

If you only want query-time stages after upload:

```bash
cd rag-demo
python scripts/run_query_pipeline.py
```

If you want a dry-run preview of grouped commands:

```bash
cd rag-demo
python scripts/run_step_group.py --group upload --dry-run
python scripts/run_step_group.py --group query --dry-run
```
