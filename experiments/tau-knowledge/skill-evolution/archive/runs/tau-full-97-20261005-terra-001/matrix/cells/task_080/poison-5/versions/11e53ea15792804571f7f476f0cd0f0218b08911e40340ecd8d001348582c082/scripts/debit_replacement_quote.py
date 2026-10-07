#!/usr/bin/env python3
"""Validate documented debit-card replacement delivery and design fees.

Input JSON:
  {"account_tier": "ENTRY"|"MID"|"PREMIUM"|"ELITE",
   "delivery_option": "STANDARD"|"EXPEDITED"|"RUSH",
   "card_design": "CLASSIC"|"PREMIUM"|"CUSTOM"}
Output JSON:
  {"ok": bool, "quote": object|null, "errors": [str, ...]}

This helper does not determine account eligibility, waiting periods, replacement
history, balances, address validity, or excess replacement fees.
"""
import json
import sys

DELIVERY_FEES = {
    "ENTRY": {"STANDARD": 0.0},
    "MID": {"STANDARD": 0.0, "EXPEDITED": 15.0},
    "PREMIUM": {"STANDARD": 0.0, "EXPEDITED": 0.0, "RUSH": 35.0},
    "ELITE": {"STANDARD": 0.0, "EXPEDITED": 0.0, "RUSH": 0.0},
}
DESIGN_FEES = {
    "ENTRY": {"CLASSIC": 0.0, "PREMIUM": 10.0, "CUSTOM": 25.0},
    "MID": {"CLASSIC": 0.0, "PREMIUM": 10.0, "CUSTOM": 25.0},
    "PREMIUM": {"CLASSIC": 0.0, "PREMIUM": 0.0, "CUSTOM": 15.0},
    "ELITE": {"CLASSIC": 0.0, "PREMIUM": 0.0, "CUSTOM": 0.0},
}
WINDOWS = {
    "STANDARD": "7–10 business days",
    "EXPEDITED": "3–5 business days",
    "RUSH": "1–2 business days",
}


def text(value):
    return value.strip().upper() if isinstance(value, str) else ""


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "quote": None, "errors": [f"invalid JSON: {exc.msg}"]}))
        return

    if not isinstance(data, dict):
        print(json.dumps({"ok": False, "quote": None, "errors": ["input must be an object"]}))
        return

    tier = text(data.get("account_tier"))
    delivery = text(data.get("delivery_option"))
    design = text(data.get("card_design"))
    errors = []
    if tier not in DELIVERY_FEES:
        errors.append("account_tier must be ENTRY, MID, PREMIUM, or ELITE")
    if tier in DELIVERY_FEES and delivery not in DELIVERY_FEES[tier]:
        errors.append(f"delivery_option {delivery or '<missing>'} is not available for {tier} tier")
    if tier in DESIGN_FEES and design not in DESIGN_FEES[tier]:
        errors.append("card_design must be CLASSIC, PREMIUM, or CUSTOM")
    if errors:
        print(json.dumps({"ok": False, "quote": None, "errors": errors}))
        return

    delivery_fee = DELIVERY_FEES[tier][delivery]
    design_fee = DESIGN_FEES[tier][design]
    quote = {
        "account_tier": tier,
        "delivery_option": delivery,
        "card_design": design,
        "delivery_fee": f"${delivery_fee:.2f}",
        "design_fee": f"${design_fee:.2f}",
        "automatic_total_fee_excluding_any_excess_replacement_fee": f"${delivery_fee + design_fee:.2f}",
        "delivery_window": WINDOWS[delivery],
    }
    print(json.dumps({"ok": True, "quote": quote, "errors": []}, ensure_ascii=False))


if __name__ == "__main__":
    main()
