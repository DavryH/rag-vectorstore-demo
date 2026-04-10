# Step 01 Summary

## AUR-DEAL-013.txt
- processing source file `AUR-DEAL-013.txt`
- detected in-document metadata tags in the source document
- removed explicit `[METADATA]...[/METADATA]` tags and saved a cleaned copy to `data/outputs/01-extract-metadata/cleaned_documents/AUR-DEAL-013.txt` for vector-store ingestion
- sent the document text to the OpenAI LLM to extract structured metadata
- extracted metadata: doc_id=AUR-DEAL-013, tenant_id=t_aurora, sensitivity=internal, doc_type=deal_note, date=2026-01-22, primary_company=Northwind Bio, participants=1
- appended one extraction record to `data/outputs/01-extract-metadata/extractions.jsonl`

## AUR-EMAIL-001.txt
- processing source file `AUR-EMAIL-001.txt`
- detected in-document metadata tags in the source document
- removed explicit `[METADATA]...[/METADATA]` tags and saved a cleaned copy to `data/outputs/01-extract-metadata/cleaned_documents/AUR-EMAIL-001.txt` for vector-store ingestion
- sent the document text to the OpenAI LLM to extract structured metadata
- extracted metadata: doc_id=AUR-EMAIL-001, tenant_id=t_aurora, sensitivity=internal, doc_type=email, date=2025-11-12, primary_company=Helio Robotics, participants=3
- appended one extraction record to `data/outputs/01-extract-metadata/extractions.jsonl`

## AUR-EMAIL-007.txt
- processing source file `AUR-EMAIL-007.txt`
- detected in-document metadata tags in the source document
- removed explicit `[METADATA]...[/METADATA]` tags and saved a cleaned copy to `data/outputs/01-extract-metadata/cleaned_documents/AUR-EMAIL-007.txt` for vector-store ingestion
- sent the document text to the OpenAI LLM to extract structured metadata
- extracted metadata: doc_id=AUR-EMAIL-007, tenant_id=t_aurora, sensitivity=internal, doc_type=email, date=2026-02-07, primary_company=Helio Robotics, participants=2
- appended one extraction record to `data/outputs/01-extract-metadata/extractions.jsonl`

## AUR-EMAIL-008.txt
- processing source file `AUR-EMAIL-008.txt`
- detected in-document metadata tags in the source document
- removed explicit `[METADATA]...[/METADATA]` tags and saved a cleaned copy to `data/outputs/01-extract-metadata/cleaned_documents/AUR-EMAIL-008.txt` for vector-store ingestion
- sent the document text to the OpenAI LLM to extract structured metadata
- extracted metadata: doc_id=AUR-EMAIL-008, tenant_id=t_aurora, sensitivity=internal, doc_type=email, date=2026-02-12, primary_company=Helio Robotics, participants=3
- appended one extraction record to `data/outputs/01-extract-metadata/extractions.jsonl`

## AUR-MEET-002.txt
- processing source file `AUR-MEET-002.txt`
- detected in-document metadata tags in the source document
- removed explicit `[METADATA]...[/METADATA]` tags and saved a cleaned copy to `data/outputs/01-extract-metadata/cleaned_documents/AUR-MEET-002.txt` for vector-store ingestion
- sent the document text to the OpenAI LLM to extract structured metadata
- extracted metadata: doc_id=AUR-MEET-002, tenant_id=t_aurora, sensitivity=internal, doc_type=meeting_notes, date=2025-11-15, primary_company=Helio Robotics, participants=3
- appended one extraction record to `data/outputs/01-extract-metadata/extractions.jsonl`

## AUR-MEMO-005.txt
- processing source file `AUR-MEMO-005.txt`
- detected in-document metadata tags in the source document
- removed explicit `[METADATA]...[/METADATA]` tags and saved a cleaned copy to `data/outputs/01-extract-metadata/cleaned_documents/AUR-MEMO-005.txt` for vector-store ingestion
- sent the document text to the OpenAI LLM to extract structured metadata
- extracted metadata: doc_id=AUR-MEMO-005, tenant_id=t_aurora, sensitivity=confidential, doc_type=internal_memo, date=2026-01-20, primary_company=Helio Robotics, participants=1
- appended one extraction record to `data/outputs/01-extract-metadata/extractions.jsonl`

## BIR-EMAIL-001.txt
- processing source file `BIR-EMAIL-001.txt`
- detected in-document metadata tags in the source document
- removed explicit `[METADATA]...[/METADATA]` tags and saved a cleaned copy to `data/outputs/01-extract-metadata/cleaned_documents/BIR-EMAIL-001.txt` for vector-store ingestion
- sent the document text to the OpenAI LLM to extract structured metadata
- extracted metadata: doc_id=BIR-EMAIL-001, tenant_id=t_birch, sensitivity=internal, doc_type=email, date=2025-10-22, primary_company=Kestrel Payments, participants=2
- appended one extraction record to `data/outputs/01-extract-metadata/extractions.jsonl`

## Eval

- metadata comparison matched `data/evals/expected_metadata.json`
```json
{
  "expected_file": "data/evals/expected_metadata.json",
  "status": "matched"
}
```

