# Overview

This step performs dense retrieval against the OpenAI vector store created in Step 02.

For a required `--query-id`, it loads that query's Step 03 plan, chooses the retrieval query from `rewritten_query` first with fallback to `original_query`, applies server-side access filters, runs vector store search without managed reranking or query rewriting, and writes semantic chunk candidates for downstream reranking.

## Expected inputs

This step reads:

- a required `--query-id` argument
- `data/outputs/02-build-vector-store/vector_store_manifest.json`
- the Step 03 query plan resolved by `find_query_plan(query_id)`

From the Step 03 plan, this step expects:

- `query_id`
- `tenant_id`
- `role`
- `rewritten_query` or `original_query`

If both query fields are blank, the step raises an error.

## Retrieval logic

The flow is:

1. Require `--query-id`; this step does not infer ids from `query_eval.json`.
2. Load the Step 03 query plan for that id.
3. Use `rewritten_query` as the retrieval query when present; otherwise use `original_query`.
4. Read `vector_store_id` from the Step 02 manifest.
5. Build server-side search filters:
   - always filter `tenant_id`
   - exclude `sensitivity == confidential` unless `role == partner`
6. Search the OpenAI vector store with:
   - `max_num_results=25`
   - `ranking_options={"ranker": "none"}`
   - `rewrite_query=False`
7. Normalize the returned results into semantic chunk candidates and assign `semantic_rank` in returned order.
8. Mark the payload as `ready_for_rerank` for the next step.

## Output schema

This step writes:

- `data/outputs/04-semantic-retrieval/semantic-retrieval.jsonl`
- `data/outputs/04-semantic-retrieval/04-semantic-retrieval-summary.md`

Each JSONL row contains:

- `query_id`
- `input_query_plan`
- `retrieval_query`
- `retrieval_mode` = `openai_vector_store_search_no_rerank`
- `access_filter`
- `candidates`
- `status` = `ready_for_rerank`

`access_filter` contains:

- `role`
- `applied`
- `server_side`
- `filters`
- `returned_candidate_count`

Each candidate contains:

- `dense_candidate_id`
- `chunk_id`
- `dense_result_id`
- `doc_id`
- `text`
- `metadata`
- `semantic_rank`
- `semantic_score`

`dense_candidate_id` is deterministically derived from document id, chunk text, a stable metadata subset, and the trace fields `chunk_id` and `dense_result_id`.

## Write behavior

When the script is run with a single `--query-id`, it merges that query's payload into the existing `semantic-retrieval.jsonl` file instead of overwriting other query rows already present.

The markdown summary records the run configuration and, for each query, the source query, retrieval query, applied filters, and the top returned semantic candidates.
