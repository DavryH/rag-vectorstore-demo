# Overview

This file implements the quote extraction step.

It reads the reranked candidates, asks the model to pull exact supporting quotes, and then repairs and enriches those quotes so the evidence package is usable by the answer step. The extraction stays grounded in source text. It does not answer the question itself.

A small amount of nearby source text can be added as `resolver_context` when it helps clarify what a quote refers to. That context is used narrowly, for cases such as pronouns, sender and recipient labels, headers, or adjacent lines that identify the entity already being referenced by the quote.

## Expected inputs

This step reads:

- `data/outputs/06-rerank/rerank.jsonl`
- `data/evals/query_eval.json`

For each query, it uses:

- the query `question`
- the top reranked candidates from Step 06

The extracted quote records can include fields such as:

- `doc_id`
- `chunk_id`
- `quote`
- `rationale`
- `resolver_context`
- `display_snippet`
- `doc_date`
- `timeline_milestone`
- `fact_labels`

The step also tracks `evidence_coverage` rows describing whether specific requested facts appear to be supported.

## Expected outputs

This step writes:

- `data/outputs/07-extract-quotes/quote-extraction.jsonl`
- `data/outputs/07-extract-quotes/07-extract-quotes-summary.md`

Each query row includes the extracted quotes, the evidence-coverage list, input candidate counts, and the extraction source and model.

## General Dataflow

Within this step, the flow is:

1. Load the query rows and the matching Step 06 rerank rows.
2. Take the top reranked candidates as the quote-extraction input set.
3. Build a structured extraction payload that includes question analysis and candidate text.
4. Ask the model to return exact quotes plus evidence-coverage notes.
5. Sanitize and deduplicate the returned quotes.
6. Apply targeted repair passes when the initial quote set misses the same entity thread, timeline milestones, or other strongly supported facts already present in the candidate pool.
7. Enrich the surviving quotes with small pieces of nearby source text, a display snippet, inferred timeline milestones, and fact labels.
8. Write the quote-extraction rows and a markdown summary.

The repair and enrichment logic is narrow. It stays within the reranked source text and is mainly there to preserve usable evidence when exact-quote extraction would otherwise drop an important nearby line or milestone.

The quote-to-candidate enrichment now uses deterministic candidate reattachment with a canonical lookup: it first matches exact `(doc_id, chunk_id)`, then falls back to doc-level matching only when the `doc_id` maps to a single unique candidate (or explicit doc-level candidate row). This keeps resolver metadata stable when one stage emits a document-level `chunk_id` and another uses an empty chunk id for the same record.
