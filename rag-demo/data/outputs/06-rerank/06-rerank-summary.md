# Step 06 Summaries

## Run configuration

- mixed-granularity fusion config: `dense_rrf_k=60, sparse_rrf_k=60, dense_weight=1.0, sparse_weight=1.0`
- dense input granularity: `chunk`
- sparse input granularity: `document`
- final ranking granularity: `chunk`

## Query `RAG-001`

- company_scope_terms: `(none)`
- role_terms: `(none)`
- query recency intent detected: `True`
- query timeline intent detected: `False`
- selected chunk candidates: `4`

- top mixed-granularity candidates (ranked chunks):
  - `#5` doc `AUR-EMAIL-008` (semantic_rank `1`, parent_sparse_rank `2`, required_terms_match `True`, mixed `0.0325`, boost `0.0800`, score `0.1125`)
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
  - `#4` doc `AUR-EMAIL-007` (semantic_rank `4`, parent_sparse_rank `4`, required_terms_match `True`, mixed `0.0312`, boost `0.0778`, score `0.1091`)
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
  - `#3` doc `AUR-MEET-002` (semantic_rank `3`, parent_sparse_rank `1`, required_terms_match `True`, mixed `0.0323`, boost `0.0613`, score `0.0936`)
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
  - `#2` doc `AUR-EMAIL-001` (semantic_rank `2`, parent_sparse_rank `3`, required_terms_match `True`, mixed `0.0320`, boost `0.0200`, score `0.0520`)
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

## Query `RAG-002`

- company_scope_terms: `(none)`
- role_terms: `(none)`
- query recency intent detected: `True`
- query timeline intent detected: `False`
- selected chunk candidates: `1`

- top mixed-granularity candidates (ranked chunks):
  - `#5` doc `AUR-DEAL-013` (semantic_rank `2`, parent_sparse_rank `1`, required_terms_match `True`, mixed `0.0325`, boost `0.1800`, score `0.2125`)
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

## Query `RAG-003A`

- company_scope_terms: `(none)`
- role_terms: `(none)`
- query recency intent detected: `False`
- query timeline intent detected: `False`
- selected chunk candidates: `4`

- top mixed-granularity candidates (ranked chunks):
  - `#5` doc `AUR-MEET-002` (semantic_rank `3`, parent_sparse_rank `1`, required_terms_match `True`, mixed `0.0323`, boost `0.1400`, score `0.1723`)
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
  - `#4` doc `AUR-EMAIL-008` (semantic_rank `1`, parent_sparse_rank `4`, required_terms_match `True`, mixed `0.0320`, boost `0.1400`, score `0.1720`)
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
  - `#3` doc `AUR-EMAIL-001` (semantic_rank `2`, parent_sparse_rank `3`, required_terms_match `True`, mixed `0.0320`, boost `0.1200`, score `0.1520`)
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
  - `#2` doc `AUR-EMAIL-007` (semantic_rank `4`, parent_sparse_rank `2`, required_terms_match `True`, mixed `0.0318`, boost `0.1200`, score `0.1518`)
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

## Query `RAG-003B`

- company_scope_terms: `(none)`
- role_terms: `(none)`
- query recency intent detected: `False`
- query timeline intent detected: `False`
- selected chunk candidates: `1`

- top mixed-granularity candidates (ranked chunks):
  - `#5` doc `BIR-EMAIL-001` (semantic_rank `1`, parent_sparse_rank `1`, required_terms_match `True`, mixed `0.0328`, boost `0.1200`, score `0.1528`)
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

- company_scope_terms: `(none)`
- role_terms: `(none)`
- query recency intent detected: `False`
- query timeline intent detected: `False`
- selected chunk candidates: `1`

- top mixed-granularity candidates (ranked chunks):
  - `#5` doc `AUR-MEMO-005` (semantic_rank `2`, parent_sparse_rank `1`, required_terms_match `True`, mixed `0.0325`, boost `0.0400`, score `0.0725`)
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

## Query `RAG-004B`

- company_scope_terms: `(none)`
- role_terms: `(none)`
- query recency intent detected: `False`
- query timeline intent detected: `False`
- selected chunk candidates: `0`

- top mixed-granularity candidates: `(none)`

## Query `RAG-005`

- company_scope_terms: `(none)`
- role_terms: `(none)`
- query recency intent detected: `True`
- query timeline intent detected: `True`
- selected chunk candidates: `4`

- top mixed-granularity candidates (ranked chunks):
  - `#5` doc `AUR-EMAIL-008` (semantic_rank `1`, parent_sparse_rank `3`, required_terms_match `True`, mixed `0.0323`, boost `0.0800`, score `0.1123`)
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
  - `#4` doc `AUR-EMAIL-007` (semantic_rank `5`, parent_sparse_rank `4`, required_terms_match `True`, mixed `0.0310`, boost `0.0778`, score `0.1088`)
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
  - `#3` doc `AUR-MEET-002` (semantic_rank `4`, parent_sparse_rank `2`, required_terms_match `True`, mixed `0.0318`, boost `0.0613`, score `0.0931`)
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
  - `#2` doc `AUR-EMAIL-001` (semantic_rank `3`, parent_sparse_rank `1`, required_terms_match `True`, mixed `0.0323`, boost `0.0400`, score `0.0723`)
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

## Query `RAG-006`

- company_scope_terms: `(none)`
- role_terms: `(none)`
- query recency intent detected: `False`
- query timeline intent detected: `False`
- selected chunk candidates: `5`

- top mixed-granularity candidates (ranked chunks):
  - `#5` doc `AUR-MEMO-005` (semantic_rank `4`, parent_sparse_rank `1`, required_terms_match `True`, mixed `0.0320`, boost `0.0600`, score `0.0920`)
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
  - `#4` doc `AUR-EMAIL-007` (semantic_rank `2`, parent_sparse_rank `2`, required_terms_match `True`, mixed `0.0323`, boost `0.0400`, score `0.0723`)
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
  - `#3` doc `AUR-MEET-002` (semantic_rank `1`, parent_sparse_rank `3`, required_terms_match `True`, mixed `0.0323`, boost `0.0200`, score `0.0523`)
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
  - `#2` doc `AUR-EMAIL-008` (semantic_rank `3`, parent_sparse_rank `4`, required_terms_match `True`, mixed `0.0315`, boost `0.0200`, score `0.0515`)
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
  - `#1` doc `AUR-EMAIL-001` (semantic_rank `5`, parent_sparse_rank `5`, required_terms_match `True`, mixed `0.0308`, boost `0.0200`, score `0.0508`)
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
