#!/usr/bin/env python3
"""Compose a complete informational card recommendation from extracted facts."""
from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def failure(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "response": "", "errors": errors}


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


def strings(value: Any, field: str, errors: list[str], allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        errors.append(f"{field} must be an array of nonempty strings")
        return []
    if not allow_empty and not value:
        errors.append(f"{field} must not be empty")
    return [x.strip() for x in value]


def displayed_number(value: Decimal) -> str:
    result = format(value.normalize(), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def main(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("offer"), dict) or not isinstance(data.get("application"), dict):
        return failure(["input requires offer and application objects"])
    offer = data["offer"]
    application = data["application"]
    errors: list[str] = []

    name = offer.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("offer.name must be a nonempty string")
    rate = decimal_value(offer.get("cash_back_rate_percent"), "offer.cash_back_rate_percent", errors)
    fee = decimal_value(offer.get("annual_fee"), "offer.annual_fee", errors)
    score = decimal_value(offer.get("min_credit_score"), "offer.min_credit_score", errors, True)
    all_purchases = offer.get("all_purchases")
    if not isinstance(all_purchases, bool):
        errors.append("offer.all_purchases must be boolean")
    confirmed = strings(offer.get("confirmed_prerequisites", []), "offer.confirmed_prerequisites", errors)
    remaining = strings(offer.get("remaining_requirements", []), "offer.remaining_requirements", errors)

    channel = application.get("channel")
    consent = application.get("consent")
    preparation = strings(application.get("prepare", []), "application.prepare", errors, allow_empty=False)
    if not isinstance(channel, str) or not channel.strip():
        errors.append("application.channel must be a nonempty string")
    if not isinstance(consent, str) or not consent.strip():
        errors.append("application.consent must be a nonempty string")
    if errors:
        return failure(errors)

    coverage = " on all purchases" if all_purchases else ""
    response = [
        f"I recommend {name.strip()}. It earns {displayed_number(rate)}% cash back{coverage} and has a ${fee.quantize(Decimal('0.00'))} card annual fee, matching your documented reward and fee preferences."
    ]
    if confirmed:
        response.append("Your confirmed " + "; ".join(confirmed) + " satisfies that requirement.")
    conditions: list[str] = []
    if score is not None:
        conditions.append(f"the minimum credit score is {displayed_number(score)}")
    conditions.extend(remaining)
    if conditions:
        response.append("Remaining eligibility conditions: " + "; ".join(conditions) + ".")
    response.append("Approval remains subject to credit evaluation and underwriting.")
    response.append(
        "Next steps: apply through " + channel.strip() + ". Prepare " + ", ".join(preparation) + ", and " + consent.strip() + "."
    )
    return {"ok": True, "response": " ".join(response), "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps(failure([f"invalid JSON input: {exc.msg}"]), sort_keys=True))
