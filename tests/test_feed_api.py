from __future__ import annotations

import datetime as dt
import itertools
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


_EVENT_COUNTER = itertools.count(1)


@pytest.fixture
def client_and_session():
    from app.db import Base, get_db
    from app.main import create_app
    from app.models import Event

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        yield client, testing_session_local, Event
    finally:
        app.dependency_overrides.clear()
        client.close()
        engine.dispose()


def _insert_event(
    session_factory,
    event_model,
    *,
    event_time: dt.datetime | None,
    summary: str | None,
    topic: str = "macro_econ",
) -> int:
    idx = next(_EVENT_COUNTER)
    with session_factory() as db:
        event = event_model(
            event_fingerprint=f"feed-fingerprint-{idx}",
            topic=topic,
            summary_1_sentence=summary,
            impact_score=50.0,
            is_breaking=False,
            breaking_window="none",
            event_time=event_time,
            last_updated_at=event_time or dt.datetime(2026, 3, 1, 0, 0, 0),
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event.id


def test_feed_response_shape_and_summary_filtering(client_and_session):
    client, session_factory, event_model = client_and_session
    _insert_event(
        session_factory,
        event_model,
        event_time=dt.datetime(2026, 3, 1, 20, 28, 48),
        summary="US CPI rose 0.4% m/m in February.",
        topic="macro_econ",
    )
    _insert_event(
        session_factory,
        event_model,
        event_time=dt.datetime(2026, 3, 1, 20, 28, 47),
        summary="   ",
        topic="macro_econ",
    )
    _insert_event(
        session_factory,
        event_model,
        event_time=dt.datetime(2026, 3, 1, 20, 28, 46),
        summary=None,
        topic="macro_econ",
    )

    response = client.get("/api/feed/events")

    assert response.status_code == 200
    payload = response.json()
    assert list(payload.keys()) == ["items", "next_cursor"]
    assert payload["next_cursor"] is None
    assert len(payload["items"]) == 1

    item = payload["items"][0]
    assert list(item.keys()) == ["id", "summary", "topic", "event_time"]
    assert item["summary"] == "US CPI rose 0.4% m/m in February."
    assert item["topic"] == "macro_econ"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", item["event_time"])


def test_feed_pagination_cursor_is_deterministic_and_no_overlap(client_and_session):
    client, session_factory, event_model = client_and_session
    t0 = dt.datetime(2026, 3, 1, 20, 0, 0)

    expected_ids = [
        _insert_event(session_factory, event_model, event_time=t0 - dt.timedelta(minutes=offset), summary=f"event {offset}")
        for offset in range(4)
    ]

    first_page = client.get("/api/feed/events", params={"limit": 2})
    assert first_page.status_code == 200
    p1 = first_page.json()
    assert [item["id"] for item in p1["items"]] == expected_ids[:2]
    assert isinstance(p1["next_cursor"], str)

    first_page_repeat = client.get("/api/feed/events", params={"limit": 2})
    assert first_page_repeat.status_code == 200
    p1_repeat = first_page_repeat.json()
    assert p1_repeat["next_cursor"] == p1["next_cursor"]
    assert [item["id"] for item in p1_repeat["items"]] == [item["id"] for item in p1["items"]]

    second_page = client.get("/api/feed/events", params={"limit": 2, "cursor": p1["next_cursor"]})
    assert second_page.status_code == 200
    p2 = second_page.json()
    assert [item["id"] for item in p2["items"]] == expected_ids[2:]
    assert p2["next_cursor"] is None

    ids_page1 = {item["id"] for item in p1["items"]}
    ids_page2 = {item["id"] for item in p2["items"]}
    assert ids_page1.isdisjoint(ids_page2)
    assert ids_page1.union(ids_page2) == set(expected_ids)


def test_feed_ordering_is_stable_with_id_tiebreak(client_and_session):
    client, session_factory, event_model = client_and_session
    same_time = dt.datetime(2026, 3, 1, 21, 0, 0)

    first_id = _insert_event(session_factory, event_model, event_time=same_time, summary="same-time first")
    second_id = _insert_event(session_factory, event_model, event_time=same_time, summary="same-time second")
    older_id = _insert_event(
        session_factory,
        event_model,
        event_time=dt.datetime(2026, 3, 1, 20, 59, 0),
        summary="older",
    )

    response = client.get("/api/feed/events", params={"limit": 10})

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [second_id, first_id, older_id]


def test_feed_topic_filter_and_validation(client_and_session):
    client, session_factory, event_model = client_and_session

    _insert_event(
        session_factory,
        event_model,
        event_time=dt.datetime(2026, 3, 1, 22, 0, 0),
        summary="FX event",
        topic="fx",
    )
    _insert_event(
        session_factory,
        event_model,
        event_time=dt.datetime(2026, 3, 1, 21, 59, 0),
        summary="Macro event",
        topic="macro_econ",
    )

    filtered = client.get("/api/feed/events", params={"topic": "fx"})
    assert filtered.status_code == 200
    payload = filtered.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["topic"] == "fx"
    assert payload["items"][0]["summary"] == "FX event"

    invalid = client.get("/api/feed/events", params={"topic": "invalid_topic"})
    assert invalid.status_code == 422


def test_feed_invalid_cursor_returns_400(client_and_session):
    client, _, _ = client_and_session

    response = client.get("/api/feed/events", params={"cursor": "not-a-valid-cursor"})

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid cursor"
