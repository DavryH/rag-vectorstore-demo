# Step 04 Summaries

## Run configuration

- retrieval mode: `openai_vector_store_search_no_rerank`
- retrieval query source: `rewritten_query` (fallback: `original_query`)
- query rewriting: `enabled in Step 03 plan`
- managed reranking: `disabled`

## Query `RAG-001`

- source query: `What is Helio's latest valuation, and how does it differ from the earlier ask?`
- retrieval query: `helio latest valuation difference earlier ask`
- retrieval mode: `openai_vector_store_search_no_rerank`
- query role: `analyst`
- server-side filters applied: `True`
- server-side filters: `{"filters":[{"key":"tenant_id","type":"eq","value":"t_aurora"},{"key":"sensitivity","type":"nin","value":["confidential"]}],"type":"and"}`
- returned candidates: `5`
- top semantic candidates (ranked):
  - `#1` doc `AUR-EMAIL-008` (semantic_score `0.0328`, dense_candidate_id `densecand_f6643ef52c3e3969d98857def407574259287f2da85f5f1aa1c2a1ccbd4f0bb0`)
    - chunk text:
      From: Alex Chen <alex.chen@heliorobotics.example>
      To: Priya Singh <priya.singh@auroracap.example>
      Cc: Jordan Lee <jordan.lee@auroracap.example>
      Date: 2026-02-12
      Subject: Revised Helio term sheet
      
      Hi Priya,
      
      Thanks for the quick turnaround.
      
      Attached is the updated term sheet for discussion. The company is now proposing an $82M pre-money valuation.
      
      Current draft terms:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - one board observer seat
      
      Let me know if this gets us close enough for the next conversation.
      
      Best,
      Alex Chen
      CFO, Helio Robotics
  - `#2` doc `AUR-EMAIL-001` (semantic_score `0.0318`, dense_candidate_id `densecand_b55347ec4b65c343bc6a7197ba7aa8f11a59e9ca267ad825d1778b53cb16a715`)
    - chunk text:
      From: Jordan Lee <jordan.lee@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Cc: Priya Singh <priya.singh@auroracap.example>
      Date: 2025-11-12
      Subject: Intro: Aurora Capital <> Helio Robotics
      
      Hi Alex,
      
      Great to meet you virtually. As mentioned, I'm Jordan Lee, a Partner at Aurora Capital.
      
      Priya Singh (cc'd) will coordinate next steps with you. If it is easiest, you can treat Priya as the primary point of contact on our side.
      
      Looking forward to learning more about Helio Robotics and the current Series A process.
      
      Best,
      Jordan
  - `#3` doc `AUR-MEET-002` (semantic_score `0.0315`, dense_candidate_id `densecand_26d70ead81752d5377a108f17bb4e0c121a301b4cacb43e93ae996a7f30eb94a`)
    - chunk text:
      Meeting Title: Helio Robotics - Introductory Diligence Call
      Date: 2025-11-15
      Attendees:
      - Jordan Lee, Partner, Aurora Capital
      - Priya Singh, Associate, Aurora Capital
      - Alex Chen, CFO, Helio Robotics
      
      Helio is raising $18M in its Series A at a $90M pre-money valuation.
      
      Current topline metrics discussed on the call:
      - ARR: $4.2M
      - Main risk raised by the company: supply chain volatility for a key hardware component
      
      Alex Chen, CFO, walked through the financing process and said the data room should be ready by 2025-11-20.
      
      Notes:
      The company is moving quickly and asked for feedback on terms after Aurora reviews the initial materials.
  - `#4` doc `AUR-EMAIL-007` (semantic_score `0.0315`, dense_candidate_id `densecand_0ac10015abfd591da1b32df8099467660267d7cecd8adbfa3fe0f3d270988f78`)
    - chunk text:
      From: Priya Singh <priya.singh@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Date: 2026-02-07
      Subject: Aurora counter on Helio term sheet
      
      Hi Alex,
      
      Following up on our internal review, Aurora would be prepared to proceed at a $78M pre-money valuation.
      
      Other proposed terms from our side:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - no board seat
      
      If this is directionally workable, please send through a revised term sheet.
      
      Best,
      Priya
  - `#5` doc `AUR-DEAL-013` (semantic_score `0.0189`, dense_candidate_id `densecand_cea7aa2760ca71830ff72771b76da1850c9c8ebbc8cb543bdb1841dcdb5a4625`)
    - chunk text:
      Deal Note
      Company: Northwind Bio
      Date: 2026-01-22
      Created by: Priya Singh
      
      Current stage: Diligence
      
      Status summary:
      Northwind Bio remains in diligence pending cleanup of outstanding legal diligence items.
      
      Open items before the deal can move forward:
      - revised IP assignment
      - contractor remediation plan
      
      No other gating items are listed in this note.

## Query `RAG-002`

- source query: `For Northwind Bio, what is the current deal stage and what is it waiting on?`
- retrieval query: `northwind bio current deal stage waiting`
- retrieval mode: `openai_vector_store_search_no_rerank`
- query role: `analyst`
- server-side filters applied: `True`
- server-side filters: `{"filters":[{"key":"tenant_id","type":"eq","value":"t_aurora"},{"key":"sensitivity","type":"nin","value":["confidential"]}],"type":"and"}`
- returned candidates: `5`
- top semantic candidates (ranked):
  - `#1` doc `AUR-EMAIL-008` (semantic_score `0.0325`, dense_candidate_id `densecand_f6643ef52c3e3969d98857def407574259287f2da85f5f1aa1c2a1ccbd4f0bb0`)
    - chunk text:
      From: Alex Chen <alex.chen@heliorobotics.example>
      To: Priya Singh <priya.singh@auroracap.example>
      Cc: Jordan Lee <jordan.lee@auroracap.example>
      Date: 2026-02-12
      Subject: Revised Helio term sheet
      
      Hi Priya,
      
      Thanks for the quick turnaround.
      
      Attached is the updated term sheet for discussion. The company is now proposing an $82M pre-money valuation.
      
      Current draft terms:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - one board observer seat
      
      Let me know if this gets us close enough for the next conversation.
      
      Best,
      Alex Chen
      CFO, Helio Robotics
  - `#2` doc `AUR-DEAL-013` (semantic_score `0.0318`, dense_candidate_id `densecand_cea7aa2760ca71830ff72771b76da1850c9c8ebbc8cb543bdb1841dcdb5a4625`)
    - chunk text:
      Deal Note
      Company: Northwind Bio
      Date: 2026-01-22
      Created by: Priya Singh
      
      Current stage: Diligence
      
      Status summary:
      Northwind Bio remains in diligence pending cleanup of outstanding legal diligence items.
      
      Open items before the deal can move forward:
      - revised IP assignment
      - contractor remediation plan
      
      No other gating items are listed in this note.
  - `#3` doc `AUR-EMAIL-001` (semantic_score `0.0318`, dense_candidate_id `densecand_b55347ec4b65c343bc6a7197ba7aa8f11a59e9ca267ad825d1778b53cb16a715`)
    - chunk text:
      From: Jordan Lee <jordan.lee@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Cc: Priya Singh <priya.singh@auroracap.example>
      Date: 2025-11-12
      Subject: Intro: Aurora Capital <> Helio Robotics
      
      Hi Alex,
      
      Great to meet you virtually. As mentioned, I'm Jordan Lee, a Partner at Aurora Capital.
      
      Priya Singh (cc'd) will coordinate next steps with you. If it is easiest, you can treat Priya as the primary point of contact on our side.
      
      Looking forward to learning more about Helio Robotics and the current Series A process.
      
      Best,
      Jordan
  - `#4` doc `AUR-MEET-002` (semantic_score `0.0317`, dense_candidate_id `densecand_26d70ead81752d5377a108f17bb4e0c121a301b4cacb43e93ae996a7f30eb94a`)
    - chunk text:
      Meeting Title: Helio Robotics - Introductory Diligence Call
      Date: 2025-11-15
      Attendees:
      - Jordan Lee, Partner, Aurora Capital
      - Priya Singh, Associate, Aurora Capital
      - Alex Chen, CFO, Helio Robotics
      
      Helio is raising $18M in its Series A at a $90M pre-money valuation.
      
      Current topline metrics discussed on the call:
      - ARR: $4.2M
      - Main risk raised by the company: supply chain volatility for a key hardware component
      
      Alex Chen, CFO, walked through the financing process and said the data room should be ready by 2025-11-20.
      
      Notes:
      The company is moving quickly and asked for feedback on terms after Aurora reviews the initial materials.
  - `#5` doc `AUR-EMAIL-007` (semantic_score `0.0186`, dense_candidate_id `densecand_0ac10015abfd591da1b32df8099467660267d7cecd8adbfa3fe0f3d270988f78`)
    - chunk text:
      From: Priya Singh <priya.singh@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Date: 2026-02-07
      Subject: Aurora counter on Helio term sheet
      
      Hi Alex,
      
      Following up on our internal review, Aurora would be prepared to proceed at a $78M pre-money valuation.
      
      Other proposed terms from our side:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - no board seat
      
      If this is directionally workable, please send through a revised term sheet.
      
      Best,
      Priya

## Query `RAG-003A`

- source query: `Who is Alex Chen in Aurora's records, and what company is he associated with?`
- retrieval query: `alex chen aurora company association`
- retrieval mode: `openai_vector_store_search_no_rerank`
- query role: `analyst`
- server-side filters applied: `True`
- server-side filters: `{"filters":[{"key":"tenant_id","type":"eq","value":"t_aurora"},{"key":"sensitivity","type":"nin","value":["confidential"]}],"type":"and"}`
- returned candidates: `5`
- top semantic candidates (ranked):
  - `#1` doc `AUR-EMAIL-008` (semantic_score `0.0323`, dense_candidate_id `densecand_f6643ef52c3e3969d98857def407574259287f2da85f5f1aa1c2a1ccbd4f0bb0`)
    - chunk text:
      From: Alex Chen <alex.chen@heliorobotics.example>
      To: Priya Singh <priya.singh@auroracap.example>
      Cc: Jordan Lee <jordan.lee@auroracap.example>
      Date: 2026-02-12
      Subject: Revised Helio term sheet
      
      Hi Priya,
      
      Thanks for the quick turnaround.
      
      Attached is the updated term sheet for discussion. The company is now proposing an $82M pre-money valuation.
      
      Current draft terms:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - one board observer seat
      
      Let me know if this gets us close enough for the next conversation.
      
      Best,
      Alex Chen
      CFO, Helio Robotics
  - `#2` doc `AUR-EMAIL-001` (semantic_score `0.0320`, dense_candidate_id `densecand_b55347ec4b65c343bc6a7197ba7aa8f11a59e9ca267ad825d1778b53cb16a715`)
    - chunk text:
      From: Jordan Lee <jordan.lee@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Cc: Priya Singh <priya.singh@auroracap.example>
      Date: 2025-11-12
      Subject: Intro: Aurora Capital <> Helio Robotics
      
      Hi Alex,
      
      Great to meet you virtually. As mentioned, I'm Jordan Lee, a Partner at Aurora Capital.
      
      Priya Singh (cc'd) will coordinate next steps with you. If it is easiest, you can treat Priya as the primary point of contact on our side.
      
      Looking forward to learning more about Helio Robotics and the current Series A process.
      
      Best,
      Jordan
  - `#3` doc `AUR-MEET-002` (semantic_score `0.0320`, dense_candidate_id `densecand_26d70ead81752d5377a108f17bb4e0c121a301b4cacb43e93ae996a7f30eb94a`)
    - chunk text:
      Meeting Title: Helio Robotics - Introductory Diligence Call
      Date: 2025-11-15
      Attendees:
      - Jordan Lee, Partner, Aurora Capital
      - Priya Singh, Associate, Aurora Capital
      - Alex Chen, CFO, Helio Robotics
      
      Helio is raising $18M in its Series A at a $90M pre-money valuation.
      
      Current topline metrics discussed on the call:
      - ARR: $4.2M
      - Main risk raised by the company: supply chain volatility for a key hardware component
      
      Alex Chen, CFO, walked through the financing process and said the data room should be ready by 2025-11-20.
      
      Notes:
      The company is moving quickly and asked for feedback on terms after Aurora reviews the initial materials.
  - `#4` doc `AUR-EMAIL-007` (semantic_score `0.0313`, dense_candidate_id `densecand_0ac10015abfd591da1b32df8099467660267d7cecd8adbfa3fe0f3d270988f78`)
    - chunk text:
      From: Priya Singh <priya.singh@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Date: 2026-02-07
      Subject: Aurora counter on Helio term sheet
      
      Hi Alex,
      
      Following up on our internal review, Aurora would be prepared to proceed at a $78M pre-money valuation.
      
      Other proposed terms from our side:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - no board seat
      
      If this is directionally workable, please send through a revised term sheet.
      
      Best,
      Priya
  - `#5` doc `AUR-DEAL-013` (semantic_score `0.0313`, dense_candidate_id `densecand_cea7aa2760ca71830ff72771b76da1850c9c8ebbc8cb543bdb1841dcdb5a4625`)
    - chunk text:
      Deal Note
      Company: Northwind Bio
      Date: 2026-01-22
      Created by: Priya Singh
      
      Current stage: Diligence
      
      Status summary:
      Northwind Bio remains in diligence pending cleanup of outstanding legal diligence items.
      
      Open items before the deal can move forward:
      - revised IP assignment
      - contractor remediation plan
      
      No other gating items are listed in this note.

## Query `RAG-003B`

- source query: `Who is Alex Chen in Birch's records, and what company is he associated with?`
- retrieval query: `alex chen birch company association`
- retrieval mode: `openai_vector_store_search_no_rerank`
- query role: `analyst`
- server-side filters applied: `True`
- server-side filters: `{"filters":[{"key":"tenant_id","type":"eq","value":"t_birch"},{"key":"sensitivity","type":"nin","value":["confidential"]}],"type":"and"}`
- returned candidates: `1`
- top semantic candidates (ranked):
  - `#1` doc `BIR-EMAIL-001` (semantic_score `0.0328`, dense_candidate_id `densecand_4d661720d3ff0244e45f429938dee9259a228b538f3e7d9f4af74dcec6d0a56b`)
    - chunk text:
      From: Mara Holt <mara.holt@birchvc.example>
      To: Alex Chen <alex.chen@kestrel.example>
      Date: 2025-10-22
      Subject: Intro and next steps
      
      Hi Alex,
      
      Good speaking today. Thanks again for making time.
      
      For the record, I have you listed as VP Sales at Kestrel Payments. I will circulate notes internally and come back with next steps after the team reviews the opportunity.
      
      Best,
      Mara

## Query `RAG-004A`

- source query: `What is Project Sunflower and what are the related diligence concerns?`
- retrieval query: `project sunflower diligence concerns`
- retrieval mode: `openai_vector_store_search_no_rerank`
- query role: `partner`
- server-side filters applied: `True`
- server-side filters: `{"filters":[{"key":"tenant_id","type":"eq","value":"t_aurora"}],"type":"and"}`
- returned candidates: `6`
- top semantic candidates (ranked):
  - `#1` doc `AUR-DEAL-013` (semantic_score `0.0325`, dense_candidate_id `densecand_cea7aa2760ca71830ff72771b76da1850c9c8ebbc8cb543bdb1841dcdb5a4625`)
    - chunk text:
      Deal Note
      Company: Northwind Bio
      Date: 2026-01-22
      Created by: Priya Singh
      
      Current stage: Diligence
      
      Status summary:
      Northwind Bio remains in diligence pending cleanup of outstanding legal diligence items.
      
      Open items before the deal can move forward:
      - revised IP assignment
      - contractor remediation plan
      
      No other gating items are listed in this note.
  - `#2` doc `AUR-MEMO-005` (semantic_score `0.0318`, dense_candidate_id `densecand_3ab5f043d16c6abf9b5a03b20938a4a44513558565d9656117eca40a878d9f58`)
    - chunk text:
      Aurora Capital
      Confidential Internal Memo
      Date: 2026-01-20
      Created by: Jordan Lee
      Company: Helio Robotics
      
      Project Sunflower is the internal codename being used for the Helio Robotics situation.
      
      Separate from the financing discussion, there may be potential acquisition interest from OmniDynamics. This is early and unconfirmed, but it is relevant context for partner-level review.
      
      Key diligence concern:
      Customer concentration remains elevated. Helio's top 2 customers account for 38% of revenue.
      
      This memo is confidential and should not be forwarded outside the partnership.
  - `#3` doc `AUR-MEET-002` (semantic_score `0.0310`, dense_candidate_id `densecand_26d70ead81752d5377a108f17bb4e0c121a301b4cacb43e93ae996a7f30eb94a`)
    - chunk text:
      Meeting Title: Helio Robotics - Introductory Diligence Call
      Date: 2025-11-15
      Attendees:
      - Jordan Lee, Partner, Aurora Capital
      - Priya Singh, Associate, Aurora Capital
      - Alex Chen, CFO, Helio Robotics
      
      Helio is raising $18M in its Series A at a $90M pre-money valuation.
      
      Current topline metrics discussed on the call:
      - ARR: $4.2M
      - Main risk raised by the company: supply chain volatility for a key hardware component
      
      Alex Chen, CFO, walked through the financing process and said the data room should be ready by 2025-11-20.
      
      Notes:
      The company is moving quickly and asked for feedback on terms after Aurora reviews the initial materials.
  - `#4` doc `AUR-EMAIL-008` (semantic_score `0.0191`, dense_candidate_id `densecand_f6643ef52c3e3969d98857def407574259287f2da85f5f1aa1c2a1ccbd4f0bb0`)
    - chunk text:
      From: Alex Chen <alex.chen@heliorobotics.example>
      To: Priya Singh <priya.singh@auroracap.example>
      Cc: Jordan Lee <jordan.lee@auroracap.example>
      Date: 2026-02-12
      Subject: Revised Helio term sheet
      
      Hi Priya,
      
      Thanks for the quick turnaround.
      
      Attached is the updated term sheet for discussion. The company is now proposing an $82M pre-money valuation.
      
      Current draft terms:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - one board observer seat
      
      Let me know if this gets us close enough for the next conversation.
      
      Best,
      Alex Chen
      CFO, Helio Robotics
  - `#5` doc `AUR-EMAIL-001` (semantic_score `0.0189`, dense_candidate_id `densecand_b55347ec4b65c343bc6a7197ba7aa8f11a59e9ca267ad825d1778b53cb16a715`)
    - chunk text:
      From: Jordan Lee <jordan.lee@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Cc: Priya Singh <priya.singh@auroracap.example>
      Date: 2025-11-12
      Subject: Intro: Aurora Capital <> Helio Robotics
      
      Hi Alex,
      
      Great to meet you virtually. As mentioned, I'm Jordan Lee, a Partner at Aurora Capital.
      
      Priya Singh (cc'd) will coordinate next steps with you. If it is easiest, you can treat Priya as the primary point of contact on our side.
      
      Looking forward to learning more about Helio Robotics and the current Series A process.
      
      Best,
      Jordan

## Query `RAG-004B`

- source query: `What is Project Sunflower and what are the related diligence concerns?`
- retrieval query: `project sunflower diligence concerns`
- retrieval mode: `openai_vector_store_search_no_rerank`
- query role: `analyst`
- server-side filters applied: `True`
- server-side filters: `{"filters":[{"key":"tenant_id","type":"eq","value":"t_aurora"},{"key":"sensitivity","type":"nin","value":["confidential"]}],"type":"and"}`
- returned candidates: `5`
- top semantic candidates (ranked):
  - `#1` doc `AUR-DEAL-013` (semantic_score `0.0328`, dense_candidate_id `densecand_cea7aa2760ca71830ff72771b76da1850c9c8ebbc8cb543bdb1841dcdb5a4625`)
    - chunk text:
      Deal Note
      Company: Northwind Bio
      Date: 2026-01-22
      Created by: Priya Singh
      
      Current stage: Diligence
      
      Status summary:
      Northwind Bio remains in diligence pending cleanup of outstanding legal diligence items.
      
      Open items before the deal can move forward:
      - revised IP assignment
      - contractor remediation plan
      
      No other gating items are listed in this note.
  - `#2` doc `AUR-MEET-002` (semantic_score `0.0315`, dense_candidate_id `densecand_26d70ead81752d5377a108f17bb4e0c121a301b4cacb43e93ae996a7f30eb94a`)
    - chunk text:
      Meeting Title: Helio Robotics - Introductory Diligence Call
      Date: 2025-11-15
      Attendees:
      - Jordan Lee, Partner, Aurora Capital
      - Priya Singh, Associate, Aurora Capital
      - Alex Chen, CFO, Helio Robotics
      
      Helio is raising $18M in its Series A at a $90M pre-money valuation.
      
      Current topline metrics discussed on the call:
      - ARR: $4.2M
      - Main risk raised by the company: supply chain volatility for a key hardware component
      
      Alex Chen, CFO, walked through the financing process and said the data room should be ready by 2025-11-20.
      
      Notes:
      The company is moving quickly and asked for feedback on terms after Aurora reviews the initial materials.
  - `#3` doc `AUR-EMAIL-008` (semantic_score `0.0191`, dense_candidate_id `densecand_f6643ef52c3e3969d98857def407574259287f2da85f5f1aa1c2a1ccbd4f0bb0`)
    - chunk text:
      From: Alex Chen <alex.chen@heliorobotics.example>
      To: Priya Singh <priya.singh@auroracap.example>
      Cc: Jordan Lee <jordan.lee@auroracap.example>
      Date: 2026-02-12
      Subject: Revised Helio term sheet
      
      Hi Priya,
      
      Thanks for the quick turnaround.
      
      Attached is the updated term sheet for discussion. The company is now proposing an $82M pre-money valuation.
      
      Current draft terms:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - one board observer seat
      
      Let me know if this gets us close enough for the next conversation.
      
      Best,
      Alex Chen
      CFO, Helio Robotics
  - `#4` doc `AUR-EMAIL-001` (semantic_score `0.0189`, dense_candidate_id `densecand_b55347ec4b65c343bc6a7197ba7aa8f11a59e9ca267ad825d1778b53cb16a715`)
    - chunk text:
      From: Jordan Lee <jordan.lee@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Cc: Priya Singh <priya.singh@auroracap.example>
      Date: 2025-11-12
      Subject: Intro: Aurora Capital <> Helio Robotics
      
      Hi Alex,
      
      Great to meet you virtually. As mentioned, I'm Jordan Lee, a Partner at Aurora Capital.
      
      Priya Singh (cc'd) will coordinate next steps with you. If it is easiest, you can treat Priya as the primary point of contact on our side.
      
      Looking forward to learning more about Helio Robotics and the current Series A process.
      
      Best,
      Jordan
  - `#5` doc `AUR-EMAIL-007` (semantic_score `0.0186`, dense_candidate_id `densecand_0ac10015abfd591da1b32df8099467660267d7cecd8adbfa3fe0f3d270988f78`)
    - chunk text:
      From: Priya Singh <priya.singh@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Date: 2026-02-07
      Subject: Aurora counter on Helio term sheet
      
      Hi Alex,
      
      Following up on our internal review, Aurora would be prepared to proceed at a $78M pre-money valuation.
      
      Other proposed terms from our side:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - no board seat
      
      If this is directionally workable, please send through a revised term sheet.
      
      Best,
      Priya

## Query `RAG-005`

- source query: `In 4 bullets, summarize the Helio deal from intro to latest terms.`
- retrieval query: `helio deal summary intro latest terms`
- retrieval mode: `openai_vector_store_search_no_rerank`
- query role: `analyst`
- server-side filters applied: `True`
- server-side filters: `{"filters":[{"key":"tenant_id","type":"eq","value":"t_aurora"},{"key":"sensitivity","type":"nin","value":["confidential"]}],"type":"and"}`
- returned candidates: `5`
- top semantic candidates (ranked):
  - `#1` doc `AUR-EMAIL-008` (semantic_score `0.0325`, dense_candidate_id `densecand_f6643ef52c3e3969d98857def407574259287f2da85f5f1aa1c2a1ccbd4f0bb0`)
    - chunk text:
      From: Alex Chen <alex.chen@heliorobotics.example>
      To: Priya Singh <priya.singh@auroracap.example>
      Cc: Jordan Lee <jordan.lee@auroracap.example>
      Date: 2026-02-12
      Subject: Revised Helio term sheet
      
      Hi Priya,
      
      Thanks for the quick turnaround.
      
      Attached is the updated term sheet for discussion. The company is now proposing an $82M pre-money valuation.
      
      Current draft terms:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - one board observer seat
      
      Let me know if this gets us close enough for the next conversation.
      
      Best,
      Alex Chen
      CFO, Helio Robotics
  - `#2` doc `AUR-DEAL-013` (semantic_score `0.0323`, dense_candidate_id `densecand_cea7aa2760ca71830ff72771b76da1850c9c8ebbc8cb543bdb1841dcdb5a4625`)
    - chunk text:
      Deal Note
      Company: Northwind Bio
      Date: 2026-01-22
      Created by: Priya Singh
      
      Current stage: Diligence
      
      Status summary:
      Northwind Bio remains in diligence pending cleanup of outstanding legal diligence items.
      
      Open items before the deal can move forward:
      - revised IP assignment
      - contractor remediation plan
      
      No other gating items are listed in this note.
  - `#3` doc `AUR-EMAIL-001` (semantic_score `0.0318`, dense_candidate_id `densecand_b55347ec4b65c343bc6a7197ba7aa8f11a59e9ca267ad825d1778b53cb16a715`)
    - chunk text:
      From: Jordan Lee <jordan.lee@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Cc: Priya Singh <priya.singh@auroracap.example>
      Date: 2025-11-12
      Subject: Intro: Aurora Capital <> Helio Robotics
      
      Hi Alex,
      
      Great to meet you virtually. As mentioned, I'm Jordan Lee, a Partner at Aurora Capital.
      
      Priya Singh (cc'd) will coordinate next steps with you. If it is easiest, you can treat Priya as the primary point of contact on our side.
      
      Looking forward to learning more about Helio Robotics and the current Series A process.
      
      Best,
      Jordan
  - `#4` doc `AUR-MEET-002` (semantic_score `0.0313`, dense_candidate_id `densecand_26d70ead81752d5377a108f17bb4e0c121a301b4cacb43e93ae996a7f30eb94a`)
    - chunk text:
      Meeting Title: Helio Robotics - Introductory Diligence Call
      Date: 2025-11-15
      Attendees:
      - Jordan Lee, Partner, Aurora Capital
      - Priya Singh, Associate, Aurora Capital
      - Alex Chen, CFO, Helio Robotics
      
      Helio is raising $18M in its Series A at a $90M pre-money valuation.
      
      Current topline metrics discussed on the call:
      - ARR: $4.2M
      - Main risk raised by the company: supply chain volatility for a key hardware component
      
      Alex Chen, CFO, walked through the financing process and said the data room should be ready by 2025-11-20.
      
      Notes:
      The company is moving quickly and asked for feedback on terms after Aurora reviews the initial materials.
  - `#5` doc `AUR-EMAIL-007` (semantic_score `0.0310`, dense_candidate_id `densecand_0ac10015abfd591da1b32df8099467660267d7cecd8adbfa3fe0f3d270988f78`)
    - chunk text:
      From: Priya Singh <priya.singh@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Date: 2026-02-07
      Subject: Aurora counter on Helio term sheet
      
      Hi Alex,
      
      Following up on our internal review, Aurora would be prepared to proceed at a $78M pre-money valuation.
      
      Other proposed terms from our side:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - no board seat
      
      If this is directionally workable, please send through a revised term sheet.
      
      Best,
      Priya

## Query `RAG-006`

- source query: `Do we have any internal codename tied to Helio, and if so, what business issue is attached to it?`
- retrieval query: `internal codename helio business issue`
- retrieval mode: `openai_vector_store_search_no_rerank`
- query role: `partner`
- server-side filters applied: `True`
- server-side filters: `{"filters":[{"key":"tenant_id","type":"eq","value":"t_aurora"}],"type":"and"}`
- returned candidates: `6`
- top semantic candidates (ranked):
  - `#1` doc `AUR-MEET-002` (semantic_score `0.0320`, dense_candidate_id `densecand_26d70ead81752d5377a108f17bb4e0c121a301b4cacb43e93ae996a7f30eb94a`)
    - chunk text:
      Meeting Title: Helio Robotics - Introductory Diligence Call
      Date: 2025-11-15
      Attendees:
      - Jordan Lee, Partner, Aurora Capital
      - Priya Singh, Associate, Aurora Capital
      - Alex Chen, CFO, Helio Robotics
      
      Helio is raising $18M in its Series A at a $90M pre-money valuation.
      
      Current topline metrics discussed on the call:
      - ARR: $4.2M
      - Main risk raised by the company: supply chain volatility for a key hardware component
      
      Alex Chen, CFO, walked through the financing process and said the data room should be ready by 2025-11-20.
      
      Notes:
      The company is moving quickly and asked for feedback on terms after Aurora reviews the initial materials.
  - `#2` doc `AUR-EMAIL-007` (semantic_score `0.0320`, dense_candidate_id `densecand_0ac10015abfd591da1b32df8099467660267d7cecd8adbfa3fe0f3d270988f78`)
    - chunk text:
      From: Priya Singh <priya.singh@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Date: 2026-02-07
      Subject: Aurora counter on Helio term sheet
      
      Hi Alex,
      
      Following up on our internal review, Aurora would be prepared to proceed at a $78M pre-money valuation.
      
      Other proposed terms from our side:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - no board seat
      
      If this is directionally workable, please send through a revised term sheet.
      
      Best,
      Priya
  - `#3` doc `AUR-EMAIL-008` (semantic_score `0.0320`, dense_candidate_id `densecand_f6643ef52c3e3969d98857def407574259287f2da85f5f1aa1c2a1ccbd4f0bb0`)
    - chunk text:
      From: Alex Chen <alex.chen@heliorobotics.example>
      To: Priya Singh <priya.singh@auroracap.example>
      Cc: Jordan Lee <jordan.lee@auroracap.example>
      Date: 2026-02-12
      Subject: Revised Helio term sheet
      
      Hi Priya,
      
      Thanks for the quick turnaround.
      
      Attached is the updated term sheet for discussion. The company is now proposing an $82M pre-money valuation.
      
      Current draft terms:
      - 1x non-participating liquidation preference
      - pro-rata participation rights
      - one board observer seat
      
      Let me know if this gets us close enough for the next conversation.
      
      Best,
      Alex Chen
      CFO, Helio Robotics
  - `#4` doc `AUR-MEMO-005` (semantic_score `0.0318`, dense_candidate_id `densecand_3ab5f043d16c6abf9b5a03b20938a4a44513558565d9656117eca40a878d9f58`)
    - chunk text:
      Aurora Capital
      Confidential Internal Memo
      Date: 2026-01-20
      Created by: Jordan Lee
      Company: Helio Robotics
      
      Project Sunflower is the internal codename being used for the Helio Robotics situation.
      
      Separate from the financing discussion, there may be potential acquisition interest from OmniDynamics. This is early and unconfirmed, but it is relevant context for partner-level review.
      
      Key diligence concern:
      Customer concentration remains elevated. Helio's top 2 customers account for 38% of revenue.
      
      This memo is confidential and should not be forwarded outside the partnership.
  - `#5` doc `AUR-EMAIL-001` (semantic_score `0.0310`, dense_candidate_id `densecand_b55347ec4b65c343bc6a7197ba7aa8f11a59e9ca267ad825d1778b53cb16a715`)
    - chunk text:
      From: Jordan Lee <jordan.lee@auroracap.example>
      To: Alex Chen <alex.chen@heliorobotics.example>
      Cc: Priya Singh <priya.singh@auroracap.example>
      Date: 2025-11-12
      Subject: Intro: Aurora Capital <> Helio Robotics
      
      Hi Alex,
      
      Great to meet you virtually. As mentioned, I'm Jordan Lee, a Partner at Aurora Capital.
      
      Priya Singh (cc'd) will coordinate next steps with you. If it is easiest, you can treat Priya as the primary point of contact on our side.
      
      Looking forward to learning more about Helio Robotics and the current Series A process.
      
      Best,
      Jordan
