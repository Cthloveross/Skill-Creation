#!/usr/bin/env python3
"""Find likely Erlang SSH decode/state-dispatch sites without modifying a tree.

Input (stdin): {"root": "...", "terms": ["optional", "search", "terms"]}
Output (stdout): {"root": "...", "terms": [...], "matches": [...]}
"""
import json
import os
import sys
from pathlib import Path

DEFAULT_TERMS = [
    "ssh_msg_channel_open",
    "ssh_msg_channel_request",
    "ssh_msg_service_request",
    "ssh_connection_handler",
    "userauth",
    "authenticated",
    "handle_event",
    "gen_statem",
]


def main() -> int:
    try:
        request = json.load(sys.stdin)
        root_value = request["root"]
        terms = request.get("terms", DEFAULT_TERMS)
        if not isinstance(root_value, str) or not isinstance(terms, list) or not all(isinstance(t, str) for t in terms):
            raise ValueError("root must be a string and terms must be an array of strings")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2

    root = Path(root_value).resolve()
    if not root.is_dir():
        print(json.dumps({"error": "root is not a directory", "root": str(root)}))
        return 2

    lowered = [term.lower() for term in terms if term]
    matches = []
    for directory, dirnames, filenames in os.walk(root):
        # Avoid generated/vendor metadata while retaining OTP applications.
        dirnames[:] = [d for d in dirnames if d not in {".git", "_build", "ebin"}]
        for filename in filenames:
            if not filename.endswith((".erl", ".hrl")):
                continue
            path = Path(directory) / filename
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, start=1):
                found = [terms[i] for i, term in enumerate(lowered) if term in line.lower()]
                if found:
                    start = max(0, number - 2)
                    end = min(len(lines), number + 1)
                    matches.append({
                        "path": str(path.relative_to(root)),
                        "line": number,
                        "terms": found,
                        "context": lines[start:end],
                    })

    print(json.dumps({"root": str(root), "terms": terms, "matches": matches}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
