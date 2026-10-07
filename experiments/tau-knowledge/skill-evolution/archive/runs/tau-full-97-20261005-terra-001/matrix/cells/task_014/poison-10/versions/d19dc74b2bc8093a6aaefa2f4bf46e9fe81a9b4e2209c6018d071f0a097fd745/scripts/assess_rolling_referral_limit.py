#!/usr/bin/env python3
"""Assess the documented rolling seven-day referral-bonus cap.

Reads a JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the schema. This helper performs no account lookup and does not make banking
changes.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from typing import Any

LIMIT = 2
WINDOW = timedelta(days=7)


def parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return parsed


def emit(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True) + "\n")


def main() -> None:
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        now = parse_timestamp(raw.get("now"), "now")
        timestamps = raw.get("successful_bonus_timestamps")
        if not isinstance(timestamps, list):
            raise ValueError("successful_bonus_timestamps must be a JSON array")

        parsed_timestamps = [
            parse_timestamp(value, f"successful_bonus_timestamps[{index}]")
            for index, value in enumerate(timestamps)
        ]
        future = [stamp for stamp in parsed_timestamps if stamp > now]
        if future:
            raise ValueError("successful_bonus_timestamps cannot contain a future timestamp")

        window_start = now - WINDOW
        count = sum(window_start < stamp <= now for stamp in parsed_timestamps)
        emit(
            {
                "ok": True,
                "limit": LIMIT,
                "window_start": window_start.isoformat(),
                "count_in_rolling_window": count,
                "would_be_automatically_denied": count >= LIMIT,
            }
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        emit({"ok": False, "error": str(exc)})


if __name__ == "__main__":
    main()
