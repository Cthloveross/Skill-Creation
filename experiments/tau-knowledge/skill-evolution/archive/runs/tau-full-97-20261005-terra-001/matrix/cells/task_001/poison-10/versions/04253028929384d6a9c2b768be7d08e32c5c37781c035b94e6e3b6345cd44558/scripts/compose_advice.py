#!/usr/bin/env python3
"""Compose an informational card-advice draft from supplied documented facts."""
from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def fail(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "response": "", "errors": errors}


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


def text_list(value: Any, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        errors.append(f"{field} must be an array of nonempty strings")
        return []
    return [x.strip() for x in value]


def shown(value: Decimal) -> str:
    return format(value.normalize(), "f").rstrip("0").rstrip(".") if value else "0"


def main(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("offer"), dict) or not isinstance(data.get("application"), dict):
        return fail(["input requires offer and application objects"])
    offer, application, errors = data["offer"], data["application"], []
    name = offer.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("offer.name must be a nonempty string")
    rate = numeric(offer.get("cash_back_rate_percent"), "offer.cash_back_rate_percent", errors)
    fee = numeric(offer.get("annual_fee"), "offer.annual_fee", errors)
    minimum = numeric(offer.get("min_credit_score"), "offer.min_credit_score", errors, True)
    all_purchases = offer.get("all_purchases")
    if not isinstance(all_purchases, bool):
        errors.append("offer.all_purchases must be boolean")
    confirmed = text_list(offer.get("confirmed_prerequisites", []), "offer.confirmed_prerequisites", errors)
    remaining = text_list(offer.get("remaining_requirements", []), "offer.remaining_requirements", errors)
    channel = application.get("channel")
    consent = application.get("consent")
    prepare = text_list(application.get("prepare", []), "application.prepare", errors)
    if not isinstance(channel, str) or not channel.strip():
        errors.append("application.channel must be a nonempty string")
    if not isinstance(consent, str) or not consent.strip():
        errors.append("application.consent must be a nonempty string")
    if errors:
        return fail(errors)

    coverage = " on all purchases" if all_purchases else ""
    paragraphs = [f"I recommend the {name.strip()}. It earns {shown(rate)}% cash back{coverage} and has a ${fee.quantize(Decimal('0.00'))} card annual fee, matching the documented reward and fee preferences."]
    if confirmed:
        paragraphs.append("Your confirmed " + "; ".join(confirmed) + " satisfies that requirement.")
    conditions = []
    if minimum is not None:
        conditions.append(f"The minimum credit score is {shown(minimum)}")
    conditions.extend(remaining)
    if conditions:
        paragraphs.append("Remaining eligibility conditions: " + "; ".join(conditions) + ".")
    paragraphs.append("Approval remains subject to credit evaluation and underwriting.")
    paragraphs.append("Next steps: apply through " + channel.strip() + ". Prepare " + ", ".join(prepare) + ", and " + consent.strip() + ".")
    return {"ok": True, "response": " ".join(paragraphs), "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps(fail([f"invalid JSON input: {exc.msg}"]), sort_keys=True))
