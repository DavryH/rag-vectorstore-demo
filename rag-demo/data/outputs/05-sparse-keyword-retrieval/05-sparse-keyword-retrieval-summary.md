# Step 05 Summaries

## Query `RAG-001`

- source query: `What is Helio's latest valuation, and how does it differ from the earlier ask?`
- query role: `analyst`
- access filter applied: `True`
- accessible documents: `5` / `6`
- excluded documents: `1`
- excluded doc ids: `AUR-MEMO-005`
- required sparse terms: `helio`
- include sparse terms: `helio, valuation, latest, difference, earlier, ask`
- phrase terms: `latest valuation, earlier ask`
- excluded terms: `(none)`
- constructed sparse query text: `helio helio valuation latest difference earlier ask latest valuation earlier ask`
- required-term annotation applied: `True`
- required-term annotation status: `required_terms_annotation_ranked`
- candidate coverage: `5` / `5` accessible documents
- required-term matches: `4`
- required-term non-matches: `1`
- required-term zero-match: `False`
- top sparse document candidates (ranked):
  - `#1` doc `AUR-MEET-002` (sparse_score `0.8959`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#2` doc `AUR-EMAIL-008` (sparse_score `0.8076`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#3` doc `AUR-EMAIL-001` (sparse_score `0.8012`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#4` doc `AUR-EMAIL-007` (sparse_score `0.5977`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#5` doc `AUR-DEAL-013` (sparse_score `0.0000`)
    - required_terms_match: `False`
    - required_terms_missing: `helio`
    - document text:
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
- query role: `analyst`
- access filter applied: `True`
- accessible documents: `5` / `6`
- excluded documents: `1`
- excluded doc ids: `AUR-MEMO-005`
- required sparse terms: `northwind bio`
- include sparse terms: `northwind bio, current, deal, stage, waiting`
- phrase terms: `deal stage`
- excluded terms: `(none)`
- constructed sparse query text: `northwind bio northwind bio current deal stage waiting deal stage`
- required-term annotation applied: `True`
- required-term annotation status: `required_terms_annotation_ranked`
- candidate coverage: `5` / `5` accessible documents
- required-term matches: `1`
- required-term non-matches: `4`
- required-term zero-match: `False`
- top sparse document candidates (ranked):
  - `#1` doc `AUR-DEAL-013` (sparse_score `16.9144`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#2` doc `AUR-EMAIL-008` (sparse_score `0.2807`)
    - required_terms_match: `False`
    - required_terms_missing: `northwind bio`
    - document text:
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
  - `#3` doc `AUR-EMAIL-001` (sparse_score `0.2776`)
    - required_terms_match: `False`
    - required_terms_missing: `northwind bio`
    - document text:
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
  - `#4` doc `AUR-MEET-002` (sparse_score `0.2553`)
    - required_terms_match: `False`
    - required_terms_missing: `northwind bio`
    - document text:
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
  - `#5` doc `AUR-EMAIL-007` (sparse_score `0.0000`)
    - required_terms_match: `False`
    - required_terms_missing: `northwind bio`
    - document text:
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
- query role: `analyst`
- access filter applied: `True`
- accessible documents: `5` / `6`
- excluded documents: `1`
- excluded doc ids: `AUR-MEMO-005`
- required sparse terms: `alex chen`
- include sparse terms: `alex chen, aurora, company, association`
- phrase terms: `alex chen, aurora records`
- excluded terms: `(none)`
- constructed sparse query text: `alex chen alex chen aurora company association alex chen aurora records`
- required-term annotation applied: `True`
- required-term annotation status: `required_terms_annotation_ranked`
- candidate coverage: `5` / `5` accessible documents
- required-term matches: `4`
- required-term non-matches: `1`
- required-term zero-match: `False`
- top sparse document candidates (ranked):
  - `#1` doc `AUR-MEET-002` (sparse_score `4.6460`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#2` doc `AUR-EMAIL-007` (sparse_score `3.7453`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#3` doc `AUR-EMAIL-001` (sparse_score `3.5360`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#4` doc `AUR-EMAIL-008` (sparse_score `2.9487`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#5` doc `AUR-DEAL-013` (sparse_score `0.6344`)
    - required_terms_match: `False`
    - required_terms_missing: `alex chen`
    - document text:
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
- query role: `analyst`
- access filter applied: `True`
- accessible documents: `1` / `1`
- excluded documents: `0`
- excluded doc ids: `(none)`
- required sparse terms: `alex chen`
- include sparse terms: `alex chen, birch, company, association`
- phrase terms: `alex chen, birch records`
- excluded terms: `(none)`
- constructed sparse query text: `alex chen alex chen birch company association alex chen birch records`
- required-term annotation applied: `True`
- required-term annotation status: `required_terms_annotation_ranked`
- candidate coverage: `1` / `1` accessible documents
- required-term matches: `1`
- required-term non-matches: `0`
- required-term zero-match: `False`
- top sparse document candidates (ranked):
  - `#1` doc `BIR-EMAIL-001` (sparse_score `2.0960`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
- query role: `partner`
- access filter applied: `True`
- accessible documents: `6` / `6`
- excluded documents: `0`
- excluded doc ids: `(none)`
- required sparse terms: `project sunflower`
- include sparse terms: `project sunflower, diligence, concerns`
- phrase terms: `project sunflower`
- excluded terms: `(none)`
- constructed sparse query text: `project sunflower project sunflower diligence concerns project sunflower`
- required-term annotation applied: `True`
- required-term annotation status: `required_terms_annotation_ranked`
- candidate coverage: `6` / `6` accessible documents
- required-term matches: `1`
- required-term non-matches: `5`
- required-term zero-match: `False`
- top sparse document candidates (ranked):
  - `#1` doc `AUR-MEMO-005` (sparse_score `9.6920`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#2` doc `AUR-DEAL-013` (sparse_score `1.2631`)
    - required_terms_match: `False`
    - required_terms_missing: `project sunflower`
    - document text:
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
  - `#3` doc `AUR-MEET-002` (sparse_score `0.6188`)
    - required_terms_match: `False`
    - required_terms_missing: `project sunflower`
    - document text:
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
  - `#4` doc `AUR-EMAIL-001` (sparse_score `0.0000`)
    - required_terms_match: `False`
    - required_terms_missing: `project sunflower`
    - document text:
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
  - `#5` doc `AUR-EMAIL-007` (sparse_score `0.0000`)
    - required_terms_match: `False`
    - required_terms_missing: `project sunflower`
    - document text:
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

## Query `RAG-004B`

- source query: `What is Project Sunflower and what are the related diligence concerns?`
- query role: `analyst`
- access filter applied: `True`
- accessible documents: `5` / `6`
- excluded documents: `1`
- excluded doc ids: `AUR-MEMO-005`
- required sparse terms: `project sunflower`
- include sparse terms: `project sunflower, diligence, concerns`
- phrase terms: `project sunflower`
- excluded terms: `(none)`
- constructed sparse query text: `project sunflower project sunflower diligence concerns project sunflower`
- required-term annotation applied: `True`
- required-term annotation status: `required_terms_annotation_zero_matches`
- candidate coverage: `5` / `5` accessible documents
- required-term matches: `0`
- required-term non-matches: `5`
- required-term zero-match: `True`
- top sparse document candidates (ranked):
  - `#1` doc `AUR-DEAL-013` (sparse_score `1.5921`)
    - required_terms_match: `False`
    - required_terms_missing: `project sunflower`
    - document text:
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
  - `#2` doc `AUR-MEET-002` (sparse_score `0.7771`)
    - required_terms_match: `False`
    - required_terms_missing: `project sunflower`
    - document text:
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
  - `#3` doc `AUR-EMAIL-001` (sparse_score `0.0000`)
    - required_terms_match: `False`
    - required_terms_missing: `project sunflower`
    - document text:
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
  - `#4` doc `AUR-EMAIL-007` (sparse_score `0.0000`)
    - required_terms_match: `False`
    - required_terms_missing: `project sunflower`
    - document text:
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
  - `#5` doc `AUR-EMAIL-008` (sparse_score `0.0000`)
    - required_terms_match: `False`
    - required_terms_missing: `project sunflower`
    - document text:
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

## Query `RAG-005`

- source query: `In 4 bullets, summarize the Helio deal from intro to latest terms.`
- query role: `analyst`
- access filter applied: `True`
- accessible documents: `5` / `6`
- excluded documents: `1`
- excluded doc ids: `AUR-MEMO-005`
- required sparse terms: `helio`
- include sparse terms: `helio, deal, summary, intro, latest, terms`
- phrase terms: `helio deal, latest terms`
- excluded terms: `(none)`
- constructed sparse query text: `helio helio deal summary intro latest terms helio deal latest terms`
- required-term annotation applied: `True`
- required-term annotation status: `required_terms_annotation_ranked`
- candidate coverage: `5` / `5` accessible documents
- required-term matches: `4`
- required-term non-matches: `1`
- required-term zero-match: `False`
- top sparse document candidates (ranked):
  - `#1` doc `AUR-EMAIL-001` (sparse_score `2.5398`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#2` doc `AUR-MEET-002` (sparse_score `2.3007`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#3` doc `AUR-EMAIL-008` (sparse_score `2.2632`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#4` doc `AUR-EMAIL-007` (sparse_score `2.0163`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#5` doc `AUR-DEAL-013` (sparse_score `6.0691`)
    - required_terms_match: `False`
    - required_terms_missing: `helio`
    - document text:
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

## Query `RAG-006`

- source query: `Do we have any internal codename tied to Helio, and if so, what business issue is attached to it?`
- query role: `partner`
- access filter applied: `True`
- accessible documents: `6` / `6`
- excluded documents: `0`
- excluded doc ids: `(none)`
- required sparse terms: `helio`
- include sparse terms: `helio, internal, codename, business, issue`
- phrase terms: `business issue, internal codename`
- excluded terms: `(none)`
- constructed sparse query text: `helio helio internal codename business issue business issue internal codename`
- required-term annotation applied: `True`
- required-term annotation status: `required_terms_annotation_ranked`
- candidate coverage: `6` / `6` accessible documents
- required-term matches: `5`
- required-term non-matches: `1`
- required-term zero-match: `False`
- top sparse document candidates (ranked):
  - `#1` doc `AUR-MEMO-005` (sparse_score `6.6879`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#2` doc `AUR-EMAIL-007` (sparse_score `2.6528`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#3` doc `AUR-MEET-002` (sparse_score `0.7536`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#4` doc `AUR-EMAIL-008` (sparse_score `0.6795`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
  - `#5` doc `AUR-EMAIL-001` (sparse_score `0.6742`)
    - required_terms_match: `True`
    - required_terms_missing: `(none)`
    - document text:
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
