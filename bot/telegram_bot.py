from __future__ import annotations

import html
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv


logger = logging.getLogger("civicquant.telegram_bot")
_ALLOWED_WINDOWS = {"1h", "4h", "24h"}


@dataclass(frozen=True)
class CommandRequest:
    command: str
    topic: str
    window: str


@dataclass(frozen=True)
class BotReply:
    text: str
    parse_mode: str | None = None


@dataclass(frozen=True)
class BotRuntimeConfig:
    tg_bot_token: str
    backend_api_base_url: str
    backend_bot_api_token: str
    request_timeout_seconds: float
    allowed_chat_ids: set[int] | None
    poll_interval_seconds: float


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_bot_runtime_config() -> BotRuntimeConfig:
    load_dotenv()
    token = _require_env("TG_BOT_TOKEN")
    backend_base = _require_env("BACKEND_API_BASE_URL").rstrip("/")
    backend_token = _require_env("BACKEND_BOT_API_TOKEN")
    request_timeout_seconds = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "8"))
    poll_interval_seconds = float(os.getenv("BOT_POLL_INTERVAL_SECONDS", "2.5"))

    allowed_raw = os.getenv("ALLOWED_TELEGRAM_CHAT_IDS", "").strip()
    allowed_chat_ids: set[int] | None = None
    if allowed_raw:
        parsed: set[int] = set()
        for part in allowed_raw.split(","):
            candidate = part.strip()
            if not candidate:
                continue
            parsed.add(int(candidate))
        allowed_chat_ids = parsed

    return BotRuntimeConfig(
        tg_bot_token=token,
        backend_api_base_url=backend_base,
        backend_bot_api_token=backend_token,
        request_timeout_seconds=request_timeout_seconds,
        allowed_chat_ids=allowed_chat_ids,
        poll_interval_seconds=poll_interval_seconds,
    )


def _normalize_topic(value: str) -> str:
    return " ".join(value.strip().split()).lower()


def _usage(command: str) -> str:
    if command == "summary":
        return "Usage: /summary <topic> <1h|4h|24h>"
    return "Usage: /news <topic> <1h|4h|24h>"


def parse_command(text: str | None) -> tuple[CommandRequest | None, str | None]:
    if not isinstance(text, str):
        return None, None
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None, None

    parts = stripped.split()
    if not parts:
        return None, None

    command_token = parts[0].split("@", 1)[0].lower()
    if command_token not in {"/news", "/summary"}:
        return None, None

    command_name = command_token.lstrip("/")
    if len(parts) < 3:
        return None, _usage(command_name)

    window = parts[-1].strip().lower()
    topic = _normalize_topic(" ".join(parts[1:-1]))
    if not topic or window not in _ALLOWED_WINDOWS:
        return None, _usage(command_name)

    return CommandRequest(command=command_name, topic=topic, window=window), None


def _is_allowed_chat(chat_id: int, allowed_chat_ids: set[int] | None) -> bool:
    if allowed_chat_ids is None:
        return True
    return chat_id in allowed_chat_ids


def _format_time(value: str) -> str:
    if not value:
        return "unknown"
    if "T" in value:
        date_part, _, time_part = value.partition("T")
        hhmm = time_part[:5]
        if len(date_part) == 10 and len(hhmm) == 5:
            return f"{date_part} {hhmm}Z"
    return value


def format_news_message(payload: dict[str, Any]) -> str:
    topic = str(payload.get("topic") or "").strip()
    window = str(payload.get("window") or "").strip()
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    count = int(payload.get("count") or len(results))

    lines = [f"<b>News: {html.escape(topic)} ({html.escape(window)})</b>"]
    if not results:
        lines.append("No matching reported developments found.")
        return "\n".join(lines)

    lines.append(f"{count} ranked updates")
    for idx, result in enumerate(results, start=1):
        claim = html.escape(str(result.get("claim") or "Reported development."))
        timestamp = _format_time(str(result.get("timestamp") or ""))
        importance = html.escape(str(result.get("importance") or "low"))
        category = html.escape(str(result.get("category") or "other"))
        score = float(result.get("score") or 0.0)
        lines.append(f"{idx}. <b>{claim}</b>")
        lines.append(
            f"   {html.escape(timestamp)} | {importance} | {category} | score {score:.2f}"
        )
    return "\n".join(lines)


def format_summary_message(payload: dict[str, Any]) -> str:
    topic = html.escape(str(payload.get("topic") or "").strip())
    window = html.escape(str(payload.get("window") or "").strip())
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}

    lines = [f"<b>Summary: {topic} ({window})</b>"]

    def _render_section(label: str, key: str) -> None:
        rows = summary.get(key) if isinstance(summary.get(key), list) else []
        lines.append(f"<b>{label}</b>")
        if not rows:
            lines.append("- None")
            return
        for row in rows[:4]:
            text = html.escape(str(row.get("text") or "").strip() or "No detail.")
            refs = row.get("evidence_refs") if isinstance(row.get("evidence_refs"), list) else []
            refs_text = ", ".join(str(ref) for ref in refs[:3]) if refs else "none"
            lines.append(f"- {text} ({html.escape(refs_text)})")

    _render_section("Key Developments", "key_developments")
    _render_section("Uncertainties", "uncertainties")
    _render_section("Why It Matters", "why_it_matters")
    return "\n".join(lines)


class BackendQueryClient:
    def __init__(self, *, base_url: str, token: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    def _get(self, path: str, *, topic: str, window: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.get(
                url,
                params={"topic": topic, "window": window},
                headers={"Authorization": f"Bearer {self.token}"},
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("backend returned non-object payload")
        return payload

    def get_news(self, *, topic: str, window: str) -> dict[str, Any]:
        return self._get("/api/query/news", topic=topic, window=window)

    def get_summary(self, *, topic: str, window: str) -> dict[str, Any]:
        return self._get("/api/query/summary", topic=topic, window=window)


class TelegramBotApiClient:
    def __init__(self, *, token: str, timeout_seconds: float) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.timeout_seconds = timeout_seconds

    def get_updates(self, *, offset: int | None = None, timeout_seconds: int = 20) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": timeout_seconds}
        if offset is not None:
            params["offset"] = offset
        with httpx.Client(timeout=self.timeout_seconds + float(timeout_seconds)) as client:
            response = client.get(f"{self.base_url}/getUpdates", params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not bool(payload.get("ok")):
            return []
        result = payload.get("result")
        if not isinstance(result, list):
            return []
        return [row for row in result if isinstance(row, dict)]

    def send_message(self, *, chat_id: int, text: str, parse_mode: str | None = None) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/sendMessage",
                json=payload,
            )
        response.raise_for_status()


def handle_group_command(
    *,
    text: str | None,
    chat_id: int,
    allowed_chat_ids: set[int] | None,
    backend_client: BackendQueryClient,
) -> BotReply | None:
    if not _is_allowed_chat(chat_id, allowed_chat_ids):
        return BotReply(text="This bot is not enabled for this chat.", parse_mode=None)

    command, usage_error = parse_command(text)
    if usage_error:
        return BotReply(text=usage_error, parse_mode=None)
    if command is None:
        return None

    started_at = time.perf_counter()
    logger.info(
        "bot_command_received chat_id=%s command=%s topic=%s window=%s",
        chat_id,
        command.command,
        command.topic,
        command.window,
    )
    try:
        if command.command == "news":
            payload = backend_client.get_news(topic=command.topic, window=command.window)
            message = BotReply(text=format_news_message(payload), parse_mode="HTML")
            result_count = int(payload.get("count") or 0)
        else:
            payload = backend_client.get_summary(topic=command.topic, window=command.window)
            message = BotReply(text=format_summary_message(payload), parse_mode="HTML")
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            result_count = len(summary.get("key_developments") or [])
    except (httpx.HTTPError, ValueError):
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        logger.warning(
            "bot_command_failed chat_id=%s command=%s topic=%s window=%s latency_ms=%s",
            chat_id,
            command.command,
            command.topic,
            command.window,
            latency_ms,
        )
        return BotReply(text="Request failed. Please try again shortly.", parse_mode=None)

    latency_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "bot_command_ok chat_id=%s command=%s topic=%s window=%s latency_ms=%s result_count=%s",
        chat_id,
        command.command,
        command.topic,
        command.window,
        latency_ms,
        result_count,
    )
    return message


def run_bot_forever(
    *,
    config: BotRuntimeConfig,
    backend_client: BackendQueryClient | None = None,
    telegram_client: TelegramBotApiClient | None = None,
) -> None:
    backend = backend_client or BackendQueryClient(
        base_url=config.backend_api_base_url,
        token=config.backend_bot_api_token,
        timeout_seconds=config.request_timeout_seconds,
    )
    telegram = telegram_client or TelegramBotApiClient(
        token=config.tg_bot_token,
        timeout_seconds=config.request_timeout_seconds,
    )
    offset: int | None = None

    logger.info(
        "telegram_bot_started backend_api_base_url=%s allowlist_enabled=%s",
        config.backend_api_base_url,
        bool(config.allowed_chat_ids),
    )
    while True:
        try:
            updates = telegram.get_updates(offset=offset, timeout_seconds=20)
            for update in updates:
                update_id = int(update.get("update_id") or 0)
                offset = update_id + 1
                message = update.get("message") if isinstance(update.get("message"), dict) else {}
                if not message:
                    continue
                chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
                chat_type = str(chat.get("type") or "")
                if chat_type not in {"group", "supergroup"}:
                    continue
                chat_id = int(chat.get("id") or 0)
                text = message.get("text") if isinstance(message.get("text"), str) else None
                reply = handle_group_command(
                    text=text,
                    chat_id=chat_id,
                    allowed_chat_ids=config.allowed_chat_ids,
                    backend_client=backend,
                )
                if reply:
                    telegram.send_message(chat_id=chat_id, text=reply.text, parse_mode=reply.parse_mode)
        except Exception as exc:  # noqa: BLE001
            logger.exception("telegram_bot_poll_error error=%s", type(exc).__name__)
            time.sleep(config.poll_interval_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_bot_runtime_config()
    run_bot_forever(config=config)


if __name__ == "__main__":
    main()
