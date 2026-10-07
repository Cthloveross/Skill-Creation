#!/usr/bin/env python3
"""Validate a normalized credit-card replacement request before tool submission.

Input JSON:
{
  "account_id": string,
  "reason": "fraud_suspected" | "lost" | "stolen" | "damaged" | "expired" | "other",
  "shipping_address": string,
  "shipping_speed": "standard" | "expedited",
  "expedited_fee": number (optional, defaults to 0),
  "expedited_fee_acknowledgement": boolean (optional),
  "notes": string (optional)
}

Output JSON:
{
  "ok": boolean,
  "normalized_request": object,
  "errors": [string],
  "fee_acknowledgement_required": boolean
}

The script is read-only. It cannot establish that an address or consent was actually
confirmed by a customer; the executor must establish those facts in the conversation.
"""

import json
import math
import sys
from typing import Any, Dict, List

ALLOWED_REASONS = {
    "fraud_suspected", "lost", "stolen", "damaged", "expired", "other"
}
ALLOWED_SPEEDS = {"standard", "expedited"}


def text(value: Any) -> str:
    return str(value or "").strip()


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    account_id = text(payload.get("account_id"))
    reason = text(payload.get("reason")).lower()
    address = text(payload.get("shipping_address"))
    speed = text(payload.get("shipping_speed")).lower()
    notes = text(payload.get("notes"))
    acknowledgement = payload.get("expedited_fee_acknowledgement", False)

    raw_fee = payload.get("expedited_fee", 0)
    try:
        fee = float(raw_fee)
        if not math.isfinite(fee) or fee < 0:
            raise ValueError
    except (TypeError, ValueError):
        fee = 0.0
        errors.append("expedited_fee must be a non-negative finite number")

    if not account_id:
        errors.append("account_id is required")
    if reason not in ALLOWED_REASONS:
        errors.append("reason must be one of: " + ", ".join(sorted(ALLOWED_REASONS)))
    if not address:
        errors.append("shipping_address is required and must be customer-confirmed")
    if speed not in ALLOWED_SPEEDS:
        errors.append("shipping_speed must be 'standard' or 'expedited'")
    if not isinstance(acknowledgement, bool):
        errors.append("expedited_fee_acknowledgement must be boolean")

    fee_consent_required = speed == "expedited" and fee > 0
    if fee_consent_required and acknowledgement is not True:
        errors.append("explicit expedited_fee_acknowledgement is required when expedited_fee is positive")

    normalized = {
        "account_id": account_id,
        "reason": reason,
        "shipping_address": address,
        "shipping_speed": speed,
        "expedited_fee_acknowledgement": acknowledgement if isinstance(acknowledgement, bool) else False,
        "notes": notes,
    }
    return {
        "ok": not errors,
        "normalized_request": normalized,
        "errors": errors,
        "fee_acknowledgement_required": fee_consent_required,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON must be an object")
        result = main(raw)
    except Exception as exc:
        result = {
            "ok": False,
            "normalized_request": {},
            "errors": ["invalid_input: " + str(exc)],
            "fee_acknowledgement_required": False,
        }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
