# RAG Demo

## Run it locally

For a reproducible setup (dependencies, env configuration, and end-to-end commands), use:

- `QUICKSTART.md` for the runbook
- `rag-demo/requirements.txt` as the install manifest

## Overview

This project is a document-grounded question answering demo designed to show how I build practical retrieval-augmented generation systems for business and relationship data.

At a high level, the system takes a set of unstructured documents, preserves important structured metadata, indexes the documents for retrieval, rewrites incoming questions into retrieval-friendly forms, retrieves evidence through vector-store semantic retrieval and document-level keyword retrieval, reranks the results, extracts grounded supporting quotes, and produces a final answer that stays tied to the source material.

The goal is not just to return an answer. The goal is to return an answer that is inspectable, constrained by evidence, aware of document metadata, and easier to evaluate when something goes wrong.

There are simpler out-of-the-box ways to build document QA systems, including managed file-search style retrieval. This demo uses more explicit custom stages, such as query rewriting, mixed-granularity dense+sparse retrieval stages, deterministic reranking, and evidence packaging, to show that I understand how the underlying system works rather than only how to call a single high-level API.

## What this demo is meant to show

This demo is meant to demonstrate capability across the main parts of a modern RAG system, especially the kinds of retrieval problems that come up in CRM, relationship intelligence, and other enterprise knowledge workflows:

- document ingestion and metadata normalization
- vector-store indexing with retrieval attributes
- query understanding and query augmentation
- mixed-granularity dense+sparse retrieval with chunk-level reranking
- metadata-aware and access-aware filtering
- reranking to improve final evidence quality
- contextual compression through quote extraction
- answer generation grounded in explicit evidence
- structured evaluation with deterministic checks

That combination is especially relevant for enterprise AI systems where correctness, traceability, and access boundaries matter as much as raw retrieval quality.

## What the system does

The demo answers questions against a business-style document set rather than relying on the model's general knowledge.

It is designed for situations where the answer may be spread across emails, notes, or other internal documents, where wording can vary, and where the system needs to handle more than one retrieval strategy. It is also built with the assumption that not every document should be equally accessible to every query context, so retrieval is scoped using tenant and role information carried through the pipeline.

The output is not just a freeform response. The system also preserves supporting evidence, citations, and evaluation artifacts so the full path from question to answer can be inspected afterward.

## How it works

### 1. Prepare the document set

The pipeline begins by reading the source documents and normalizing the metadata needed for retrieval and filtering.

For simplicity, the documents can include an in-document metadata block for structured fields that would reasonably already be known outside the model, such as tenant, access level, sensitivity, and other security-related or operational metadata. The system then uses an LLM to extract or normalize information that can be inferred from the document content itself, such as participants, companies, and other useful document attributes.

A cleaned version of each document is also produced so the retrieval layer works from indexable text without carrying along the inline metadata wrapper.

### 2. Build the retrieval index

Once metadata has been normalized, the documents are uploaded into a vector store with retrieval attributes attached.

This matters because the retrieval layer is not only searching raw text similarity. It is also working with structured attributes that help the system keep results scoped and interpretable.

### 3. Build retrieval plans from the user question

Before retrieval, the system builds a query plan that keeps the original question, generates a rewritten variant, and creates a structured keyword query that separates stronger anchor terms from broader optional terms, phrases, and exclusions.

The current pipeline uses the original question for dense retrieval and the structured keyword plan for sparse retrieval, while preserving the rewritten variant as an inspectable planning artifact for future tuning.

### 4. Retrieve with both dense and sparse search

The demo uses a mixed-granularity dense+sparse retrieval and reranking pipeline.

One path uses vector-store semantic retrieval over the original question to find semantically similar chunks, which helps when wording differs across documents. The other path uses document-level keyword retrieval driven by the Step 03 structured keyword plan, which helps when exact terms, named entities, or phrases are important.

Both paths are filtered to respect the query's tenant and role context before ranking the candidates.

### 5. Rerank the combined candidate pool

Step 06 performs chunk-level reranking with document-level lexical evidence: chunk-level semantic candidates are joined to their parent document-level keyword evidence and then refined with lightweight deterministic signals already present in the query and candidate text.

This step improves the ordering of the candidate pool without turning reranking into an unconstrained reasoning phase. In practice, that means the system can better preserve the most relevant evidence for the next stage while still remaining understandable and debuggable.

### 6. Compress the context into usable evidence

Instead of dumping large chunks directly into answer generation, the system extracts exact supporting quotes from the highest-value candidates.

It can also attach a small amount of nearby context when needed to clarify what a quote refers to, such as who a pronoun refers to or what role or header line gives the quote its meaning. This keeps the evidence grounded while still making it more usable.

### 7. Generate a final grounded answer

The final answer stage works from the prepared evidence package rather than from the full retrieval set.

That means answer generation is constrained by the extracted support, and the result includes citations and fact-level support information. If something is unsupported, the pipeline is designed to make that easier to identify instead of quietly filling gaps with confident guesswork.

### 8. Evaluate the result

The demo also includes an answer evaluation stage.

This checks the final answer against expected outcomes, validates citations, and applies explicit verdict logic on top of structured model findings. When a query fails, the earlier pipeline artifacts are preserved so the failure can be traced back to retrieval, evidence selection, citation problems, or answer generation.

## Design choices

### Mixed-granularity dense+sparse retrieval instead of single-method retrieval

Vector-store semantic retrieval and document-level keyword retrieval fail in different ways. Using both gives the system better coverage, especially for named entities, business terminology, and questions where the user's phrasing does not match the documents exactly.

### Metadata-aware retrieval

The metadata layer is not cosmetic. It gives the system a way to keep retrieval scoped, support access-aware filtering, and make the candidate pool more relevant before later steps ever see it.

### Evidence-first answering

The answer stage is intentionally downstream of quote extraction. That creates a narrower and more inspectable interface between retrieval and generation, which is useful when trust and debugging matter.

### Inspectability over magic

This is a stepwise pipeline rather than a single black-box prompt. Each stage writes structured artifacts so retrieval quality, evidence quality, and answer quality can be examined independently.

### Evaluation as part of the system

The evaluation layer is not an afterthought. It is part of the design. That makes the demo more representative of how I approach production LLM systems: not just generating outputs, but building a repeatable way to measure whether the system is actually behaving correctly.

## Why this is relevant

This demo was built to reflect the kinds of problems that come up in enterprise AI retrieval systems:

- unstructured documents with inconsistent wording
- structured metadata that still needs to influence retrieval
- access or sensitivity boundaries
- the need for mixed-granularity dense+sparse retrieval and reranking
- the need to compress large retrieval results into answerable evidence
- the need to inspect and evaluate failures rather than treating the model as a black box

In other words, this is meant to show practical system design for RAG, not just prompt-writing.

## Scope

This project is intentionally a demo rather than a full production platform.

The emphasis is on clear architecture, grounded retrieval, evidence handling, and evaluation discipline. The system is broken into explicit stages so each part of the RAG pipeline can be understood, tested, and improved independently.
