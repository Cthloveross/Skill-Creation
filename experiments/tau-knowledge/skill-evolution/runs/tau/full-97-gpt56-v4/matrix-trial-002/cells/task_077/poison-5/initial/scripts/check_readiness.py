#!/usr/bin/env python3
"""Validate minimum, caller-supplied prerequisites for card-protection actions.

Input JSON:
  operation: "freeze" or "credit_replacement"
  identity_verified: boolean
  owner_verified: boolean
  customer_confirmed: boolean
  card_status: string (required for freeze; must be ACTIVE)
  eligible: boolean (required for credit_replacement)
  reason: supported replacement reason (required for credit_replacement)
  shipping_address_confirmed: boolean (required for credit_replacement)
  shipping_speed: "standard" or "expedited" (required for credit_replacement)
  expedited_fee_acknowledged: boolean (required only for an expedited paid tier)
  expedited_fee_applies: boolean (defaults false)

Output JSON:
  {"ready": boolean, "missing": [string, ...]}
"""
import json
import sys

REASONS = {"fraud_suspected", "lost", "stolen", "damaged", "expired", "other"}


def require(data, key, missing, label=None):
    if data.get(key) is not True:
        missing.append(label or key)


def check(data):
    operation = data.get("operation")
    missing = []
    if operation not in {"freeze", "credit_replacement"}:
        return {"ready": False, "missing": ["operation (freeze or credit_replacement)"]}

    require(data, "identity_verified", missing)
    require(data, "owner_verified", missing)
    require(data, "customer_confirmed", missing)

    if operation == "freeze":
        if data.get("card_status") != "ACTIVE":
            missing.append("card_status=ACTIVE")
    else:
        require(data, "eligible", missing, "replacement eligibility")
        if data.get("reason") not in REASONS:
            missing.append("supported replacement reason")
        require(data, "shipping_address_confirmed", missing, "confirmed shipping address")
        if data.get("shipping_speed") not in {"standard", "expedited"}:
            missing.append("shipping speed (standard or expedited)")
        if data.get("shipping_speed") == "expedited" and data.get("expedited_fee_applies", False):
            require(data, "expedited_fee_acknowledged", missing, "expedited fee acknowledgement")

    return {"ready": not missing, "missing": missing}


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(check(data), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ready": False, "missing": ["valid JSON object"], "error": str(exc)}))


if __name__ == "__main__":
    main()
