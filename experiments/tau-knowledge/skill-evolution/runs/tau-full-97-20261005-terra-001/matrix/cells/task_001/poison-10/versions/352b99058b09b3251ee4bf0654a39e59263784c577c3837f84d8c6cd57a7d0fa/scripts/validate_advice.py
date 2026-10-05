#!/usr/bin/env python3
"""Check a response draft against caller-supplied selected-card facts."""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-"})


def fail(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "checks": {}, "missing": [], "errors": errors}


def norm(value: str) -> str:
    return value.translate(DASHES).casefold()


def numeric(value: Any, field: str, errors: list[str], nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{field} must be finite and nonnegative")
        return None
    return result


def number_text(value: Decimal) -> str:
    return format(value.normalize(), "f").rstrip("0").rstrip(".") if value else "0"


def main(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("response"), str) or not isinstance(data.get("selected_offer"), dict):
        return fail(["input requires response text and selected_offer object"])
    selected, errors = data["selected_offer"], []
    name = selected.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("selected_offer.name must be a nonempty string")
    rate = numeric(selected.get("cash_back_rate_percent"), "selected_offer.cash_back_rate_percent", errors)
    fee = numeric(selected.get("annual_fee"), "selected_offer.annual_fee", errors)
    score = numeric(selected.get("min_credit_score"), "selected_offer.min_credit_score", errors, True)
    confirmed = selected.get("confirmed_prerequisites", [])
    if not isinstance(confirmed, list) or any(not isinstance(x, str) or not x.strip() for x in confirmed):
        errors.append("confirmed_prerequisites must be an array of nonempty strings")
    app = data.get("application_terms", {})
    if not isinstance(app, dict):
        errors.append("application_terms must be an object")
    if errors:
        return fail(errors)

    text = norm(data["response"])
    rate_pattern = re.escape(number_text(rate)) + r"\s*%"
    fee_pattern = re.escape(format(fee.quantize(Decimal("0.00")), "f"))
    def phrase(key: str) -> bool:
        values = app.get(key, [])
        return values == [] or (isinstance(values, list) and any(isinstance(x, str) and x.strip() and norm(x) in text for x in values))

    checks = {
        "card_name": norm(name) in text,
        "cash_back_rate": bool(re.search(rate_pattern, text)),
        "annual_fee": bool(re.search(r"annual fee.{0,40}(?:\$?" + fee_pattern + r"|zero|no)|(?:\$?" + fee_pattern + r"|zero|no).{0,40}annual fee", text)),
        "minimum_credit_score": score is None or bool(re.search(r"(?:credit score|score).{0,35}" + re.escape(number_text(score)), text)),
        "confirmed_prerequisites": all(norm(item) in text for item in confirmed),
        "application_channel": phrase("channel_phrases"),
        "application_preparation": phrase("preparation_phrases"),
        "application_consent": phrase("consent_phrases"),
        "approval_caveat": "approval" in text and ("credit evaluation" in text or "underwriting" in text),
    }
    missing = [key for key, present in checks.items() if not present]
    return {"ok": not missing, "checks": checks, "missing": missing, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps(fail([f"invalid JSON input: {exc.msg}"]), sort_keys=True))
