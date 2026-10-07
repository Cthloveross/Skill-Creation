#!/usr/bin/env python3
"""Validate normalized public credit-card replacement fields.

Input JSON:
{
  "credit_card_account_id": string,
  "user_id": string,
  "reason": "fraud_suspected" | "lost" | "stolen" | "damaged" | "expired" | "other",
  "shipping_address": string,
  "expedited_shipping": boolean,
  "expedited_fee": number (optional, default 0),
  "fee_consent_captured": boolean (optional, default false)
}

Output JSON has ok, normalized_request, errors, and fee_consent_required. The executor,
not this script, must establish address confirmation and fee consent in conversation.
"""
import json
import math
import sys

REASONS = {"fraud_suspected", "lost", "stolen", "damaged", "expired", "other"}


def text(value):
    return str(value or "").strip()


def main(payload):
    errors = []
    account_id = text(payload.get("credit_card_account_id"))
    user_id = text(payload.get("user_id"))
    reason = text(payload.get("reason")).lower()
    address = text(payload.get("shipping_address"))
    expedited = payload.get("expedited_shipping")
    consent = payload.get("fee_consent_captured", False)
    try:
        fee = float(payload.get("expedited_fee", 0))
        if not math.isfinite(fee) or fee < 0:
            raise ValueError
    except (TypeError, ValueError):
        fee = 0.0
        errors.append("expedited_fee must be a non-negative finite number")

    if not account_id:
        errors.append("credit_card_account_id is required")
    if not user_id:
        errors.append("user_id is required")
    if reason not in REASONS:
        errors.append("reason must be one of: " + ", ".join(sorted(REASONS)))
    if not address:
        errors.append("shipping_address is required and must be customer-confirmed")
    if not isinstance(expedited, bool):
        errors.append("expedited_shipping must be boolean")
    if not isinstance(consent, bool):
        errors.append("fee_consent_captured must be boolean")

    fee_required = expedited is True and fee > 0
    if fee_required and consent is not True:
        errors.append("explicit fee_consent_captured is required for paid expedited shipping")

    return {"ok": not errors,
            "normalized_request": {"credit_card_account_id": account_id, "user_id": user_id,
                                   "reason": reason, "shipping_address": address,
                                   "expedited_shipping": expedited if isinstance(expedited, bool) else False},
            "errors": errors, "fee_consent_required": fee_required}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
        output = main(data)
    except Exception as exc:
        output = {"ok": False, "normalized_request": {},
                  "errors": ["invalid_input: " + str(exc)], "fee_consent_required": False}
    print(json.dumps(output, separators=(",", ":"), sort_keys=True))
