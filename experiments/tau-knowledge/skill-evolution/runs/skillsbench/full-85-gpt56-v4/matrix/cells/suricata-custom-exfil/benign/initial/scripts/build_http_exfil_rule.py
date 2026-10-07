#!/usr/bin/env python3
"""Build a strict HTTP/URL-form Suricata exfiltration signature.

Read one JSON object from stdin and emit one JSON object on stdout.  See
SKILL.md for the schema.  Supplying output_path optionally writes the rule.
"""

import json
import os
import re
import sys
from typing import Any, Dict


def fail(message: str) -> None:
    print(json.dumps({"error": message}), file=sys.stdout)
    raise SystemExit(2)


def require_string(data: Dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        fail(f"{key} must be a non-empty string")
    if "\n" in value or "\r" in value or "\x00" in value:
        fail(f"{key} may not contain newline or NUL characters")
    return value


def require_positive_int(data: Dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        fail(f"{key} must be a positive integer")
    return value


def pcre_literal(value: str) -> str:
    """Escape a literal for a slash-delimited PCRE option."""
    return re.escape(value).replace("/", r"\/")


def build_rule(data: Dict[str, Any]) -> str:
    sid = require_positive_int(data, "sid")
    message = require_string(data, "message")
    method = require_string(data, "method")
    path = require_string(data, "path")
    header_name = require_string(data, "header_name")
    header_value = require_string(data, "header_value")
    blob_parameter = require_string(data, "blob_parameter")
    minimum_blob_chars = require_positive_int(data, "minimum_blob_chars")
    signature_parameter = require_string(data, "signature_parameter")
    signature_hex_chars = require_positive_int(data, "signature_hex_chars")

    if '"' in message:
        fail("message may not contain a double quote")
    # Field-name syntax is deliberately restricted because these values are
    # inserted next to '=' in URL-form field expressions.
    for key, value in (("blob_parameter", blob_parameter),
                       ("signature_parameter", signature_parameter)):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            fail(f"{key} must contain only letters, digits, _, ., or -")

    method_re = pcre_literal(method)
    path_re = pcre_literal(path)
    header_name_re = pcre_literal(header_name)
    header_value_re = pcre_literal(header_value)
    blob_re = pcre_literal(blob_parameter)
    signature_re = pcre_literal(signature_parameter)

    # The inline i modifier applies to the header name only. HTTP header
    # names are case-insensitive, while a custom header value can remain an
    # exact literal as required by the caller.
    header_pattern = (
        r"/(?:^|\r\n)(?i:" + header_name_re + r")[\x20\t]*:"
        r"[\x20\t]*" + header_value_re + r"[\x20\t]*(?:\r\n|$)/"
    )
    blob_pattern = (
        r"/(?:^|&)" + blob_re + r"=[A-Za-z0-9+\/]{" +
        str(minimum_blob_chars) + r",}={0,2}(?=&|$)/"
    )
    signature_pattern = (
        r"/(?:^|&)" + signature_re + r"=[0-9A-Fa-f]{" +
        str(signature_hex_chars) + r"}(?=&|$)/"
    )

    return (
        "alert http any any -> any any "
        "(msg:\"" + message + "\"; "
        "flow:to_server,established; "
        "http.method; pcre:\"/^" + method_re + "$/\"; "
        "http.uri; pcre:\"/^" + path_re + "$/\"; "
        "http.header; pcre:\"" + header_pattern + "\"; "
        "http.request_body; pcre:\"" + blob_pattern + "\"; "
        "pcre:\"" + signature_pattern + "\"; "
        "sid:" + str(sid) + "; rev:1;)"
    )


def maybe_write(rule: str, data: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {"rule": rule, "written": False}
    output_path = data.get("output_path")
    if output_path is None:
        return result
    if not isinstance(output_path, str) or not output_path:
        fail("output_path must be a non-empty string when supplied")
    if "\x00" in output_path:
        fail("output_path may not contain NUL")

    mode = data.get("write_mode", "append_if_absent")
    if mode not in ("append_if_absent", "replace"):
        fail("write_mode must be append_if_absent or replace")

    sid = require_positive_int(data, "sid")
    result["output_path"] = output_path
    if mode == "append_if_absent" and os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as handle:
            old = handle.read()
        if re.search(r"\bsid\s*:\s*" + re.escape(str(sid)) + r"\s*;", old):
            return result
        separator = "" if not old or old.endswith("\n") else "\n"
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(separator + rule + "\n")
    else:
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(rule + "\n")
    result["written"] = True
    return result


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"stdin must be one JSON object: {exc.msg}")
    if not isinstance(data, dict):
        fail("stdin JSON must be an object")
    rule = build_rule(data)
    print(json.dumps(maybe_write(rule, data), sort_keys=True))


if __name__ == "__main__":
    main()
