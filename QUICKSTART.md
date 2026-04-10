# Quickstart: run and reproduce the RAG demo

This guide is the fastest way to run the repository and reproduce the pipeline artifacts.

## 1) Prerequisites

- Python **3.10+**
- An OpenAI API key

## 2) Install dependencies

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r rag-demo/requirements.txt
```

## 3) Configure environment variables

Copy the example file and add your key:

```bash
cp rag-demo/.env.example rag-demo/.env
```

Required value:

- `OPENAI_API_KEY`

Optional values:

- `OPENAI_ORG_ID`
- `OPENAI_PROJECT`
- `OPENAI_MODEL` (defaults to `gpt-4.1-mini`)
- `RAG_VECTOR_STORE_NAME` (defaults to `rag-demo`)

## 4) Reproduce the full pipeline

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

Per-step folders include machine-readable artifacts (`.json`, `.jsonl`) and summary markdown files.

## 6) Run tests

From `rag-demo/`:

```bash
pytest -q
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
