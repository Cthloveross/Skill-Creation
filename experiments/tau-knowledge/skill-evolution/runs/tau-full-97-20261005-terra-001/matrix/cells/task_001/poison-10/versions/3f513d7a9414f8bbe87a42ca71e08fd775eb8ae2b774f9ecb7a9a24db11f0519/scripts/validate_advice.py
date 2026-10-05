#!/usr/bin/env python3
"""Check disclosure coverage in a response against caller-supplied extracted facts."""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-"})


def failure(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "checks": {}, "missing": [], "errors": errors}


def normalized(value: str) -> str:
    return value.translate(DASHES).casefold()


def decimal_value(value: Any, field: str, errors: list[str], nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not number.is_finite() or number < 0:
        errors.append(f"{field} must be finite and nonnegative")
        return None
    return number


def shown(value: Decimal) -> str:
    result = format(value.normalize(), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def main(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("response"), str) or not isinstance(data.get("selected_offer"), dict):
        return failure(["input requires response text and selected_offer object"])
    offer = data["selected_offer"]
    errors: list[str] = []
    name = offer.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("selected_offer.name must be a nonempty string")
    rate = decimal_value(offer.get("cash_back_rate_percent"), "selected_offer.cash_back_rate_percent", errors)
    fee = decimal_value(offer.get("annual_fee"), "selected_offer.annual_fee", errors)
    score = decimal_value(offer.get("min_credit_score"), "selected_offer.min_credit_score", errors, True)
    confirmed = offer.get("confirmed_prerequisites", [])
    if not isinstance(confirmed, list) or any(not isinstance(x, str) or not x.strip() for x in confirmed):
        errors.append("confirmed_prerequisites must be an array of nonempty strings")
    terms = data.get("application_terms", {})
    if not isinstance(terms, dict):
        errors.append("application_terms must be an object")
    if errors:
        return failure(errors)

    text = normalized(data["response"])

    def any_phrase(key: str) -> bool:
        phrases = terms.get(key, [])
        if phrases == []:
            return True
        return isinstance(phrases, list) and any(isinstance(item, str) and item.strip() and normalized(item) in text for item in phrases)

    rate_pattern = re.escape(shown(rate)) + r"\s*%"
    fee_number = re.escape(format(fee.quantize(Decimal("0.00")), "f"))
    checks = {
        "card_name": normalized(name) in text,
        "cash_back_rate": bool(re.search(rate_pattern, text)),
        "annual_fee": bool(re.search(r"annual fee.{0,40}(?:\$?" + fee_number + r"|zero|no)|(?:\$?" + fee_number + r"|zero|no).{0,40}annual fee", text)),
        "minimum_credit_score": score is None or bool(re.search(r"(?:credit score|score).{0,35}" + re.escape(shown(score)), text)),
        "confirmed_prerequisites": all(normalized(item) in text for item in confirmed),
        "application_channel": any_phrase("channel_phrases"),
        "application_preparation": any_phrase("preparation_phrases"),
        "application_consent": any_phrase("consent_phrases"),
        "approval_caveat": "approval" in text and ("credit evaluation" in text or "underwriting" in text),
    }
    missing = [key for key, present in checks.items() if not present]
    return {"ok": not missing, "checks": checks, "missing": missing, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps(failure([f"invalid JSON input: {exc.msg}"]), sort_keys=True))
