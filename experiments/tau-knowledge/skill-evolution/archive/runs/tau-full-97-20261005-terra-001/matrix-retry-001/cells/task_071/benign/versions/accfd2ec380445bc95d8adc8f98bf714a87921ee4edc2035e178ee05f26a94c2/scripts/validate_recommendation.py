#!/usr/bin/env python3
"""Audit a proposed account-recommendation response against a normalized ledger.

The caller supplies customer-facing names and disclosure anchors derived from the
runtime evidence. This script performs deterministic omission checks only; it does
not determine whether an anchor is factually correct.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any


def normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9.%]+", " ", value.casefold()).split())


def string_list(value: Any, field: str, errors: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{field} must be an array of nonempty strings")
        return []
    return value


def audit(payload: Any) -> dict[str, Any]:
    errors: list[str] = []
    missing_recommendations: list[dict[str, str]] = []
    missing_material_phrases: list[dict[str, str]] = []
    missing_unresolved_handling: list[dict[str, str]] = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "errors": ["input must be a JSON object"],
            "missing_recommendations": [],
            "missing_material_phrases": [],
            "missing_unresolved_handling": [],
        }

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
        prefix = f"confirmed[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        account_type = item.get("account_type")
        name = item.get("name")
        if not isinstance(account_type, str) or not account_type.strip():
            errors.append(f"{prefix}.account_type must be a nonempty string")
            account_type = "unspecified"
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a nonempty string")
            continue
        if normalize(name) not in text:
            missing_recommendations.append({"account_type": account_type, "name": name})
        for phrase in string_list(item.get("required_phrases", []), f"{prefix}.required_phrases", errors):
            if normalize(phrase) not in text:
                missing_material_phrases.append({
                    "account_type": account_type,
                    "name": name,
                    "phrase": phrase,
                })

    for index, item in enumerate(unresolved):
        prefix = f"unresolved[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        account_type = item.get("account_type")
        requirement = item.get("requirement")
        if not isinstance(account_type, str) or not account_type.strip():
            errors.append(f"{prefix}.account_type must be a nonempty string")
            account_type = "unspecified"
        if not isinstance(requirement, str) or not requirement.strip():
            errors.append(f"{prefix}.requirement must be a nonempty string")
            requirement = "unspecified requirement"
        phrases = string_list(item.get("required_phrases", []), f"{prefix}.required_phrases", errors)
        if not phrases:
            errors.append(f"{prefix}.required_phrases must identify evidence-gap or review wording")
        for phrase in phrases:
            if normalize(phrase) not in text:
                missing_unresolved_handling.append({
                    "account_type": account_type,
                    "requirement": requirement,
                    "phrase": phrase,
                })

    return {
        "ok": not errors and not missing_recommendations and not missing_material_phrases and not missing_unresolved_handling,
        "errors": errors,
        "missing_recommendations": missing_recommendations,
        "missing_material_phrases": missing_material_phrases,
        "missing_unresolved_handling": missing_unresolved_handling,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        result = audit(json.loads(raw) if raw.strip() else {})
    except json.JSONDecodeError as exc:
        result = {
            "ok": False,
            "errors": [f"invalid JSON: {exc.msg}"],
            "missing_recommendations": [],
            "missing_material_phrases": [],
            "missing_unresolved_handling": [],
        }
    except Exception as exc:
        result = {
            "ok": False,
            "errors": [f"unexpected audit error: {type(exc).__name__}"],
            "missing_recommendations": [],
            "missing_material_phrases": [],
            "missing_unresolved_handling": [],
        }
    print(json.dumps(result, sort_keys=True))
