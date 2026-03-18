from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db import Base
from app.digest.adapters.base import PublishResult
from app.digest.builder import (
    build_deterministic_digest,
    build_source_digest_events,
    pre_dedupe_source_events,
)
from app.digest.orchestrator import run_digest
from app.digest.query import get_events_for_window
from app.digest.types import DigestWindow
from app.models import DigestArtifact, Event, PublishedPost


def _session_factory(db_path: str):
    if os.path.exists(db_path):
        os.remove(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)
    return session_local, engine


def _seed_event(
    db,
    *,
    fingerprint: str,
    topic: str | None,
    summary: str,
    impact: float | None,
    updated_at: datetime,
    claim_hash: str | None = None,
) -> Event:
    row = Event(
        event_fingerprint=fingerprint,
        topic=topic,
        summary_1_sentence=summary,
        impact_score=impact,
        event_time=updated_at,
        last_updated_at=updated_at,
        claim_hash=claim_hash,
    )
    db.add(row)
    db.flush()
    return row


def _digest_settings(**overrides) -> Settings:
    base = {
        "digest_llm_enabled": False,
        "digest_openai_model": "gpt-test",
        "openai_api_key": "test-key",
        "digest_top_developments_limit": 1,
        "digest_section_bullet_limit": 6,
    }
    base.update(overrides)
    return Settings(**base)


class _FakeLlmResponse:
    def __init__(self, raw_text: str) -> None:
        self.raw_text = raw_text


class FakeDigestClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0
        self.last_prompt: str | None = None

    def synthesize(self, prompt_text: str) -> _FakeLlmResponse:
        self.calls += 1
        self.last_prompt = prompt_text
        idx = min(self.calls - 1, len(self._responses) - 1)
        return _FakeLlmResponse(self._responses[idx])


class CapturingAdapter:
    def __init__(self, destination: str = "probe_destination") -> None:
        self.destination = destination
        self.publish_calls = 0
        self.last_digest = None
        self.last_canonical_text: str | None = None

    def render_payload(self, digest, canonical_text):  # noqa: ANN001
        self.last_digest = digest
        self.last_canonical_text = canonical_text
        return canonical_text

    def publish(self, payload: str) -> PublishResult:  # noqa: ARG002
        self.publish_calls += 1
        return PublishResult(status="published", external_ref="ok")


def test_digest_query_selection_window_boundaries_and_ordering():
    db_path = "./test_civicquant_digest_query.db"
    SessionLocal, engine = _session_factory(db_path)

    try:
        with SessionLocal() as db:
            start = datetime(2026, 1, 1, 0, 0, 0)
            end = datetime(2026, 1, 1, 4, 0, 0)

            excluded_before = _seed_event(
                db,
                fingerprint="e-before",
                topic="fx",
                summary="before",
                impact=10.0,
                updated_at=start - timedelta(seconds=1),
            )
            included_start = _seed_event(
                db,
                fingerprint="e-start",
                topic="fx",
                summary="start",
                impact=20.0,
                updated_at=start,
            )
            included_later = _seed_event(
                db,
                fingerprint="e-later",
                topic="fx",
                summary="later",
                impact=30.0,
                updated_at=start + timedelta(hours=1),
            )
            tie_1 = _seed_event(
                db,
                fingerprint="e-tie-1",
                topic="fx",
                summary="tie1",
                impact=40.0,
                updated_at=start + timedelta(hours=1),
            )
            tie_2 = _seed_event(
                db,
                fingerprint="e-tie-2",
                topic="fx",
                summary="tie2",
                impact=50.0,
                updated_at=start + timedelta(hours=1),
            )
            excluded_end = _seed_event(
                db,
                fingerprint="e-end",
                topic="fx",
                summary="end",
                impact=60.0,
                updated_at=end,
            )
            db.commit()

            selected = get_events_for_window(db, window_start_utc=start, window_end_utc=end)
            selected_ids = [row.id for row in selected]

            assert excluded_before.id not in selected_ids
            assert excluded_end.id not in selected_ids
            assert included_start.id in selected_ids
            assert included_later.id in selected_ids
            assert tie_1.id in selected_ids
            assert tie_2.id in selected_ids

            tied_ids_sorted = sorted([included_later.id, tie_1.id, tie_2.id])
            tied_ids_actual = [row.id for row in selected if row.last_updated_at == tie_1.last_updated_at]
            assert tied_ids_actual == tied_ids_sorted
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_pre_dedupe_exact_duplicate_events_are_merged_into_one_bullet():
    db_path = "./test_civicquant_digest_pre_dedupe.db"
    SessionLocal, engine = _session_factory(db_path)

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 2, 0, 0, 0)
            e1 = _seed_event(
                db,
                fingerprint="fx-dup",
                topic="fx",
                summary="Fed reportedly signals intervention.",
                impact=45.0,
                updated_at=now - timedelta(minutes=5),
                claim_hash="claim-dup",
            )
            e2 = _seed_event(
                db,
                fingerprint="fx-dup-2",
                topic="fx",
                summary="Fed reportedly signals intervention",
                impact=44.0,
                updated_at=now - timedelta(minutes=4),
                claim_hash="claim-dup",
            )
            e3 = _seed_event(
                db,
                fingerprint="fx-unique",
                topic="fx",
                summary="USD reportedly rises after policy comments",
                impact=35.0,
                updated_at=now - timedelta(minutes=3),
                claim_hash="claim-unique",
            )
            db.commit()

            source_events = build_source_digest_events([e1, e2, e3])
            source_groups = pre_dedupe_source_events(source_events)
            digest = build_deterministic_digest(
                window=DigestWindow(start_utc=now - timedelta(hours=4), end_utc=now, hours=4),
                source_events=source_events,
                source_groups=source_groups,
                top_developments_limit=0,
                section_bullet_limit=10,
            )

            assert len(source_groups) == 2
            merged_group = next(group for group in source_groups if set(group.source_event_ids) == {e1.id, e2.id})
            assert merged_group.summary_1_sentence.startswith("Fed reportedly")

            all_section_bullets = [bullet for section in digest.sections for bullet in section.bullets]
            assert len(all_section_bullets) == 2
            assert any(set(bullet.source_event_ids) == {e1.id, e2.id} for bullet in all_section_bullets)
            assert set(digest.covered_event_ids) == {e1.id, e2.id, e3.id}
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_fallback_builder_works_when_digest_llm_disabled():
    db_path = "./test_civicquant_digest_fallback.db"
    SessionLocal, engine = _session_factory(db_path)

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 3, 0, 0, 0)
            high = _seed_event(
                db,
                fingerprint="fallback-high",
                topic="fx",
                summary="According to officials, intervention is under review",
                impact=80.0,
                updated_at=now - timedelta(minutes=10),
                claim_hash="fallback-high",
            )
            low = _seed_event(
                db,
                fingerprint="fallback-low",
                topic="fx",
                summary="Desk chatter claimed a smaller move",
                impact=40.0,
                updated_at=now - timedelta(minutes=5),
                claim_hash="fallback-low",
            )
            db.commit()

            adapter = CapturingAdapter(destination="probe_destination")
            settings = _digest_settings(
                digest_llm_enabled=False,
                digest_top_developments_limit=1,
                digest_section_bullet_limit=6,
            )

            with patch("app.digest.orchestrator.get_settings", return_value=settings):
                run_digest(db, window_hours=4, now_utc=now, adapters=[adapter])

            digest = adapter.last_digest
            assert digest is not None
            assert len(digest.top_developments) == 1
            assert set(digest.top_developments[0].source_event_ids) == {high.id}

            section_ids = {event_id for section in digest.sections for event_id in section.covered_event_ids}
            assert high.id not in section_ids
            assert low.id in section_ids
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_synthesis_merges_same_story_and_marks_all_covered_ids_published():
    db_path = "./test_civicquant_digest_synthesis_merge.db"
    SessionLocal, engine = _session_factory(db_path)

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 4, 0, 0, 0)
            e1 = _seed_event(
                db,
                fingerprint="merge-1",
                topic="fx",
                summary="Officials reportedly discussed intervention plans",
                impact=70.0,
                updated_at=now - timedelta(minutes=7),
                claim_hash="merge-1",
            )
            e2 = _seed_event(
                db,
                fingerprint="merge-2",
                topic="fx",
                summary="According to regional press, intervention details emerged",
                impact=68.0,
                updated_at=now - timedelta(minutes=6),
                claim_hash="merge-2",
            )
            e3 = _seed_event(
                db,
                fingerprint="merge-3",
                topic="fx",
                summary="Follow-on reported response in spot markets",
                impact=55.0,
                updated_at=now - timedelta(minutes=5),
                claim_hash="merge-3",
            )
            db.commit()

            payload = {
                "top_developments": [
                    {
                        "text": "Officials reportedly outlined intervention plans, according to local reports.",
                        "source_event_ids": [e1.id, e2.id],
                    }
                ],
                "sections": [
                    {
                        "topic_label": "FX",
                        "bullets": [
                            {
                                "text": "Reported follow-on market reaction was claimed in spot FX.",
                                "source_event_ids": [e3.id],
                            }
                        ],
                    }
                ],
                "excluded_event_ids": [],
            }
            client = FakeDigestClient([json.dumps(payload)])
            adapter = CapturingAdapter(destination="vip_telegram")
            settings = _digest_settings(
                digest_llm_enabled=True,
                digest_openai_model="gpt-test",
                digest_top_developments_limit=2,
            )

            with patch("app.digest.orchestrator.get_settings", return_value=settings):
                result = run_digest(
                    db,
                    window_hours=4,
                    now_utc=now,
                    adapters=[adapter],
                    digest_llm_client=client,
                )

            assert result["status"] == "completed"
            assert client.calls == 1
            digest = adapter.last_digest
            assert digest is not None
            assert set(digest.top_developments[0].source_event_ids) == {e1.id, e2.id}
            section_ids = {event_id for section in digest.sections for event_id in section.covered_event_ids}
            assert section_ids == {e3.id}
            assert set(digest.covered_event_ids) == {e1.id, e2.id, e3.id}

            db.refresh(e1)
            db.refresh(e2)
            db.refresh(e3)
            assert e1.is_published_telegram is True
            assert e2.is_published_telegram is True
            assert e3.is_published_telegram is True
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_invalid_synthesis_response_triggers_fallback_cleanly():
    db_path = "./test_civicquant_digest_invalid_synthesis.db"
    SessionLocal, engine = _session_factory(db_path)

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 5, 0, 0, 0)
            e1 = _seed_event(
                db,
                fingerprint="invalid-1",
                topic="fx",
                summary="Reportedly large intervention signal",
                impact=90.0,
                updated_at=now - timedelta(minutes=9),
                claim_hash="invalid-1",
            )
            e2 = _seed_event(
                db,
                fingerprint="invalid-2",
                topic="fx",
                summary="Claimed smaller follow-up move",
                impact=50.0,
                updated_at=now - timedelta(minutes=8),
                claim_hash="invalid-2",
            )
            db.commit()

            invalid_payload = {
                "top_developments": [
                    {"text": "Top line", "source_event_ids": [e1.id]},
                ],
                "sections": [
                    {
                        "topic_label": "FX",
                        "bullets": [
                            {"text": "Duplicate id line", "source_event_ids": [e1.id]},
                        ],
                    }
                ],
                "excluded_event_ids": [],
            }
            client = FakeDigestClient([json.dumps(invalid_payload)])
            adapter = CapturingAdapter(destination="probe_destination")
            settings = _digest_settings(digest_llm_enabled=True, digest_top_developments_limit=1)

            with patch("app.digest.orchestrator.get_settings", return_value=settings):
                result = run_digest(
                    db,
                    window_hours=4,
                    now_utc=now,
                    adapters=[adapter],
                    digest_llm_client=client,
                )

            assert result["status"] == "completed"
            assert client.calls == 1
            digest = adapter.last_digest
            assert digest is not None
            assert set(digest.top_developments[0].source_event_ids) == {e1.id}
            section_ids = {event_id for section in digest.sections for event_id in section.covered_event_ids}
            assert section_ids == {e2.id}
            assert e1.id not in section_ids
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_artifact_dedupe_is_stable_for_identical_source_input():
    db_path = "./test_civicquant_digest_input_hash.db"
    SessionLocal, engine = _session_factory(db_path)

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 6, 0, 0, 0)
            event = _seed_event(
                db,
                fingerprint="hash-1",
                topic="fx",
                summary="Reported intervention headline",
                impact=60.0,
                updated_at=now - timedelta(minutes=6),
                claim_hash="hash-claim-1",
            )
            db.commit()

            payload_a = {
                "top_developments": [
                    {"text": "Version A reportedly flagged intervention.", "source_event_ids": [event.id]}
                ],
                "sections": [],
                "excluded_event_ids": [],
            }
            payload_b = {
                "top_developments": [
                    {"text": "Version B reportedly flagged intervention.", "source_event_ids": [event.id]}
                ],
                "sections": [],
                "excluded_event_ids": [],
            }
            client = FakeDigestClient([json.dumps(payload_a), json.dumps(payload_b)])
            adapter = CapturingAdapter(destination="probe_destination")
            settings = _digest_settings(digest_llm_enabled=True, digest_top_developments_limit=1)

            with patch("app.digest.orchestrator.get_settings", return_value=settings):
                first = run_digest(
                    db,
                    window_hours=4,
                    now_utc=now,
                    adapters=[adapter],
                    digest_llm_client=client,
                )
                second = run_digest(
                    db,
                    window_hours=4,
                    now_utc=now,
                    adapters=[adapter],
                    digest_llm_client=client,
                )

            assert client.calls == 2
            assert adapter.publish_calls == 1
            assert db.query(DigestArtifact).count() == 1
            artifact = db.query(DigestArtifact).one()
            assert artifact.input_hash is not None
            assert "Version A reportedly flagged intervention." in artifact.canonical_text
            assert first["artifact_id"] == second["artifact_id"]
            assert second["publications"][0]["status"] == "skipped_published"
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_orchestrator_persists_artifact_before_publish_attempt():
    db_path = "./test_civicquant_digest_artifact_first.db"
    SessionLocal, engine = _session_factory(db_path)

    class ProbeAdapter:
        destination = "probe_destination"

        def __init__(self, session_factory):
            self.session_factory = session_factory

        def render_payload(self, digest, canonical_text):  # noqa: ANN001
            return canonical_text

        def publish(self, payload: str) -> PublishResult:  # noqa: ARG002
            with self.session_factory() as verify_db:
                assert verify_db.query(DigestArtifact).count() >= 1
            return PublishResult(status="published", external_ref="probe-ok")

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 7, 0, 0, 0)
            _seed_event(
                db,
                fingerprint="a1",
                topic="fx",
                summary="Artifact first",
                impact=40.0,
                updated_at=now - timedelta(minutes=5),
            )
            db.commit()

            settings = _digest_settings(digest_llm_enabled=False)
            with patch("app.digest.orchestrator.get_settings", return_value=settings):
                out = run_digest(
                    db,
                    window_hours=4,
                    now_utc=now,
                    adapters=[ProbeAdapter(SessionLocal)],
                )

            assert out["status"] == "completed"
            assert db.query(DigestArtifact).count() == 1
            posts = db.query(PublishedPost).all()
            assert len(posts) == 1
            assert posts[0].status == "published"
            assert posts[0].artifact_id is not None
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_orchestrator_filters_out_events_with_impact_25_or_lower():
    db_path = "./test_civicquant_digest_impact_filter.db"
    SessionLocal, engine = _session_factory(db_path)

    try:
        with SessionLocal() as db:
            now = datetime(2026, 1, 8, 0, 0, 0)
            _seed_event(
                db,
                fingerprint="i-low",
                topic="fx",
                summary="Low impact excluded",
                impact=25.0,
                updated_at=now - timedelta(minutes=5),
            )
            _seed_event(
                db,
                fingerprint="i-high",
                topic="fx",
                summary="High impact included",
                impact=26.0,
                updated_at=now - timedelta(minutes=4),
            )
            db.commit()

            adapter = CapturingAdapter(destination="probe_destination")
            settings = _digest_settings(digest_llm_enabled=False)
            with patch("app.digest.orchestrator.get_settings", return_value=settings):
                out = run_digest(db, window_hours=4, now_utc=now, adapters=[adapter])

            assert out["status"] == "completed"
            assert adapter.publish_calls == 1
            artifact = db.query(DigestArtifact).one()
            assert "High impact included" in artifact.canonical_text
            assert "Low impact excluded" not in artifact.canonical_text
    finally:
        engine.dispose()
        if os.path.exists(db_path):
            os.remove(db_path)
