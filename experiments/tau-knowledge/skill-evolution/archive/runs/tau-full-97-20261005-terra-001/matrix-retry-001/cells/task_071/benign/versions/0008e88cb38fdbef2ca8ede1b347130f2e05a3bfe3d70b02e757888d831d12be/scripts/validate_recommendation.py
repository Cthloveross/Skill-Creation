#!/usr/bin/env python3
"""Check a proposed recommendation for supplied disclosure and escalation anchors.

The caller supplies anchors derived from runtime evidence. This script checks only
for omissions and never determines factual correctness.
"""
from __future__ import annotations
import json
import re
import sys
from typing import Any

def norm(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9.%]+", " ", value.casefold()).split())

def phrases(value: Any, path: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        errors.append(f"{path} must be an array of nonempty strings")
        return []
    return value

def audit(payload: Any) -> dict[str, Any]:
    missing_recommendations: list[dict[str, str]] = []
    missing_material_phrases: list[dict[str, str]] = []
    missing_unresolved_handling: list[dict[str, str]] = []
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["input must be a JSON object"], "missing_recommendations": [], "missing_material_phrases": [], "missing_unresolved_handling": []}
    response = payload.get("response")
    if not isinstance(response, str): errors.append("response must be a string"); response = ""
    text = norm(response)
    confirmed, unresolved = payload.get("confirmed", []), payload.get("unresolved", [])
    if not isinstance(confirmed, list): errors.append("confirmed must be an array"); confirmed = []
    if not isinstance(unresolved, list): errors.append("unresolved must be an array"); unresolved = []
    for i, item in enumerate(confirmed):
        path = f"confirmed[{i}]"
        if not isinstance(item, dict): errors.append(f"{path} must be an object"); continue
        account_type, name = item.get("account_type"), item.get("name")
        if not isinstance(account_type, str) or not account_type.strip(): errors.append(f"{path}.account_type must be a nonempty string"); account_type = "unspecified"
        if not isinstance(name, str) or not name.strip(): errors.append(f"{path}.name must be a nonempty string"); continue
        if norm(name) not in text: missing_recommendations.append({"account_type": account_type, "name": name})
        for phrase in phrases(item.get("required_phrases", []), f"{path}.required_phrases", errors):
            if norm(phrase) not in text: missing_material_phrases.append({"account_type": account_type, "name": name, "phrase": phrase})
    for i, item in enumerate(unresolved):
        path = f"unresolved[{i}]"
        if not isinstance(item, dict): errors.append(f"{path} must be an object"); continue
        account_type, requirement = item.get("account_type"), item.get("requirement")
        if not isinstance(account_type, str) or not account_type.strip(): errors.append(f"{path}.account_type must be a nonempty string"); account_type = "unspecified"
        if not isinstance(requirement, str) or not requirement.strip(): errors.append(f"{path}.requirement must be a nonempty string"); requirement = "unspecified requirement"
        anchors = phrases(item.get("required_phrases", []), f"{path}.required_phrases", errors)
        if not anchors: errors.append(f"{path}.required_phrases must identify evidence-gap or review wording")
        for phrase in anchors:
            if norm(phrase) not in text: missing_unresolved_handling.append({"account_type": account_type, "requirement": requirement, "phrase": phrase})
    return {"ok": not errors and not missing_recommendations and not missing_material_phrases and not missing_unresolved_handling, "errors": errors, "missing_recommendations": missing_recommendations, "missing_material_phrases": missing_material_phrases, "missing_unresolved_handling": missing_unresolved_handling}

if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        result = audit(json.loads(raw) if raw.strip() else {})
    except json.JSONDecodeError as exc:
        result = {"ok": False, "errors": [f"invalid JSON: {exc.msg}"], "missing_recommendations": [], "missing_material_phrases": [], "missing_unresolved_handling": []}
    except Exception as exc:
        result = {"ok": False, "errors": [f"unexpected audit error: {type(exc).__name__}"], "missing_recommendations": [], "missing_material_phrases": [], "missing_unresolved_handling": []}
    print(json.dumps(result, sort_keys=True))
