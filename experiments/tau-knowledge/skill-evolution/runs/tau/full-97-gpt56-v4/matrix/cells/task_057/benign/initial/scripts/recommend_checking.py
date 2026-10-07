#!/usr/bin/env python3
"""Produce a policy-grounded checking recommendation from a narrow preference input.

Reads one JSON object from stdin and writes one JSON object to stdout.
"""

import json
import sys
from typing import Any, Dict


def recommend(payload: Dict[str, Any]) -> Dict[str, Any]:
    strict = payload.get("requires_no_overdraft_related_charges")
    if not isinstance(strict, bool):
        return {
            "status": "error",
            "error": "requires_no_overdraft_related_charges must be a boolean",
        }

    age = payload.get("age")
    if age is not None and (not isinstance(age, int) or isinstance(age, bool) or age < 0):
        return {"status": "error", "error": "age must be a nonnegative integer when supplied"}

    if not strict:
        return {
            "status": "unsupported",
            "error": "This helper only ranks accounts for an absolute no-overdraft-related-charges preference.",
        }

    alternatives = [
        {
            "account_class": "Blue Account",
            "not_equivalent_reason": (
                "Its account overdraft fee is $0.00, but optional overdraft-protection "
                "transfers cost $12.50 each if enabled."
            ),
        }
    ]
    if age is None or not 13 <= age <= 24:
        alternatives.append(
            {
                "account_class": "Light Green Account",
                "not_equivalent_reason": "It is restricted to primary account holders age 13 through 24.",
            }
        )

    return {
        "status": "ok",
        "recommended_account_class": "Green Account (checking)",
        "rationale": [
            "No overdraft fees apply.",
            "There is no overdraft coverage or linked-account overdraft transfer service.",
            "A transaction above available funds is declined rather than creating an overdraft.",
        ],
        "material_tradeoffs": [
            "The monthly maintenance fee is $22.50.",
            "The fee is waived with a $1,350 minimum daily balance.",
            "Paper statements cost $2.50 per month.",
        ],
        "alternatives_not_equivalent": alternatives,
        "customer_message": (
            "Based on your non-negotiable preference, Green Account (checking) is the best fit: "
            "it has no overdraft fees, no overdraft coverage or linked-account transfers, and "
            "a purchase that exceeds your available balance is declined. Please note its $22.50 "
            "monthly fee is waived with a $1,350 minimum daily balance. Would you like to select "
            "Green Account (checking) and continue with the eligibility steps?"
        ),
    }


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        output = recommend(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        output = {"status": "error", "error": str(exc)}
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
