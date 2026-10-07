#!/usr/bin/env python3
"""Build a display-LaTeX Markdown file from reviewed JSON candidates.

stdin JSON schema:
 {"originals": [{"formula": str, ...}], "corrections": [{"formula": str, ...}],
  "output_path": str}
stdout JSON schema:
 {"ok": bool, "output_path": str, "original_count": int, "correction_count": int,
  "duplicates_removed": int, "delimiter_issues": [{"section": str,"index": int,
  "formula": str,"issues": [str]}], "errors": [str]}

This program intentionally never guesses a corrected delimiter or command. Human visual
review is required before a correction is supplied.
"""
import json
import os
import re
import sys
import tempfile

# A left/right delimiter can be a character, a TeX escaped character, or a named command.
DELIMITER_TOKENS = [
    r"\\langle", r"\\rangle", r"\\lfloor", r"\\rfloor", r"\\lceil", r"\\rceil",
    r"\\vert", r"\\Vert", r"\\|", r"\\{", r"\\}",
    r"\\[A-Za-z]+", r"\\[^A-Za-z\s]", r"[()\[\]{}|.]",
]
TOKEN_RE = re.compile(r"\\(left|right)\s*(" + "|".join(DELIMITER_TOKENS) + ")")

OPEN_TO_CLOSE = {
    "(": ")", "[": "]", r"\{": r"\}",
    r"\langle": r"\rangle", r"\lfloor": r"\rfloor", r"\lceil": r"\rceil",
    "|": "|", r"\vert": r"\vert", r"\|": r"\|", r"\Vert": r"\Vert",
}


def strip_outer_dollars(value):
    value = value.strip()
    if value.startswith("$$") and value.endswith("$$") and len(value) >= 4:
        return value[2:-2].strip()
    return value


def remove_terminal_tag(value):
    # Standard tags rarely nest. Repeat permits whitespace-separated terminal tags.
    old = None
    while old != value:
        old = value
        value = re.sub(r"\s*\\tag\s*\{[^{}]*\}\s*$", "", value)
    # Equation number is non-mathematical only in an explicit spacing-command tail.
    value = re.sub(
        r"\s*\\(?:quad|qquad|hspace\s*\{[^{}]*\})\s*\(\s*\d+(?:\.\d+)*\s*\)\s*$",
        "", value,
    )
    return value


def normalize_formula(value):
    if not isinstance(value, str):
        raise ValueError("formula must be a string")
    value = strip_outer_dollars(value)
    if "$$" in value:
        raise ValueError("formula contains internal $$ delimiters")
    value = remove_terminal_tag(value)
    value = re.sub(r"\s+", " ", value).strip()
    # Only a literal punctuation glyph at the formula's end is sentence punctuation.
    value = re.sub(r"[,.]\s*$", "", value).rstrip()
    if not value:
        raise ValueError("formula is empty after cleanup")
    return value


def delimiter_issues(formula):
    """Return structural \left/\right concerns without changing formula text."""
    stack = []
    issues = []
    for match in TOKEN_RE.finditer(formula):
        side, token = match.group(1), match.group(2)
        pos = match.start()
        if side == "left":
            stack.append((token, pos))
            continue
        if not stack:
            issues.append("unmatched \\right%s at character %d" % (token, pos))
            continue
        opening, opening_pos = stack.pop()
        # A period is TeX's invisible, intentionally one-sided delimiter.
        expected = OPEN_TO_CLOSE.get(opening)
        if opening == "." or token == ".":
            continue
        if expected is None:
            issues.append("unrecognized \\left delimiter %s at character %d" % (opening, opening_pos))
        elif token != expected:
            issues.append(
                "mismatched pair \\left%s (character %d) and \\right%s (character %d); expected %s"
                % (opening, opening_pos, token, pos, expected)
            )
    for opening, pos in stack:
        issues.append("unmatched \\left%s at character %d" % (opening, pos))
    return issues


def candidate_formula(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict) and "formula" in item:
        return item["formula"]
    raise ValueError("each candidate must be a string or an object with formula")


def main():
    report = {"ok": False, "output_path": None, "original_count": 0,
              "correction_count": 0, "duplicates_removed": 0,
              "delimiter_issues": [], "errors": []}
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
        originals = data.get("originals")
        corrections = data.get("corrections", [])
        output_path = data.get("output_path")
        if not isinstance(originals, list) or not isinstance(corrections, list):
            raise ValueError("originals and corrections must be JSON lists")
        if not isinstance(output_path, str) or not output_path.strip():
            raise ValueError("output_path must be a nonempty string")
        output_path = os.path.abspath(output_path)
        report["output_path"] = output_path

        seen = set()
        cleaned_originals = []
        cleaned_corrections = []
        for section, raw_items, target in (("original", originals, cleaned_originals),
                                           ("correction", corrections, cleaned_corrections)):
            for index, item in enumerate(raw_items):
                formula = normalize_formula(candidate_formula(item))
                if formula in seen:
                    report["duplicates_removed"] += 1
                    continue
                seen.add(formula)
                target.append(formula)
                issues = delimiter_issues(formula)
                if issues:
                    report["delimiter_issues"].append({"section": section, "index": index,
                                                        "formula": formula, "issues": issues})

        lines = ["$$%s$$" % f for f in cleaned_originals + cleaned_corrections]
        if any("\n" in line or not (line.startswith("$$") and line.endswith("$$")) for line in lines):
            raise ValueError("internal output-line validation failed")
        parent = os.path.dirname(output_path) or "."
        if not os.path.isdir(parent):
            raise ValueError("output directory does not exist: %s" % parent)
        fd, temporary = tempfile.mkstemp(prefix=".latex-formulas-", dir=parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lines))
                if lines:
                    handle.write("\n")
            os.replace(temporary, output_path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        report["original_count"] = len(cleaned_originals)
        report["correction_count"] = len(cleaned_corrections)
        report["ok"] = True
    except Exception as exc:
        report["errors"].append(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
