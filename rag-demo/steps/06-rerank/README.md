# Overview

This file implements mixed-granularity dense+sparse reranking.

- Step 04 input is **vector-store semantic chunk candidates**.
- Step 05 input is **document-level keyword candidates**.
- Step 06 joins document-level lexical evidence onto dense chunks by `doc_id` and produces a final **chunk-level** ranking for quote extraction.

## Expected inputs

This step reads:

- `data/outputs/04-semantic-retrieval/semantic-retrieval.jsonl`
- `data/outputs/05-sparse-keyword-retrieval/sparse-keyword-retrieval.jsonl`
- `data/evals/query_eval.json` when no single query id is provided

It relies on query-plan fields embedded in Step 04 rows:

- `original_query`
- `sparse_query`
- optional explicit `company_scope_terms`

## Scoring model

For each query:

1. De-duplicate dense chunk candidates by `dense_candidate_id`.
2. Build sparse document map by `doc_id` (duplicate conflicting rows fail loudly).
3. Keep the dense scoring pool (`MAX_DENSE_CANDIDATES`) and validate sparse coverage for that scored pool.
4. Join each dense chunk to its parent sparse document row and compute:
   - chunk semantic signal
   - parent sparse signal
5. Apply deterministic adjustments (company/person/role/business/recency) on top of the mixed chunk+document signal.

In other words, Step 06 is chunk-level reranking with document-level lexical evidence.

### Required-term gate behavior

Step 05 provides per-document required-term status. Step 06 uses it conservatively:

- if `parent_sparse_required_terms_match` is false:
  - parent sparse lexical signal is `0.0`
  - company/person/business-term boosts are disabled for that candidate
- dense semantic signal remains active
- recency logic remains independent

Step 06 no longer performs a global no-evidence short-circuit purely from Step 05 `required_terms_zero_match` metadata. Mixed candidate construction and candidate-level entity linking still run first (`parent_sparse_required_terms_match`, `parent_sparse_metadata_entity_match`, `entity_linked`). A short-circuit now happens only when there are no dense candidates to evaluate or when no candidates survive entity-linking.

### Conservative entity heuristics

- Company-scope boost terms are used **only** from explicit `query_plan.company_scope_terms`.
- Generic sparse required terms are not auto-reused as company terms.
- Person-name extraction is conservative and blocks obvious non-person prefixes like `project` and `operation`.

## Expected outputs

This step writes:

- `data/outputs/06-rerank/rerank.jsonl`
- `data/outputs/06-rerank/06-rerank-summary.md`

Final `ranked_candidates` remain chunk rows and include both chunk-level dense evidence and parent-document lexical fields (for example `parent_sparse_rank`, `parent_sparse_score`, `parent_sparse_signal`, `parent_sparse_required_terms_match`).
