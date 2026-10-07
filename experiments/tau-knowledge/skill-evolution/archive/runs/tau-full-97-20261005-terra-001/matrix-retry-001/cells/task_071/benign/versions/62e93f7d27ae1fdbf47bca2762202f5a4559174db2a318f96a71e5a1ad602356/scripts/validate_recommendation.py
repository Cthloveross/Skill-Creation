#!/usr/bin/env python3
"""Check caller-supplied recommendation and escalation wording for omissions.

This helper performs normalized text containment only. Callers must derive all
product facts and required phrases from supplied runtime evidence.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any


def normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9.%]+", " ", value.casefold()).split())


def string_list(value: Any, path: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{path} must be an array of nonempty strings")
        return []
    return value


def missing_phrase(text: str, account_type: str, kind: str, phrase: str, missing: list[dict[str, str]]) -> None:
    if normalize(phrase) not in text:
        missing.append({"account_type": account_type, "kind": kind, "phrase": phrase})


def audit(payload: Any) -> dict[str, Any]:
    errors: list[str] = []
    missing: list[dict[str, str]] = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["input must be a JSON object"], "missing": []}

    response = payload.get("response")
    if not isinstance(response, str):
        errors.append("response must be a string")
        response = ""
    text = normalize(response)

    confirmed = payload.get("confirmed", [])
    unresolved = payload.get("unresolved", [])
    if not isinstance(confirmed, list):
        errors.append("confirmed must be an array")
        confirmed = []
    if not isinstance(unresolved, list):
        errors.append("unresolved must be an array")
        unresolved = []

    for index, item in enumerate(confirmed):
        path = f"confirmed[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        account_type = item.get("account_type")
        if not isinstance(account_type, str) or not account_type.strip():
            errors.append(f"{path}.account_type must be a nonempty string")
            account_type = "unspecified"

        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{path}.name must be a nonempty string")
        else:
            missing_phrase(text, account_type, "product_name", name, missing)

        recommendation = item.get("recommendation_phrase")
        if not isinstance(recommendation, str) or not recommendation.strip():
            errors.append(f"{path}.recommendation_phrase must be a nonempty string")
        else:
            missing_phrase(text, account_type, "recommendation", recommendation, missing)

        for phrase in string_list(item.get("required_phrases", []), f"{path}.required_phrases", errors):
            missing_phrase(text, account_type, "disclosure", phrase, missing)

    for index, item in enumerate(unresolved):
        path = f"unresolved[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        account_type = item.get("account_type")
        if not isinstance(account_type, str) or not account_type.strip():
            errors.append(f"{path}.account_type must be a nonempty string")
            account_type = "unspecified"
        phrases = string_list(item.get("required_phrases", []), f"{path}.required_phrases", errors)
        if not phrases:
            errors.append(f"{path}.required_phrases must include evidence-gap and review wording")
        for phrase in phrases:
            missing_phrase(text, account_type, "unresolved_handling", phrase, missing)

    return {"ok": not errors and not missing, "errors": errors, "missing": missing}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        output = audit(json.loads(raw) if raw.strip() else {})
    except json.JSONDecodeError as exc:
        output = {"ok": False, "errors": [f"invalid JSON: {exc.msg}"], "missing": []}
    except Exception as exc:  # Defensive JSON-only failure behavior.
        output = {"ok": False, "errors": [f"unexpected audit error: {type(exc).__name__}"], "missing": []}
    print(json.dumps(output, sort_keys=True))
