#!/usr/bin/env python3
"""Clean and assemble manually reviewed PDF display-formula transcriptions.

Read one JSON object from stdin and write a JSON report to stdout. See SKILL.md for
schema. This program deliberately validates and reports questionable syntax but never
invents a correction from a PDF extraction.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Terminal-only artifacts. The tag pattern accepts one non-nested brace group, which
# covers normal equation tags without risking removal from formula interiors.
TERMINAL_TAG = re.compile(r"\s*\\tag\s*\{[^{}]*\}\s*$")
TERMINAL_NUMBER = re.compile(
    r"\s*\\(?:quad|qquad|hspace\s*\{[^{}]*\})\s*\(\s*[0-9]+(?:\.[0-9]+)*\s*\)\s*$"
)
OUTER_DOLLARS = re.compile(r"^\s*\$\$(.*?)\$\$\s*$", re.DOTALL)

# Delimiters occurring after \left or \right. Dot is a legitimate invisible mate.
DELIM_TOKEN = re.compile(
    r"\\(?:left|right)\s*(\\langle|\\rangle|\\vert|\\Vert|\\\||\\\{|\\\}|[.()\[\]|])"
)
LEFT_TO_RIGHT = {
    "(": ")", "[": "]", r"\{": r"\}", r"\langle": r"\rangle",
    "|": "|", r"\|": r"\|", r"\vert": r"\vert", r"\Vert": r"\Vert",
}


def clean_formula(value: str) -> str:
    """Return a one-line formula body after only mandated terminal cleanup."""
    match = OUTER_DOLLARS.match(value)
    body = match.group(1) if match else value
    body = re.sub(r"\s+", " ", body).strip()
    # A formula may have both a terminal tag and extracted terminal numbering; repeat
    # to remove each only when it is actually at the end.
    changed = True
    while changed:
        before = body
        body = TERMINAL_TAG.sub("", body)
        body = TERMINAL_NUMBER.sub("", body)
        changed = body != before
    body = body.rstrip()
    if body.endswith(",") or body.endswith("."):
        body = body[:-1].rstrip()
    return body


def brace_warning(body: str) -> str | None:
    """Conservative group-brace balance check, ignoring escaped literal braces."""
    depth = 0
    for i, char in enumerate(body):
        if char not in "{}":
            continue
        slash_count = 0
        j = i - 1
        while j >= 0 and body[j] == "\\":
            slash_count += 1
            j -= 1
        if slash_count % 2:  # \{ and \} are literal delimiter commands
            continue
        depth += 1 if char == "{" else -1
        if depth < 0:
            return "unmatched closing grouping brace"
    if depth:
        return "unmatched opening grouping brace"
    return None


def delimiter_warnings(body: str) -> list[str]:
    """Return warnings for sequential \left/\right errors without editing body."""
    warnings: list[str] = []
    pending: tuple[str, int] | None = None
    for match in DELIM_TOKEN.finditer(body):
        command = match.group(0).lstrip()[1:].split(None, 1)[0]
        token = match.group(1)
        # Determine command directly because whitespace after command is permitted.
        is_left = re.match(r"\\left\b", match.group(0)) is not None
        if is_left:
            if pending is not None:
                warnings.append("nested or unpaired \\left near character %d" % match.start())
            pending = (token, match.start())
            continue
        if pending is None:
            warnings.append("unpaired \\right near character %d" % match.start())
            continue
        left, position = pending
        pending = None
        # \left. / \right. is valid one-sided delimiter construction.
        expected = LEFT_TO_RIGHT.get(left)
        if left != "." and token != "." and (expected is None or token != expected):
            warnings.append(
                "mismatched \\left%s ... \\right%s near characters %d-%d"
                % (left, token, position, match.start())
            )
    if pending is not None:
        warnings.append("unpaired \\left%s near character %d" % pending)
    return warnings


def validate_list(name: str, raw: Any) -> list[str]:
    if raw is None and name == "corrections":
        return []
    if not isinstance(raw, list):
        raise ValueError("%s must be an array of strings" % name)
    result: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str):
            raise ValueError("%s[%d] must be a string" % (name, index))
        cleaned = clean_formula(value)
        if not cleaned:
            raise ValueError("%s[%d] is empty after cleanup" % (name, index))
        result.append(cleaned)
    return result


def safe_output_path(raw: Any) -> Path:
    if not isinstance(raw, str) or not raw:
        raise ValueError("output_path must be a nonempty string")
    path = Path(raw)
    # Refuse directory targets and the filesystem root. Absolute task destinations and
    # normal relative paths are both supported.
    if path == Path("/") or path.exists() and path.is_dir():
        raise ValueError("output_path must name a file")
    return path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        output = safe_output_path(payload.get("output_path"))
        originals = validate_list("originals", payload.get("originals"))
        corrections = validate_list("corrections", payload.get("corrections"))

        seen: set[str] = set()
        lines: list[str] = []
        warnings: list[str] = []
        written_originals = 0
        written_corrections = 0
        for section, formulas in (("originals", originals), ("corrections", corrections)):
            for index, body in enumerate(formulas):
                if body in seen:
                    warnings.append("duplicate %s[%d] omitted" % (section, index))
                    continue
                seen.add(body)
                issue = brace_warning(body)
                if issue:
                    warnings.append("%s[%d]: %s" % (section, index, issue))
                warnings.extend(
                    "%s[%d]: %s" % (section, index, item)
                    for item in delimiter_warnings(body)
                )
                lines.append("$$" + body + "$$")
                if section == "originals":
                    written_originals += 1
                else:
                    written_corrections += 1

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        report = {
            "output_path": str(output),
            "written": len(lines),
            "originals_written": written_originals,
            "corrections_written": written_corrections,
            "warnings": warnings,
        }
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
