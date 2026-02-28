### Story BE-12 - Enforce literal reported-claim extraction semantics

* **Story ID**: BE-12
* **Title**: Preserve claim semantics in prompt and validation contract
* **As a**: Backend engineer
* **I want**: Extraction outputs to represent literal reported claims with attribution and uncertainty preserved.
* **So that**: Stage 3 extraction does not implicitly adjudicate truth.

#### Preconditions

* Prompt template loading/versioning is implemented (`app/services/prompt_templates.py`, `app/prompts/extraction_agent_v1.txt`).
* Strict extraction validation exists (`app/services/extraction_validation.py`).

#### Acceptance Criteria

* Prompt contract explicitly instructs literal reported-claim extraction and prohibits factual confirmation language insertion.
* Validation and schema docs preserve these semantics:
  * `confidence` = extraction/classification certainty.
  * `impact_score` = significance if reported claim is taken at face value.
* Extraction persistence path in `app/services/phase2_processing.py` does not introduce derived truth-status fields in first-pass extraction rows.
* Test cases validate semantic handling of uncertain/attributed bulletins:
  * reported claim with explicit uncertainty remains represented as claim text,
  * confidence and impact are accepted without implying confirmation.
* Documentation references in `plans/` and `docs/03-interfaces/` match the same semantic definitions.

#### Out-of-scope

* External corroboration and truth scoring.
