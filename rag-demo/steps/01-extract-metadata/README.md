# Overview

This file implements the metadata extraction step for the source document set.

It reads source documents, looks for an optional in-document `[METADATA]...[/METADATA]` block, and sends the full document text plus the parsed metadata hints to the model. The result is normalized into a fixed record shape before it is written.

This step also writes cleaned document copies with the metadata block removed. Those cleaned copies keep the document text available for later indexing without reusing the inline metadata wrapper.

## Expected inputs

This step reads files from the unstructured input directory.

For each document, it uses:

- the file path and file name
- the full document text
- any parsed `[METADATA]` key-value pairs already embedded in the document

The normalized extraction record keeps these fields:

- `doc_id`
- `tenant_id`
- `sensitivity`
- `doc_type`
- `date`
- `primary_company`
- `participants`

Each participant record is normalized to:

- `name`
- `email`
- `company`
- `role`

## Expected outputs

This step writes one normalized metadata record per source document to:

- `data/outputs/01-extract-metadata/extractions.jsonl`

It also writes:

- `data/outputs/01-extract-metadata/cleaned_documents/` for source copies with `[METADATA]` blocks removed
- `data/outputs/01-extract-metadata/01-extract-metadata-summary.md` for a per-document summary of what was processed

## General Dataflow

Within this step, the flow is:

1. Collect the supported source documents from the unstructured input directory.
2. Read each document and parse any `[METADATA]...[/METADATA]` block into key-value pairs.
3. Remove that block and save a cleaned copy of the document.
4. Send the original document text and parsed metadata hints to the model using a fixed JSON schema.
5. Normalize the returned values so required strings, enums, dates, and participant records all have consistent shapes.
6. Prefer trusted `doc_id` and `tenant_id` values from the parsed metadata block when those values are present.
7. Write the normalized extraction rows to `extractions.jsonl` and write a markdown summary.

The normalization is strict on purpose. Missing or invalid values are converted to `unknown` rather than left in mixed formats.
