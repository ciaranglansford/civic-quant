from __future__ import annotations

from datetime import datetime

from app.contexts.enrichment.provider_contracts import EnrichmentRequest, EnrichmentResult
from app.contexts.triage.opportunity_contracts import OpportunityScoreResult
from app.digest.contracts import InvestmentBrief, ThesisCard


def test_enrichment_contracts_are_instantiable():
    request = EnrichmentRequest(event_id=123, requested_at=datetime.utcnow(), reason_codes=("enrichment:selected",))
    result = EnrichmentResult(provider_name="provider-x", status="ok", evidence_summary="linked source", payload={"k": "v"})

    assert request.event_id == 123
    assert result.provider_name == "provider-x"
    assert result.payload == {"k": "v"}


def test_opportunity_score_result_contract_is_instantiable():
    result = OpportunityScoreResult(score=72.5, confidence=0.8, rationale_codes=("transmission:strong",))
    assert result.score == 72.5
    assert result.confidence == 0.8
    assert result.rationale_codes == ("transmission:strong",)


def test_digest_future_reporting_contracts_are_instantiable():
    card = ThesisCard(
        event_id=7,
        title="Rates shock",
        thesis="Policy surprise can spill into funding and FX.",
        confidence=0.76,
        risks=("positioning washout",),
    )
    brief = InvestmentBrief(period_label="2026-W11", cards=(card,), summary="One high-conviction setup.")

    assert brief.period_label == "2026-W11"
    assert brief.cards[0].event_id == 7
