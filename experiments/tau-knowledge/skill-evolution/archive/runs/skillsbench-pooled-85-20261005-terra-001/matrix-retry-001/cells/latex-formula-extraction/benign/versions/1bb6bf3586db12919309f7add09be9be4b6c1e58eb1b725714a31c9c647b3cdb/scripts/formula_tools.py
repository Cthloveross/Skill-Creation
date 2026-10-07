"""Pure helpers for cleaning and structurally checking display-LaTeX candidates."""
from __future__ import annotations

import re
from typing import Any


def _balanced_end(text: str, start: int) -> int | None:
    """Return the index just after a braced group beginning at start."""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _strip_outer_math(text: str) -> str:
    text = text.strip()
    if text.startswith("$$") and text.endswith("$$") and len(text) >= 4:
        return text[2:-2].strip()
    if text.startswith("\\[") and text.endswith("\\]"):
        return text[2:-2].strip()
    return text


def _remove_tags(text: str) -> str:
    """Remove LaTex \tag{...} constructs while preserving other content."""
    out: list[str] = []
    i = 0
    while i < len(text):
        match = re.match(r"\\tag\*?\s*", text[i:])
        if match:
            group_start = i + match.end()
            group_end = _balanced_end(text, group_start)
            if group_end is not None:
                i = group_end
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def clean_formula(value: str) -> tuple[str, list[str]]:
    """Return normalized formula contents and descriptions of deterministic cleanup."""
    if not isinstance(value, str):
        raise TypeError("formula must be a string")
    changes: list[str] = []
    text = _strip_outer_math(value)
    if text != value.strip():
        changes.append("removed outer display delimiters")
    without_tags = _remove_tags(text)
    if without_tags != text:
        changes.append("removed LaTeX tag")
    text = without_tags
    # A conventional display equation number placed after a spacing command.
    numbered = re.sub(r"\s*\\(?:quad|qquad|hfill)\s*\(\s*[0-9]+(?:\.[0-9]+)*\s*\)\s*$", "", text)
    if numbered != text:
        changes.append("removed trailing equation number")
    text = numbered
    collapsed = re.sub(r"\s+", " ", text).strip()
    if collapsed != text:
        changes.append("normalized whitespace")
    text = collapsed
    # The requested cleanup treats a terminal literal comma/full stop as sentence punctuation.
    if text.endswith((",", ".")):
        text = text[:-1].rstrip()
        changes.append("removed terminal punctuation")
    if not text:
        raise ValueError("formula is empty after cleanup")
    if "\n" in text or "\r" in text:
        raise ValueError("formula contains a newline after cleanup")
    return text, changes


# command/literal token -> logical delimiter family. Dot is compatible with any side.
_LEFT = {"(": "paren", "[": "bracket", "\\{": "brace", "|": "bar", "\\|": "doublebar",
         "\\langle": "angle", "\\lvert": "bar", "\\lVert": "doublebar", ".": "invisible"}
_RIGHT = {")": "paren", "]": "bracket", "\\}": "brace", "|": "bar", "\\|": "doublebar",
          "\\rangle": "angle", "\\rvert": "bar", "\\rVert": "doublebar", ".": "invisible"}


def _delimiter_token(text: str, pos: int) -> tuple[str | None, int]:
    """Read the delimiter immediately after a left/right command, allowing spaces."""
    n = len(text)
    while pos < n and text[pos].isspace():
        pos += 1
    if pos >= n:
        return None, pos
    if text[pos] != "\\":
        return text[pos], pos + 1
    # Delimiter commands are a backslash followed by letters, or escaped punctuation.
    if pos + 1 >= n:
        return "\\", pos + 1
    if text[pos + 1].isalpha():
        end = pos + 2
        while end < n and text[end].isalpha():
            end += 1
        return text[pos:end], end
    return text[pos:pos + 2], pos + 2


def inspect_left_right(text: str) -> dict[str, Any]:
    """Check paired \left/\right constructs without interpreting mathematical meaning."""
    stack: list[tuple[str, int, str]] = []
    issues: list[dict[str, Any]] = []
    i = 0
    marker = re.compile(r"\\(left|right)\b")
    while True:
        found = marker.search(text, i)
        if not found:
            break
        side = found.group(1)
        token, after = _delimiter_token(text, found.end())
        families = _LEFT if side == "left" else _RIGHT
        family = families.get(token or "")
        if family is None:
            issues.append({"kind": "unknown_delimiter", "side": side, "token": token,
                           "position": found.start()})
        elif side == "left":
            stack.append((family, found.start(), token or ""))
        elif not stack:
            issues.append({"kind": "unmatched_right", "token": token, "position": found.start()})
        else:
            left_family, left_pos, left_token = stack.pop()
            if left_family != "invisible" and family != "invisible" and left_family != family:
                issues.append({"kind": "mismatched_pair", "left": left_token, "right": token,
                               "left_position": left_pos, "right_position": found.start(),
                               "suggested_right": _canonical_right(left_family)})
        i = max(after, found.end())
    for family, position, token in stack:
        issues.append({"kind": "unmatched_left", "token": token, "position": position,
                       "suggested_right": _canonical_right(family)})
    return {"valid_left_right": not issues, "issues": issues}


def _canonical_right(family: str) -> str:
    return {"paren": ")", "bracket": "]", "brace": "\\}", "angle": "\\rangle",
            "bar": "|", "doublebar": "\\|", "invisible": "."}.get(family, "?")
