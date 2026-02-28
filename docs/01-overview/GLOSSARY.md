# Glossary

- Raw Message: Original Telegram bulletin persisted in `raw_messages` without semantic reinterpretation.
- Wire Bulletin: Headline/ticker-style short update from a source feed (often urgent, repetitive, and attribution-heavy).
- Observation: One incoming bulletin record describing a reported development.
- Reported Claim: The literal claim made by a bulletin source, not a confirmed fact.
- Claim vs Confirmed Fact: Claim is what is reported now; confirmation requires separate later validation.
- Attribution Signal: Source context in the bulletin (publisher tag, dateline, quoted official/source wording).
- Normalization: Deterministic preprocessing that reduces formatting noise before extraction.
- Extraction: Structured representation of the reported claim.
- Confidence: Confidence in extraction/classification quality, not truth.
- Impact Score: Significance of the claim if taken at face value, not factual certainty.
- Event Fingerprint: Stable key used to cluster related observations.
- Event Cluster: Evolving canonical event built from multiple related observations.
- Observation vs Event Cluster: Observation is one message; event cluster is the merged evolving story.
- Routing Decision: Deterministic triage output (`store_to`, priority, flags, event action).
- Deferred Validation: Later selective process that confirms/denies/enriches reported claims.
- Scheduled Reporting: Digest/report generation from structured event data at a fixed cadence.
