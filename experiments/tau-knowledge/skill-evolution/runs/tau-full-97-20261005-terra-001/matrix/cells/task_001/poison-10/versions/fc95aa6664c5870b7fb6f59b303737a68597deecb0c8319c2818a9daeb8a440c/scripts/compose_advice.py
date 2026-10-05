#!/usr/bin/env python3
"""Compose a factual advice draft from selected current-document terms on stdin."""
from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def fail(messages: list[str]) -> dict[str, Any]:
    return {"ok": False, "response": "", "errors": messages}


def amount(value: Any, label: str, errors: list[str], nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        errors.append(f"{label} must be numeric")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not number.is_finite() or number < 0:
        errors.append(f"{label} must be a finite nonnegative number")
        return None
    return number


def display(value: Decimal) -> str:
    return format(value.normalize(), "f").rstrip("0").rstrip(".") if value != 0 else "0"


def text_list(value: Any, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{label} must be an array of nonempty strings")
        return []
    return [item.strip() for item in value]


def main(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("offer"), dict) or not isinstance(data.get("application"), dict):
        return fail(["input requires offer and application objects"])
    offer, application, errors = data["offer"], data["application"], []
    name = offer.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("offer.name must be a nonempty string")
    rate = amount(offer.get("cash_back_rate_percent"), "offer.cash_back_rate_percent", errors)
    fee = amount(offer.get("annual_fee"), "offer.annual_fee", errors)
    score = amount(offer.get("min_credit_score"), "offer.min_credit_score", errors, True)
    all_purchases = offer.get("all_purchases", False)
    credit_review = offer.get("approval_subject_to_credit_evaluation", True)
    if not isinstance(all_purchases, bool) or not isinstance(credit_review, bool):
        errors.append("offer boolean fields must be boolean")
    confirmed = text_list(offer.get("confirmed_prerequisites", []), "offer.confirmed_prerequisites", errors)
    remaining = text_list(offer.get("remaining_requirements", []), "offer.remaining_requirements", errors)
    channel = application.get("channel")
    consent = application.get("consent")
    if not isinstance(channel, str) or not channel.strip():
        errors.append("application.channel must be a nonempty string")
    if not isinstance(consent, str) or not consent.strip():
        errors.append("application.consent must be a nonempty string")
    prepare = text_list(application.get("prepare", []), "application.prepare", errors)
    if errors:
        return fail(errors)

    coverage = " on all purchases" if all_purchases else ""
    response = [
        f"I recommend the {name.strip()}. It earns {display(rate)}% cash back{coverage} and has a ${fee.quantize(Decimal('0.00'))} card annual fee, which fits a simple cash-back preference with no card annual fee.",
    ]
    if confirmed:
        response.append("Eligibility: your confirmed " + "; ".join(confirmed) + " satisfies that requirement.")
    eligibility = []
    if score is not None:
        eligibility.append(f"The minimum credit score is {display(score)}")
    eligibility.extend(remaining)
    if eligibility:
        response.append("Remaining eligibility conditions: " + "; ".join(eligibility) + ".")
    if credit_review:
        response.append("Approval remains subject to credit evaluation and underwriting.")
    response.append("Next steps: apply through " + channel.strip() + ". Prepare " + ", ".join(prepare) + ", and " + consent.strip() + ".")
    return {"ok": True, "response": " ".join(response), "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps(fail([f"invalid JSON input: {exc.msg}"]), sort_keys=True))
