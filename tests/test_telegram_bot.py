from __future__ import annotations

import httpx

from bot.telegram_bot import (
    format_news_message,
    format_summary_message,
    handle_group_command,
    parse_command,
)


class _FakeBackendClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str, str]] = []

    def get_news(self, *, topic: str, window: str):
        self.calls.append(("news", topic, window))
        if self.fail:
            raise httpx.ConnectError("failed")
        return {
            "topic": topic,
            "window": window,
            "count": 1,
            "results": [
                {
                    "event_id": 11,
                    "timestamp": "2026-03-28T11:35:00Z",
                    "source": "telegram:intel_feed",
                    "claim": "Iran reportedly launched missile activity.",
                    "category": "geopolitics",
                    "importance": "high",
                    "score": 0.88,
                    "evidence_refs": ["src_1", "src_2"],
                }
            ],
        }

    def get_summary(self, *, topic: str, window: str):
        self.calls.append(("summary", topic, window))
        if self.fail:
            raise httpx.ConnectError("failed")
        return {
            "topic": topic,
            "window": window,
            "summary": {
                "key_developments": [
                    {"text": "Reported military activity increased.", "evidence_refs": ["evt_11"]}
                ],
                "uncertainties": [
                    {"text": "Casualty figures remain unconfirmed.", "evidence_refs": ["evt_11"]}
                ],
                "why_it_matters": [
                    {"text": "Escalation risk can affect regional oil pricing.", "evidence_refs": ["evt_11"]}
                ],
            },
        }


def test_parse_command_valid_news():
    command, usage = parse_command("/news iran 4h")
    assert usage is None
    assert command is not None
    assert command.command == "news"
    assert command.topic == "iran"
    assert command.window == "4h"


def test_parse_command_usage_errors():
    command, usage = parse_command("/news")
    assert command is None
    assert usage == "Usage: /news <topic> <1h|4h|24h>"

    command, usage = parse_command("/summary iran 3d")
    assert command is None
    assert usage == "Usage: /summary <topic> <1h|4h|24h>"


def test_allowlist_disallows_chat():
    backend = _FakeBackendClient()
    message = handle_group_command(
        text="/news iran 4h",
        chat_id=-200,
        allowed_chat_ids={-100},
        backend_client=backend,
    )
    assert message is not None
    assert message.text == "This bot is not enabled for this chat."
    assert message.parse_mode is None
    assert backend.calls == []


def test_news_formatting_is_compact_and_numbered():
    message = format_news_message(
        {
            "topic": "iran",
            "window": "4h",
            "count": 1,
            "results": [
                {
                    "event_id": 11,
                    "timestamp": "2026-03-28T11:35:00Z",
                    "source": "telegram:intel_feed",
                    "claim": "Iran reportedly launched missile activity.",
                    "category": "geopolitics",
                    "importance": "high",
                    "score": 0.88,
                    "evidence_refs": ["src_1", "src_2"],
                }
            ],
        }
    )
    assert "<b>News: iran (4h)</b>" in message
    assert "1. <b>Iran reportedly launched missile activity.</b>" in message
    assert "refs src_1, src_2" not in message


def test_summary_formatting_includes_uncertainties_and_why_it_matters():
    message = format_summary_message(
        {
            "topic": "iran",
            "window": "4h",
            "summary": {
                "key_developments": [{"text": "Reported military activity increased.", "evidence_refs": ["evt_11"]}],
                "uncertainties": [{"text": "Casualty figures remain unconfirmed.", "evidence_refs": ["evt_11"]}],
                "why_it_matters": [{"text": "Escalation risk can affect energy prices.", "evidence_refs": ["evt_11"]}],
            },
        }
    )
    assert "<b>Summary: iran (4h)</b>" in message
    assert "<b>Uncertainties</b>" in message
    assert "<b>Why It Matters</b>" in message


def test_backend_error_handling_returns_safe_message():
    backend = _FakeBackendClient(fail=True)
    message = handle_group_command(
        text="/news iran 4h",
        chat_id=-100,
        allowed_chat_ids=None,
        backend_client=backend,
    )
    assert message is not None
    assert message.text == "Request failed. Please try again shortly."
    assert message.parse_mode is None


def test_integration_command_to_backend_to_formatted_reply():
    backend = _FakeBackendClient()
    message = handle_group_command(
        text="/summary iran 4h",
        chat_id=-100,
        allowed_chat_ids=None,
        backend_client=backend,
    )
    assert backend.calls == [("summary", "iran", "4h")]
    assert message is not None
    assert message.parse_mode == "HTML"
    assert "<b>Summary: iran (4h)</b>" in message.text
    assert "Casualty figures remain unconfirmed." in message.text
