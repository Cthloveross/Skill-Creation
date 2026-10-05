#!/usr/bin/env python3
"""Build a focused customer-facing recommendation from verified runtime facts.

Input schema:
{
  "recommendations": [
    {"account_type": "checking", "name": "...", "reasons": ["verified term"],
     "monthly_fee": "optional verified fee", "balance_condition": "optional verified condition",
     "operating_conditions": ["optional verified condition"]}
  ],
  "unresolved": [
    {"account_type": "savings", "requirement": "...", "gap": "...", "offer_review": true}
  ]
}
The script performs no evidence lookup or claim validation.
"""
from __future__ import annotations

import json
import sys
from typing import Any


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: Any, path: str, errors: list[str], required: bool = True) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(not nonempty_string(item) for item in value):
        errors.append(f"{path} must be an array of nonempty strings")
        return []
    return [item.strip() for item in value]


def build(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"response": "", "errors": ["input must be a JSON object"]}
    errors: list[str] = []
    recommendations = payload.get("recommendations", [])
    unresolved = payload.get("unresolved", [])
    if not isinstance(recommendations, list):
        errors.append("recommendations must be an array")
        recommendations = []
    if not isinstance(unresolved, list):
        errors.append("unresolved must be an array")
        unresolved = []

    sections: list[str] = []
    seen_types: set[str] = set()
    for index, item in enumerate(recommendations):
        path = f"recommendations[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        account_type, name = item.get("account_type"), item.get("name")
        if not nonempty_string(account_type):
            errors.append(f"{path}.account_type must be a nonempty string")
            continue
        if not nonempty_string(name):
            errors.append(f"{path}.name must be a nonempty string")
            continue
        normalized_type = account_type.strip().casefold()
        if normalized_type in seen_types:
            errors.append(f"duplicate recommendation account_type: {account_type.strip()}")
            continue
        seen_types.add(normalized_type)
        reasons = string_list(item.get("reasons"), f"{path}.reasons", errors)
        if not reasons:
            continue
        sentence = f"**{account_type.strip().title()}:** I recommend **{name.strip()}**. It meets your stated needs because " + "; ".join(reasons) + "."
        fee = item.get("monthly_fee")
        condition = item.get("balance_condition")
        if fee is not None:
            if not nonempty_string(fee):
                errors.append(f"{path}.monthly_fee must be a nonempty string when supplied")
            else:
                sentence += f" Monthly maintenance fee: {fee.strip()}."
        if condition is not None:
            if not nonempty_string(condition):
                errors.append(f"{path}.balance_condition must be a nonempty string when supplied")
            else:
                sentence += f" Balance condition: {condition.strip()}."
        conditions = string_list(item.get("operating_conditions"), f"{path}.operating_conditions", errors, required=False)
        if conditions:
            sentence += " Also note: " + "; ".join(conditions) + "."
        sections.append(sentence)

    for index, item in enumerate(unresolved):
        path = f"unresolved[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path} must be an object")
            continue
        account_type, requirement, gap = item.get("account_type"), item.get("requirement"), item.get("gap")
        if not all(nonempty_string(value) for value in (account_type, requirement, gap)):
            errors.append(f"{path} requires nonempty account_type, requirement, and gap")
            continue
        offer_review = item.get("offer_review", True)
        if not isinstance(offer_review, bool):
            errors.append(f"{path}.offer_review must be boolean")
            continue
        sentence = f"**{account_type.strip().title()}:** I cannot confirm a product meeting your requirement for {requirement.strip()}, because the supplied materials do not verify {gap.strip()}."
        if offer_review:
            sentence += " I can arrange focused human review of that requirement."
        sections.append(sentence)

    if not sections and not errors:
        errors.append("provide at least one recommendation or unresolved item")
    return {"response": "\n\n".join(sections), "errors": errors}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        result = build(json.loads(raw) if raw.strip() else {})
    except json.JSONDecodeError as exc:
        result = {"response": "", "errors": [f"invalid JSON: {exc.msg}"]}
    except Exception as exc:
        result = {"response": "", "errors": [f"unexpected response-builder error: {type(exc).__name__}"]}
    print(json.dumps(result, sort_keys=True))
