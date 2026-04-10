# Overview

This file implements the sparse retrieval step.

It reads the Step 03 query plan, builds a keyword query from the structured sparse-query fields, loads tenant-scoped chunks, applies the same role-based access filter used in dense retrieval, and ranks the accessible parent documents with BM25.

After BM25 scoring, it annotates each candidate with required-term match metadata and reranks so required-term matches are listed first while preserving deterministic BM25-based ordering.

## Expected inputs

This step reads:

- `data/outputs/03-query-rewrite-and-sparse-query/query-plans.json`
- `data/evals/query_eval.json` to enumerate query ids when no single query id is provided
- tenant chunk data loaded through `load_chunks_for_tenant(...)`

For each query plan, it uses fields such as:

- `query_id`
- `tenant_id`
- `role`
- `sparse_query`
- `original_query`

The `sparse_query` object includes:

- `required_terms`
- `include_terms`
- `phrases`
- `exclude_terms`

Each candidate written by this step includes:

- `doc_id`
- `document_text`
- `document_metadata`
- `sparse_rank`
- `sparse_score`
- `required_terms_match`
- `required_terms_missing`

## Expected outputs

This step writes:

- `data/outputs/05-sparse-keyword-retrieval/sparse-keyword-retrieval.jsonl`
- `data/outputs/05-sparse-keyword-retrieval/05-sparse-keyword-retrieval-summary.md`

Each output row also records the access-filter result plus required-term annotation/ranking metadata.
Each run rewrites the Step 05 artifact for the query ids processed in that run.

## General Dataflow

Within this step, the flow is:

1. Load the query ids to process and read the matching Step 03 query plans.
2. Build one sparse query string by combining required terms, include terms, and phrase terms while removing explicit exclusions.
3. Load all chunks for the query's tenant.
4. Remove chunks the current role should not access, while recording excluded document ids.
5. Score the accessible parent documents with BM25 against the constructed sparse query text.
6. Annotate every accessible document with `required_terms_match` and `required_terms_missing`.
7. Rerank candidates so required-term matches are first, then BM25 score and deterministic tie-breakers.
8. Write one sparse retrieval payload per query and a markdown summary.

The required-term pass keeps sparse retrieval anchored to the main named entities or terms from the query without dropping sparse coverage for accessible documents.

Step 05 still performs literal required-term annotations against accessible document text. Provenance/scope phrasing cleanup (for example “in Birch’s records” / “from our CRM”) is handled upstream in Step 03 before these hard required terms are set.
