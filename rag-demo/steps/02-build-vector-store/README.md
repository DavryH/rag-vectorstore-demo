# Overview

This file implements the vector store build step.

It reads the metadata extraction output, resolves the target OpenAI vector store, clears any files already attached to that store, and uploads the current document set with retrieval attributes derived from the extracted metadata.

The step uses cleaned document copies when they exist. If they do not, it falls back to the original unstructured files.

## Expected inputs

This step reads:

- `data/outputs/01-extract-metadata/extractions.jsonl`
- `data/outputs/01-extract-metadata/cleaned_documents/` when available
- the raw unstructured input directory as a fallback document source
- environment configuration for the target vector store

The metadata rows are used to build vector store attributes such as:

- `doc_id`
- `tenant_id`
- `sensitivity`
- `doc_type`
- `date`
- optional `primary_company`
- optional `participants` as a compact participant-name string

## Expected outputs

This step writes:

- `data/outputs/02-build-vector-store/vector_store_manifest.json` (local runtime artifact; ignored from git)
- `data/outputs/02-build-vector-store/02-build-vector-store-summary.md`

The manifest records the resolved vector store, the source directories used, document counts, and the manifest `created_at` timestamp.

## General Dataflow

Within this step, the flow is:

1. Load the extracted metadata rows and index them by `doc_id`.
2. Choose the document directory, preferring cleaned documents over raw inputs.
3. Resolve the target vector store by explicit id or by name, creating it only when needed.
4. List the files currently attached to that vector store, detach them, and delete the underlying OpenAI files.
5. Walk the selected document directory in a stable order and infer each document's `doc_id` from its file name.
6. Match each document to its metadata row and build the attributes that will travel with the uploaded file.
7. Upload the files in batches and, when supported by the SDK helper, pass an explicit static chunking strategy.
8. Write a local manifest and a markdown summary of the rebuild.

By default, files with no matching Step 01 metadata row are skipped. If `RAG_VECTOR_SKIP_FILES_WITHOUT_METADATA` is set to `false`, the step raises an error instead.

This step also validates required metadata fields before upload. If a required string field is missing, it raises an error instead of uploading incomplete attributes.
