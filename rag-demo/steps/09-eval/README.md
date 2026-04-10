# Overview

This file implements the answer evaluation step.

It compares the Step 08 answer against the original query, the expected answer data, and the extracted quote package. The model produces structured findings, and the file then applies deterministic verdict rules on top of those findings.

This step also validates the answer's returned citations before final scoring. Citation mismatches are turned into explicit issue records, along with narrow root-cause diagnostics such as missing retrieval, tenant spillover, or access-permission problems.

## Expected inputs

This step reads:

- `data/evals/query_eval.json`
- `data/outputs/08-answer/answer.jsonl`
- `data/outputs/07-extract-quotes/quote-extraction.jsonl`
- `data/outputs/06-rerank/rerank.jsonl`
- `data/outputs/01-extract-metadata/extractions.jsonl`
- `data/outputs/03-query-rewrite-and-sparse-query/query-plans.json`
- `data/outputs/04-semantic-retrieval/semantic-retrieval.jsonl`
- `data/outputs/05-sparse-keyword-retrieval/sparse-keyword-retrieval.jsonl`

For each query, it uses fields such as:

- `expected_answer`
- optional `expected_facts`
- optional `forbidden_claims`
- optional `expected_citations`
- optional `citation_policy`
- the generated answer text and citations from Step 08
- the supporting quotes from Step 07

The final evaluation row includes fields such as:

- `query_id`
- `answer`
- `expected_answer`
- `returned_citations`
- `expected_citations`
- `citations_match`
- `findings`
- `verdict`
- `failed_tests`
- `hard_tests`
- `soft_tests`

## Expected outputs

This step writes:

- `data/outputs/09-eval/answer-eval.jsonl`
- `data/outputs/09-eval/09-eval-summary.md`
- `data/outputs/09-eval/failure-traces/` for non-passing queries

The failure traces include the query-specific artifacts from earlier steps so a failing run can be inspected directly.

## General Dataflow

Within this step, the flow is:

1. Load the selected query rows together with the Step 08 answers and Step 07 quote payloads.
2. Normalize the supporting quotes into a stable internal format with quote ids, source doc ids, exact quote text, resolver context, and display snippets.
3. Evaluate the answer with either OpenAI structured output or the dry-run fallback.
4. Check the returned citations against the query's citation policy and expected citations.
5. Add citation-related hard or soft issues to the model findings, including root-cause diagnostics when citations do not line up.
6. Apply deterministic pass, soft-fail, or hard-fail rules from the combined findings.
7. Write per-query evaluation rows, a markdown summary, and detailed failure traces for non-passing results.

This step keeps the final verdict logic explicit in code. The model supplies structured findings, but the pass-or-fail decision is made by deterministic checks in this file.
