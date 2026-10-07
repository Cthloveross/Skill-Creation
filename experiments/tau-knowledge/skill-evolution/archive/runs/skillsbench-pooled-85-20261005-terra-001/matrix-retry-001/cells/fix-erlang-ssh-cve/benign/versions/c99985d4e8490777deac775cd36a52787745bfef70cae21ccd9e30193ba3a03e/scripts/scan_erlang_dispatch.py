#!/usr/bin/env python3
"""Locate likely SSH inbound-message dispatch sites without modifying the source tree.

Read JSON from stdin and emit JSON to stdout.  See SKILL.md for the schema.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_PATTERNS = [
    "ssh_msg_channel_open",
    "ssh_msg_channel_request",
    "ssh_msg_global_request",
    "ssh_msg_service_request",
]
STATE_WORDS = (
    "hello", "kex", "new_keys", "ext_info", "service", "userauth",
    "auth", "connected", "connection",
)


def context(lines: list[str], line_number: int, radius: int = 3) -> list[dict[str, Any]]:
    start = max(0, line_number - 1 - radius)
    end = min(len(lines), line_number + radius)
    return [
        {"line": index + 1, "text": lines[index]}
        for index in range(start, end)
    ]


def candidate_files(root: Path) -> list[Path]:
    ssh_dir = root / "lib" / "ssh"
    search_root = ssh_dir if ssh_dir.is_dir() else root
    return sorted(path for path in search_root.rglob("*.erl") if path.is_file())


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        root_value = request.get("root")
        if not isinstance(root_value, str) or not root_value:
            raise ValueError("root must be a nonempty string")
        root = Path(root_value).resolve()
        if not root.is_dir():
            raise ValueError("root does not name a directory")
        patterns = request.get("message_patterns", DEFAULT_PATTERNS)
        if (not isinstance(patterns, list) or not patterns or
                not all(isinstance(item, str) and item for item in patterns)):
            raise ValueError("message_patterns must be a nonempty array of strings")
        max_hits = request.get("max_hits", 30)
        if not isinstance(max_hits, int) or isinstance(max_hits, bool) or max_hits < 1:
            raise ValueError("max_hits must be a positive integer")
    except (json.JSONDecodeError, ValueError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 2

    files = candidate_files(root)
    hits: dict[str, list[dict[str, Any]]] = {pattern: [] for pattern in patterns}
    read_errors: list[str] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            read_errors.append(f"{path}: {exc}")
            continue
        lowered = [line.lower() for line in lines]
        for pattern in patterns:
            if len(hits[pattern]) >= max_hits:
                continue
            needle = pattern.lower()
            for index, line in enumerate(lowered):
                if needle not in line:
                    continue
                nearby = " ".join(lowered[max(0, index - 5): index + 1])
                state_words = [word for word in STATE_WORDS if word in nearby]
                hits[pattern].append({
                    "file": str(path.relative_to(root)),
                    "line": index + 1,
                    "nearby_state_words": state_words,
                    "context": context(lines, index + 1),
                })
                if len(hits[pattern]) >= max_hits:
                    break

    result = {
        "ok": True,
        "root": str(root),
        "files_scanned": len(files),
        "patterns": hits,
        "read_errors": read_errors,
        "note": (
            "Occurrences are textual candidates only. Trace state transitions and "
            "callback ordering before deciding where to patch."
        ),
    }
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
