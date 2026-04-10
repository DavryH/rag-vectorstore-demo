# Step 07 Summaries

## Query `RAG-001`

- question: `What is Helio's latest valuation, and how does it differ from the earlier ask?`
- quote extraction source: `openai_structured_output`
- input candidate count: `4`
- evidence coverage:
  - latest_valuation: supported=True; reason=The 2026-02-12 email explicitly states Helio's latest valuation is $82M pre-money.
  - earlier_valuation: supported=True; reason=The 2025-11-15 meeting notes explicitly state Helio's earlier ask was $90M pre-money.
- extracted quotes:
  - doc `AUR-EMAIL-008` chunk ``: The company is now proposing an $82M pre-money valuation.
  - doc `AUR-MEET-002` chunk ``: Helio is raising $18M in its Series A at a $90M pre-money valuation.

## Query `RAG-002`

- question: `For Northwind Bio, what is the current deal stage and what is it waiting on?`
- quote extraction source: `openai_structured_output`
- input candidate count: `1`
- evidence coverage:
  - current deal stage: supported=False; reason=Supported coverage did not have a matching returned quote after post-processing (likely truncated).
  - what the deal is waiting on: supported=False; reason=Supported coverage did not have a matching returned quote after post-processing (likely truncated).
- extracted quotes:
  - doc `AUR-DEAL-013` chunk ``: Current stage: Diligence
  - doc `AUR-DEAL-013` chunk ``: Northwind Bio remains in diligence pending cleanup of outstanding legal diligence items.
  - doc `AUR-DEAL-013` chunk ``: Open items before the deal can move forward:
- revised IP assignment
- contractor remediation plan

## Query `RAG-003A`

- question: `Who is Alex Chen in Aurora's records, and what company is he associated with?`
- quote extraction source: `openai_structured_output`
- input candidate count: `4`
- evidence coverage:
  - Alex Chen's role: supported=False; reason=Supported coverage did not have a matching returned quote after post-processing (likely truncated).
  - Company associated with Alex Chen: supported=False; reason=Supported coverage did not have a matching returned quote after post-processing (likely truncated).
- extracted quotes:
  - doc `AUR-MEET-002` chunk ``: Alex Chen, CFO, Helio Robotics
  - doc `AUR-EMAIL-008` chunk ``: Alex Chen
CFO, Helio Robotics

## Query `RAG-003B`

- question: `Who is Alex Chen in Birch's records, and what company is he associated with?`
- quote extraction source: `openai_structured_output`
- input candidate count: `1`
- evidence coverage:
  - Alex Chen's role: supported=False; reason=Supported coverage did not have a matching returned quote after post-processing (likely truncated).
  - Company associated with Alex Chen: supported=False; reason=Supported coverage did not have a matching returned quote after post-processing (likely truncated).
- extracted quotes:
  - doc `BIR-EMAIL-001` chunk ``: For the record, I have you listed as VP Sales at Kestrel Payments.

## Query `RAG-004A`

- question: `What is Project Sunflower and what are the related diligence concerns?`
- quote extraction source: `openai_structured_output`
- input candidate count: `1`
- evidence coverage:
  - What is Project Sunflower: supported=True; reason=Supported field quote coverage repaired with deterministic evidence for all required support concepts.
  - Related diligence concerns: supported=True; reason=The text explicitly states the key diligence concern as elevated customer concentration with top 2 customers accounting for 38% of revenue.
- extracted quotes:
  - doc `AUR-MEMO-005` chunk ``: Key diligence concern:
Customer concentration remains elevated. Helio's top 2 customers account for 38% of revenue.
  - doc `AUR-MEMO-005` chunk ``: Project Sunflower is the internal codename being used for the Helio Robotics situation.
  - doc `AUR-MEMO-005` chunk ``: Separate from the financing discussion, there may be potential acquisition interest from OmniDynamics. This is early and unconfirmed, but it is relevant context for partner-level review.

## Query `RAG-004B`

- question: `What is Project Sunflower and what are the related diligence concerns?`
- quote extraction source: `deterministic_no_accessible_evidence`
- input candidate count: `0`
- evidence coverage:
  - anchor_entity_presence: supported=False; reason=Required anchored entity/codename not explicitly present in accessible evidence.
  - entity_grounding: supported=False; reason=no_candidates_after_entity_linking
- extracted quotes: `(none)`

## Query `RAG-005`

- question: `In 4 bullets, summarize the Helio deal from intro to latest terms.`
- quote extraction source: `openai_structured_output`
- input candidate count: `4`
- evidence coverage:
  - intro_contact: supported=True; reason=Initial email from Jordan Lee to Alex Chen on 2025-11-12 establishing contact.
  - initial_terms: supported=True; reason=Meeting notes from 2025-11-15 state $18M raise at $90M pre-money valuation.
  - counter_terms: supported=True; reason=Aurora's counter offer on 2026-02-07 with $78M valuation and term details.
  - latest_terms: supported=True; reason=Helio's revised term sheet on 2026-02-12 with $82M valuation and updated terms.
  - timeline_milestone_repair: supported=True; reason=Applied deterministic timeline milestone coverage checks with conservative merge.
- extracted quotes:
  - doc `AUR-EMAIL-001` chunk ``: Hi Alex,
Great to meet you virtually. As mentioned, I'm Jordan Lee, a Partner at Aurora Capital.
Priya Singh (cc'd) will coordinate next steps with you. If it is easiest, you can treat Priya as the primary point of contact on our side.
  - doc `AUR-MEET-002` chunk ``: Helio is raising $18M in its Series A at a $90M pre-money valuation.
  - doc `AUR-EMAIL-007` chunk ``: Following up on our internal review, Aurora would be prepared to proceed at a $78M pre-money valuation.
Other proposed terms from our side:
- 1x non-participating liquidation preference
- pro-rata participation rights
- no board seat
  - doc `AUR-EMAIL-008` chunk ``: The company is now proposing an $82M pre-money valuation.
Current draft terms:
- 1x non-participating liquidation preference
- pro-rata participation rights
- one board observer seat

## Query `RAG-006`

- question: `Do we have any internal codename tied to Helio, and if so, what business issue is attached to it?`
- quote extraction source: `openai_structured_output`
- input candidate count: `5`
- evidence coverage:
  - internal codename tied to Helio: supported=True; reason=The text explicitly states 'Project Sunflower is the internal codename being used for the Helio Robotics situation.'
  - business issue attached to the internal codename: supported=True; reason=The text explicitly states the key diligence concern as 'Customer concentration remains elevated. Helio's top 2 customers account for 38% of revenue.'
- extracted quotes:
  - doc `AUR-MEMO-005` chunk ``: Key diligence concern:
Customer concentration remains elevated. Helio's top 2 customers account for 38% of revenue.
  - doc `AUR-MEMO-005` chunk ``: Project Sunflower is the internal codename being used for the Helio Robotics situation.
