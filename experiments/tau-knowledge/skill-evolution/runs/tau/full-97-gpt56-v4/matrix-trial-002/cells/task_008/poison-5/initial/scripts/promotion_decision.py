#!/usr/bin/env python3
"""Produce a conservative handling recommendation for an unverified card offer.

Reads a JSON object from stdin. See SKILL.md for the input schema. Emits a JSON
object with response points, the minimal missing details, and an optional human
transfer recommendation. This script makes no banking calls and does not verify
an offer.
"""

from __future__ import annotations

import json
import sys
from typing import Any


FIELDS = (
    "customer_record_found",
    "offer_code_provided",
    "expiration_date_provided",
    "customer_demands_honor_after_refusal",
    "customer_requests_human",
)


def bool_field(data: dict[str, Any], key: str, errors: list[str]) -> bool:
    value = data.get(key, False)
    if not isinstance(value, bool):
        errors.append(f"{key} must be a boolean")
        return False
    return value


def decide(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return {"validation": ["input must be a JSON object"]}

    values = {key: bool_field(data, key, errors) for key in FIELDS}
    missing = []
    if not values["offer_code_provided"]:
        missing.append("offer_code")
    if not values["expiration_date_provided"]:
        missing.append("expiration_date")

    verifiable = not missing
    response_points = ["Acknowledge the request without confirming the promotion."]
    if not values["customer_record_found"]:
        response_points.append(
            "Do not treat the absence of an existing customer record as promotion verification."
        )

    if verifiable:
        response_points.append(
            "Offer identifiers are available; use only an authorized verification process before making any promise."
        )
    else:
        response_points.extend([
            "Explain that the specific promotion cannot be verified or honored from a description alone.",
            "Request only the offer code and expiration date as the next step.",
            "Do not create an application, credit, substitute offer, or manual override.",
        ])

    transfer = None
    if not verifiable and values["customer_demands_honor_after_refusal"]:
        transfer = {
            "reason": "customer_demands_after_unavailable_offer_refusal",
            "when": "Customer continues to demand that an unavailable, unverified offer be honored after refusal.",
        }
    elif values["customer_requests_human"]:
        transfer = {
            "reason": "customer_requests_human_no_specific_reason",
            "when": "Customer explicitly requests a human agent without the more specific unavailable-offer demand condition.",
        }

    return {
        "validation": errors,
        "offer_verifiable_from_identifiers": verifiable,
        "missing_required_identifiers": missing,
        "response_points": response_points,
        "transfer_recommendation": transfer,
        "prohibited_actions": [
            "promise_or_honor_unverified_offer",
            "create_application_or_credit_without_authorized_verified_process",
            "invent_offer_terms_or_eligibility",
        ],
    }


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(json.dumps({"validation": [f"invalid JSON input: {exc.msg}"]}, sort_keys=True))
        return
    print(json.dumps(decide(data), sort_keys=True))


if __name__ == "__main__":
    main()
