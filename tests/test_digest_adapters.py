from __future__ import annotations

from datetime import datetime, timedelta

from app.config import Settings
from app.digest.adapters.telegram import TelegramDigestAdapter, render_telegram_payload
from app.digest.adapters.x_placeholder import XPlaceholderDigestAdapter
from app.digest.orchestrator import _default_adapters
from app.digest.types import (
    CanonicalDigest,
    DigestBullet,
    DigestWindow,
    SourceDigestEvent,
    TopicSection,
)


def _sample_digest() -> CanonicalDigest:
    now = datetime(2026, 1, 1, 0, 0, 0)
    window = DigestWindow(
        start_utc=now,
        end_utc=now + timedelta(hours=4),
        hours=4,
    )
    source_events = (
        SourceDigestEvent(
            event_id=1,
            topic_raw="fx",
            topic_label="FX",
            summary_1_sentence="Top line chosen by synthesis",
            impact_score=60.0,
            last_updated_at=now + timedelta(minutes=5),
            event_fingerprint="fp-1",
            claim_hash="claim-1",
        ),
        SourceDigestEvent(
            event_id=2,
            topic_raw="fx",
            topic_label="FX",
            summary_1_sentence="Section line",
            impact_score=50.0,
            last_updated_at=now + timedelta(minutes=10),
            event_fingerprint="fp-2",
            claim_hash="claim-2",
        ),
    )

    top_developments = (
        DigestBullet(
            text="Top line chosen by synthesis",
            topic_label=None,
            source_event_ids=(1,),
        ),
    )

    sections = (
        TopicSection(
            topic_label="FX",
            bullets=(
                DigestBullet(
                    text="Section line",
                    topic_label="FX",
                    source_event_ids=(2,),
                ),
            ),
            covered_event_ids=(2,),
        ),
    )

    return CanonicalDigest(
        window=window,
        source_events=source_events,
        top_developments=top_developments,
        sections=sections,
        covered_event_ids=(1, 2),
    )


def test_telegram_payload_uses_canonical_digest_semantics_without_duplicates():
    digest = _sample_digest()
    payload = render_telegram_payload(digest)

    assert "<b>Top developments</b>" in payload
    assert "<b>FX</b>" in payload
    assert payload.count("Top line chosen by synthesis") == 1
    assert payload.count("Section line") == 1
    assert "<i>Covered events: 2</i>" in payload
    assert "<i>Topics: FX 1</i>" in payload


def test_telegram_adapter_does_not_pick_top_items_by_recency():
    now = datetime(2026, 1, 1, 0, 0, 0)
    digest = CanonicalDigest(
        window=DigestWindow(start_utc=now, end_utc=now + timedelta(hours=4), hours=4),
        source_events=(
            SourceDigestEvent(
                event_id=10,
                topic_raw="fx",
                topic_label="FX",
                summary_1_sentence="older, but selected as top",
                impact_score=70.0,
                last_updated_at=now + timedelta(minutes=1),
                event_fingerprint="fp-10",
                claim_hash="claim-10",
            ),
            SourceDigestEvent(
                event_id=11,
                topic_raw="fx",
                topic_label="FX",
                summary_1_sentence="newer section item",
                impact_score=20.0,
                last_updated_at=now + timedelta(minutes=5),
                event_fingerprint="fp-11",
                claim_hash="claim-11",
            ),
        ),
        top_developments=(
            DigestBullet(
                text="older, but selected as top",
                topic_label=None,
                source_event_ids=(10,),
            ),
        ),
        sections=(
            TopicSection(
                topic_label="FX",
                bullets=(
                    DigestBullet(
                        text="newer section item",
                        topic_label="FX",
                        source_event_ids=(11,),
                    ),
                ),
                covered_event_ids=(11,),
            ),
        ),
        covered_event_ids=(10, 11),
    )

    payload = render_telegram_payload(digest)
    assert payload.count("older, but selected as top") == 1
    assert payload.count("newer section item") == 1


def test_telegram_payload_escapes_html_safely():
    digest = _sample_digest()
    digest = CanonicalDigest(
        window=digest.window,
        source_events=digest.source_events,
        top_developments=(
            DigestBullet(
                text="Claimed <unexpected> move",
                topic_label=None,
                source_event_ids=(1,),
            ),
        ),
        sections=digest.sections,
        covered_event_ids=digest.covered_event_ids,
    )

    payload = render_telegram_payload(digest)
    assert "Claimed &lt;unexpected&gt; move" in payload
    assert "Claimed <unexpected> move" not in payload


def test_telegram_adapter_only_transports_payload_not_canonical_text():
    digest = _sample_digest()
    canonical_text = "canonical text payload\n"
    adapter = TelegramDigestAdapter(settings=Settings())

    payload = adapter.render_payload(digest, canonical_text)
    assert payload != canonical_text
    assert "<b>News Digest</b>" in payload
    assert "<i>Window:" in payload
    assert "<i>- Not investment advice.</i>" in payload


def test_x_placeholder_adapter_is_deferred():
    digest = _sample_digest()
    adapter = XPlaceholderDigestAdapter()

    payload = adapter.render_payload(digest, "canonical text payload\n")
    result = adapter.publish(payload)

    assert payload == "canonical text payload\n"
    assert result.status == "deferred"
    assert "deferred" in (result.error or "").lower()


def test_default_adapter_registry_excludes_x_placeholder():
    adapters = _default_adapters(Settings(tg_bot_token="token", tg_vip_chat_id="chat"))
    destinations = [adapter.destination for adapter in adapters]

    assert "x" not in destinations
    assert destinations == ["vip_telegram"]
