from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


MAX_TEXT = 500


def _truncate(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True)
    if len(text) <= MAX_TEXT:
        return text
    return text[: MAX_TEXT - 3] + "..."


def _section(title: str, value: Any) -> str:
    return f"## {title}\n\n{_truncate(value) if value is not None else 'n/a'}\n"


def render_report(payload: dict[str, Any]) -> str:
    parts = [
        "# Event Debug Report",
        "",
        _section("Root Cause", payload.get("root_cause")),
        _section("Evidence", payload.get("evidence")),
        _section("Proposed Fix", payload.get("proposed_fix")),
        _section("Regression Risk", payload.get("regression_risk")),
        _section("Validation Steps", payload.get("validation_steps")),
    ]
    return "\n".join(parts).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render compact markdown from event-debugger JSON output.")
    parser.add_argument("input_json", help="Input JSON file path or '-' for stdin")
    parser.add_argument("--output", help="Optional output markdown path")
    args = parser.parse_args()

    if args.input_json == "-":
        payload = json.load(sys.stdin)
    else:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")

    markdown = render_report(payload)
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")


if __name__ == "__main__":
    main()
