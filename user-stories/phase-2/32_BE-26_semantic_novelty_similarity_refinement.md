### Story BE-26 - Add semantic novelty refinement for enrichment candidate deduplication

* **Story ID**: BE-26
* **Status**: future
* **Title**: Extend novelty filtering with semantic similarity once deterministic heuristics saturate
* **As a**: Backend engineer
* **I want**: A controlled semantic similarity layer for near-duplicate detection among enrichment candidates.
* **So that**: Repetitive paraphrases can be suppressed beyond deterministic key-based matching.

#### Preconditions

* Deterministic novelty heuristics (lineage/cluster/title/entity-time overlap) are active.
* Evaluation fixture set exists for false-positive/false-negative review.

#### Acceptance Criteria

* Semantic similarity is introduced behind a feature flag.
* Deterministic heuristics remain first-pass gate; semantic check is second-pass refinement.
* Precision/recall metrics are documented against a fixed evaluation fixture set.
* Rule outcomes remain auditable with explainable reason codes.

#### Out-of-scope

* End-to-end learned ranking replacement for triage.
