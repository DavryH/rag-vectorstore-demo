# Overview

This file implements the query planning step for retrieval.

It reads query rows from the evaluation query file, rewrites each question into a compact retrieval-oriented form with the OpenAI API, and builds a structured sparse query alongside it. The sparse query separates required terms, broader include terms, phrase matches, and explicit exclusions.

After structured output is parsed, this step applies deterministic sanitization to `sparse_query.required_terms`. Provenance/scope framing such as “in Birch’s records”, “from our CRM”, or “in the database” is treated as retrieval context, not a hard answer anchor. Those scope terms are removed from required terms before downstream entity-grounding checks, while remaining available in include terms/phrases for recall.

The step validates that the model response matches the expected shape before writing it. It does not provide a local fallback path.

## Expected inputs

This step reads `data/evals/query_eval.json`.

For each query row, it uses:

- `id`
- `question`
- `tenant_id`
- `role`

The internal query plan written by this step includes:

- `query_id`
- `tenant_id`
- `role`
- `original_query`
- `rewritten_query`
- `sparse_query`
- `provenance_scope_terms`
- `sanitized_required_terms`
- `rewrite_model`
- `rewrite_source`
- `status`

The `sparse_query` object includes:

- `required_terms`
- `include_terms`
- `phrases`
- `exclude_terms`

## Expected outputs

This step writes:

- `data/outputs/03-query-rewrite-and-sparse-query/query-plans.json`
- `data/outputs/03-query-rewrite-and-sparse-query/summaries.md`

When the script is run for a single query id, it merges that updated plan into the existing `query-plans.json` file instead of replacing unrelated rows.

## General Dataflow

Within this step, the flow is:

1. Load query rows from `query_eval.json` and select either one query or the full set.
2. Send each question to the OpenAI API with a fixed JSON schema for `rewritten_query` and `sparse_query`.
3. Validate that the returned payload contains the expected fields and list types.
4. Wrap the rewrite result into a query plan record that preserves the original query, tenant, and role fields.
5. Merge with existing query plans when only one query is being updated.
6. Write the full query-plan array and a markdown summary.

This step expects the OpenAI call to succeed. Tests for this file should stub the client response rather than rely on a separate deterministic rewrite path.
