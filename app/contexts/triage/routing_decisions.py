from __future__ import annotations

from sqlalchemy.orm import Session

from ...models import RoutingDecision
from ...schemas import RoutingDecisionData


def upsert_routing_decision(db: Session, raw_message_id: int, decision: RoutingDecisionData) -> int:
    existing = db.query(RoutingDecision).filter(RoutingDecision.raw_message_id == raw_message_id).one_or_none()
    if existing is not None:
        existing.store_to = decision.store_to
        existing.publish_priority = decision.publish_priority
        existing.requires_evidence = decision.requires_evidence
        existing.event_action = decision.event_action
        existing.triage_action = decision.triage_action
        existing.triage_rules = decision.triage_rules
        existing.flags = decision.flags
        db.flush()
        return existing.id

    row = RoutingDecision(
        raw_message_id=raw_message_id,
        store_to=decision.store_to,
        publish_priority=decision.publish_priority,
        requires_evidence=decision.requires_evidence,
        event_action=decision.event_action,
        triage_action=decision.triage_action,
        triage_rules=decision.triage_rules,
        flags=decision.flags,
    )
    db.add(row)
    db.flush()
    return row.id

