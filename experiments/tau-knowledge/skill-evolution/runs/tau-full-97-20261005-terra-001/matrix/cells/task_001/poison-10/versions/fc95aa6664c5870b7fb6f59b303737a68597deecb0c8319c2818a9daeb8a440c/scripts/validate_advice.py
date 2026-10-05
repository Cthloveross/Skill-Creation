#!/usr/bin/env python3
"""Mechanically check a draft against caller-supplied current-document terms."""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-"})


def fail(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "missing": [], "checks": {}, "errors": errors}


def norm(value: str) -> str:
    return value.translate(DASHES).casefold()


def number(value: Any, label: str, errors: list[str], nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if isinstance(value, bool) or not result.is_finite() or result < 0:
        errors.append(f"{label} must be a finite nonnegative number")
        return None
    return result


def phrases_present(text: str, phrases: Any) -> bool:
    return isinstance(phrases, list) and any(isinstance(item, str) and item and norm(item) in text for item in phrases)


def main(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("response"), str) or not isinstance(data.get("selected_offer"), dict):
        return fail(["input requires response text and selected_offer object"])
    selected, app, errors = data["selected_offer"], data.get("application_terms", {}), []
    if not isinstance(app, dict):
        return fail(["application_terms must be an object"])
    name = selected.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("selected_offer.name must be a nonempty string")
    rate = number(selected.get("cash_back_rate_percent"), "selected_offer.cash_back_rate_percent", errors)
    fee = number(selected.get("annual_fee"), "selected_offer.annual_fee", errors)
    score = number(selected.get("min_credit_score"), "selected_offer.min_credit_score", errors, True)
    prerequisites = selected.get("confirmed_prerequisites", [])
    if not isinstance(prerequisites, list) or any(not isinstance(item, str) or not item for item in prerequisites):
        errors.append("confirmed_prerequisites must be an array of nonempty strings")
    if errors:
        return fail(errors)
    text = norm(data["response"])
    rate_text = re.escape(format(rate.normalize(), "f").rstrip("0").rstrip(".") if rate else "0")
    fee_text = re.escape(format(fee.quantize(Decimal("0.00")), "f"))
    checks = {
        "card_name": norm(name) in text,
        "cash_back_rate": bool(re.search(rate_text + r"\s*%", text)),
        "annual_fee": bool(re.search(r"annual fee.{0,35}(?:\$?" + fee_text + r"|\$?0\b)|(?:\$?" + fee_text + r"|\$?0\b).{0,35}annual fee", text)),
        "minimum_credit_score": score is None or bool(re.search(r"(?:credit score|score).{0,35}" + re.escape(str(int(score))), text)),
        "confirmed_prerequisites": all(norm(item) in text for item in prerequisites),
        "application_channel": phrases_present(text, app.get("channel_phrases", [])),
        "application_preparation": phrases_present(text, app.get("preparation_phrases", [])),
        "application_consent": phrases_present(text, app.get("consent_phrases", [])),
    }
    for check, source in (("application_channel", "channel_phrases"), ("application_preparation", "preparation_phrases"), ("application_consent", "consent_phrases")):
        if app.get(source) == []:
            checks[check] = True
    missing = [key for key, value in checks.items() if not value]
    return {"ok": not missing, "missing": missing, "checks": checks, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps(fail([f"invalid JSON input: {exc.msg}"]), sort_keys=True))
