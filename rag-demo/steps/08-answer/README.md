# Overview

This file implements the final answer-generation step for a document-grounded question answering pipeline.

It takes a prepared query plus curated evidence from earlier steps and turns them into a final structured answer. The evidence is centered on exact source quotes, with small amounts of nearby source text added only when needed to clarify what a quote refers to. For example, that nearby text can help resolve references like "he", "she", "they", sender and recipient information in an email, or role labels that are already present in the source.

The file is designed to answer from evidence rather than from freeform inference. Exact quotes are treated as the primary evidence. Nearby context is used only to interpret those quotes more reliably, not to introduce new facts that are not stated in the source.

## Expected inputs

This step reads:

- the original query text
- quote extraction output containing exact supporting quotes and related metadata
- reranked source records used to recover small pieces of nearby context

The normalized evidence records used inside this step can include fields such as:

- `document_id`
- `chunk_id`
- `exact_quote`
- `resolver_context`
- `display_snippet`
- `doc_date`
- `timeline_milestone`
- `fact_labels`

## Expected outputs

This step writes a final structured answer artifact for each query, including:

- the final answer text
- a list of citations
- fact-level support records showing which requested facts were supported and which were not
- selected supporting quotes and metadata for inspection

The written outputs are:

- `data/outputs/08-answer/answer.jsonl`
- `data/outputs/08-answer/08-answer-summary.md`

# General Dataflow

Within this file, the flow is:

1. Load the original query.
2. Load the extracted quote records for that query.
3. Load the reranked source records for that query.
4. Turn the quote records into a normalized internal evidence structure.
5. Recover small pieces of nearby source context when needed, such as email header lines or the immediately adjacent source line.
6. Build a constrained prompt that tells the model to answer only from the provided evidence.
7. Generate a structured JSON result containing the answer, citations, and fact-level support data.
8. Normalize and validate the returned citations so they match real evidence records.
9. Validate the final answer shape and the supported-versus-unsupported fact fields.
10. Write the final structured output and summary files.

When run for a single query id, this step merges that query's result into the existing `answer.jsonl` file instead of replacing unrelated rows.

The result is a final answer stage that operates on already-prepared evidence, keeps context narrowly scoped, and produces an answer artifact that can be inspected and evaluated later.

Evidence normalization also uses the same deterministic candidate reattachment policy as Step 07: exact `(doc_id, chunk_id)` first, then a strict doc-level fallback only when the document match is unique. This preserves resolver context, dates, and fact labels without guessing across multiple same-document candidates.
