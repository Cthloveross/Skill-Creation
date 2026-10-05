#!/usr/bin/env python3
"""Build an HTTP form-field Suricata rule from JSON and optionally upsert it.

Input: a single JSON object documented in SKILL.md.
Output: {"ok": bool, "rule": str, "changed": bool, "rules_path": str|null}
        or {"ok": false, "error": str}.
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict


def require_text(spec: Dict[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a nonempty string")
    if "\r" in value or "\n" in value:
        raise ValueError(f"{key} may not contain a line break")
    return value


def require_positive_int(spec: Dict[str, Any], key: str, default: int = None) -> int:
    value = spec.get(key, default)
    # bool is an int subclass but is not an acceptable rule number.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a positive integer")
    return value


def pcre_literal(value: str) -> str:
    """Escape an external literal for a slash-delimited PCRE."""
    return re.escape(value).replace("/", r"\/")


def content_literal(value: str) -> str:
    """Escape a literal for Suricata's double-quoted content/message syntax."""
    out = []
    for char in value:
        code = ord(char)
        if char == "\\":
            out.append(r"\\")
        elif char == '"':
            out.append(r"\x22")
        elif 32 <= code <= 126:
            out.append(char)
        else:
            out.append(f"|{code:02X}|")
    return "".join(out)


def build_rule(spec: Dict[str, Any]) -> str:
    sid = require_positive_int(spec, "sid")
    rev = require_positive_int(spec, "rev", 1)
    message = require_text(spec, "message")
    method = require_text(spec, "method")
    uri = require_text(spec, "uri")
    header_name = require_text(spec, "header_name")
    header_value = require_text(spec, "header_value")
    blob_name = require_text(spec, "blob_name")
    minimum = require_positive_int(spec, "min_blob_chars")
    sig_name = require_text(spec, "sig_name")
    hex_length = require_positive_int(spec, "sig_hex_chars")

    # The header-name group alone is case-insensitive. Header values retain
    # their task-defined case semantics.
    header_re = (
        r"(?:^|\r?\n)[ \t]*(?i:" + pcre_literal(header_name) + r")"
        r"[ \t]*:[ \t]*" + pcre_literal(header_value) +
        r"[ \t]*(?=\r?$|\r?\n)"
    )
    # Lookahead counts the complete value (including any legal trailing =)
    # before the value grammar and boundary are consumed.
    blob_re = (
        r"(?:^|[&;])" + pcre_literal(blob_name) + r"="
        r"(?=[A-Za-z0-9+\/=]{" + str(minimum) + r",}(?=[&;]|$))"
        r"[A-Za-z0-9+\/]+={0,2}(?=[&;]|$)"
    )
    sig_re = (
        r"(?:^|[&;])" + pcre_literal(sig_name) + r"="
        r"[0-9A-Fa-f]{" + str(hex_length) + r"}(?=[&;]|$)"
    )

    options = [
        f'msg:"{content_literal(message)}"',
        "flow:established,to_server",
        "http.method",
        f'content:"{content_literal(method)}"',
        "http.uri",
        f'pcre:"/^{pcre_literal(uri)}$/"',
        "http.header",
        f'pcre:"/{header_re}/"',
        "http.request_body",
        f'pcre:"/{blob_re}/"',
        "http.request_body",
        f'pcre:"/{sig_re}/"',
        f"sid:{sid}",
        f"rev:{rev}",
    ]
    return "alert http any any -> any any (" + "; ".join(options) + ";)"


def sid_pattern(sid: int) -> re.Pattern:
    return re.compile(r"\bsid\s*:\s*" + re.escape(str(sid)) + r"\s*;", re.IGNORECASE)


def upsert_rule(rules_path: str, sid: int, rule: str) -> bool:
    path = Path(rules_path)
    if not path.is_file():
        raise ValueError("rules_path must name an existing regular file")
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("rules_path is not UTF-8 text") from exc

    matcher = sid_pattern(sid)
    retained = []
    for line in original.splitlines():
        # Do not remove a comment merely because it documents a SID.
        if matcher.search(line) and not line.lstrip().startswith("#"):
            continue
        retained.append(line)
    updated = "\n".join(retained).rstrip() + "\n" + rule + "\n"
    if updated == original:
        return False

    fd, temporary = tempfile.mkstemp(prefix=".suricata-rule-", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return True


def main() -> int:
    try:
        spec = json.load(sys.stdin)
        if not isinstance(spec, dict):
            raise ValueError("input must be a JSON object")
        rule = build_rule(spec)
        changed = False
        rules_path = spec.get("rules_path")
        if rules_path is not None:
            if not isinstance(rules_path, str) or not rules_path:
                raise ValueError("rules_path must be a nonempty string when supplied")
            changed = upsert_rule(rules_path, require_positive_int(spec, "sid"), rule)
        print(json.dumps({"ok": True, "rule": rule, "changed": changed,
                          "rules_path": rules_path}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
