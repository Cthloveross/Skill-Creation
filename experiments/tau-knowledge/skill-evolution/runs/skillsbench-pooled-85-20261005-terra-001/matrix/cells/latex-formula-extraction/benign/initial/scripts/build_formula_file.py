#!/usr/bin/env python3
"""Clean, order, validate, and write reviewed display-LaTex transcriptions.

Reads JSON from stdin and prints a JSON report.  See SKILL.md for schema.
This program intentionally does not OCR PDFs or make speculative corrections.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# A tag is an equation-label artifact only when it is terminal.  The non-greedy
# body is intentional: nested braces in tags are not normal equation labels.
TRAILING_TAG = re.compile(r"\s*\\tag\*?\s*\{[^{}]*\}\s*$")
# Numbering produced by PDF/OCR recovery, but only when visibly separated by a
# TeX spacing command.  A bare terminal '(1)' may be mathematical content.
TRAILING_SPACED_NUMBER = re.compile(
    r"\s*\\(?:quad|qquad|enspace|hspace\s*\{[^{}]*\}|hfill)\s*"
    r"\(\s*\d+(?:\.\d+)*\s*\)\s*$"
)

# Delimiter capture following \left or \right.  Commands are listed before
# single-character alternatives.  The negative lookahead avoids \leftarrow.
SIDE_RE = re.compile(
    r"\\(?P<side>left|right)(?![A-Za-z])\s*"
    r"(?P<delim>\\(?:langle|rangle|lbrace|rbrace|vert|Vert)|\\[{}|.]|[()\[\]|.])"
)

OPEN_KIND = {
    "(": "paren", "[": "bracket", r"\{": "brace", r"\lbrace": "brace",
    r"\langle": "angle", "|": "bar", r"\vert": "bar", r"\|": "doublebar",
    r"\Vert": "doublebar", ".": "invisible",
}
CLOSE_KIND = {
    ")": "paren", "]": "bracket", r"\}": "brace", r"\rbrace": "brace",
    r"\rangle": "angle", "|": "bar", r"\vert": "bar", r"\|": "doublebar",
    r"\Vert": "doublebar", ".": "invisible",
}


def inner_formula(value: str) -> str:
    """Normalize a reviewed input formula without changing mathematical content."""
    text = value.strip()
    if text.startswith("$$") and text.endswith("$$") and len(text) >= 4:
        text = text[2:-2]
    # PDF/OCR line breaks and extra spaces do not affect math-mode rendering.
    text = re.sub(r"\s+", " ", text).strip()
    # Remove all terminal tags first, allowing a tag plus punctuation artifact.
    while TRAILING_TAG.search(text):
        text = TRAILING_TAG.sub("", text).rstrip()
    text = TRAILING_SPACED_NUMBER.sub("", text).rstrip()
    # User-requested removal of sentence punctuation. Do not strip TeX commands
    # (e.g. \,) or punctuation occurring anywhere other than the final glyph.
    while text.endswith(",") or text.endswith("."):
        text = text[:-1].rstrip()
    return text


def delimiter_issues(formula: str) -> list[dict[str, Any]]:
    """Report unpaired/mismatched \left...\right delimiters without fixing them."""
    pending: list[tuple[str, int, str]] = []
    issues: list[dict[str, Any]] = []
    for match in SIDE_RE.finditer(formula):
        side, delim = match.group("side"), match.group("delim")
        table = OPEN_KIND if side == "left" else CLOSE_KIND
        kind = table.get(delim)
        if kind is None:
            continue
        if side == "left":
            pending.append((kind, match.start(), delim))
            continue
        if not pending:
            issues.append({"kind": "unpaired_right", "position": match.start(), "delimiter": delim})
            continue
        left_kind, left_pos, left_delim = pending.pop()
        # A dot is intentionally one-sided and can pair with any opposite side.
        if left_kind != "invisible" and kind != "invisible" and left_kind != kind:
            issues.append({
                "kind": "mismatched_pair", "left_position": left_pos,
                "left_delimiter": left_delim, "right_position": match.start(),
                "right_delimiter": delim, "expected_kind": left_kind,
            })
    for kind, pos, delim in pending:
        issues.append({"kind": "unpaired_left", "position": pos, "delimiter": delim})
    return issues


def formula_from_item(item: Any, section: str, index: int) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict) and isinstance(item.get("formula"), str):
        return item["formula"]
    raise ValueError(f"{section}[{index}] must be a string or an object containing string key 'formula'")


def main(payload: dict[str, Any]) -> dict[str, Any]:
    originals = payload.get("originals", [])
    corrections = payload.get("corrections", [])
    if not isinstance(originals, list) or not isinstance(corrections, list):
        raise ValueError("'originals' and 'corrections' must both be arrays")
    output_path = payload.get("output_path", "/root/latex_formula_extraction.md")
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("'output_path' must be a nonempty string")

    seen: set[str] = set()
    lines: list[str] = []
    duplicate_count = {"originals": 0, "corrections": 0}
    all_issues: list[dict[str, Any]] = []
    kept = {"originals": 0, "corrections": 0}

    for section, values in (("originals", originals), ("corrections", corrections)):
        for index, item in enumerate(values):
            formula = inner_formula(formula_from_item(item, section, index))
            if not formula:
                raise ValueError(f"{section}[{index}] is empty after cleanup")
            if formula in seen:
                duplicate_count[section] += 1
                continue
            seen.add(formula)
            kept[section] += 1
            lines.append(f"$${formula}$$")
            for issue in delimiter_issues(formula):
                issue.update({"section": section, "input_index": index, "formula": formula})
                all_issues.append(issue)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    # Structural validation of what was actually written.
    written = output.read_text(encoding="utf-8").splitlines()
    valid_file = (
        len(written) == len(lines)
        and all(line.startswith("$$") and line.endswith("$$") and len(line) > 4 for line in written)
        and len(written) == len(set(written))
        and all(line.strip() == line for line in written)
    )
    return {
        "output_path": str(output), "written_formula_count": len(lines),
        "kept": kept, "dropped_duplicates": duplicate_count,
        "delimiter_issues": all_issues, "valid_file": valid_file,
        "note": "Delimiter issues require visual/contextual review; originals are intentionally retained.",
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(data), ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stdout)
        sys.exit(2)
