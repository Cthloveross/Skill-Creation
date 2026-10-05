#!/usr/bin/env python3
"""Validate coverage of active sign-up offers in a customer-facing response.

Input is the respond_from_documents.py input schema plus:
{"response": "customer-facing text"}

Output: {"ok": bool, "errors": [str], "warnings": [str]}
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from respond_from_documents import main as analyze_documents


def normalized(value):
    return " ".join(value.lower().split())


def digits(value):
    return re.sub(r"[^0-9]", "", value)


def contains_number(text_digits, value):
    plain = re.sub(r"[^0-9]", "", str(value))
    return bool(plain) and plain in text_digits


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
        return {"ok": False, "errors": ["response must be a string"], "warnings": []}
    analysis = analyze_documents(payload)
    if not analysis.get("ok"):
        return analysis

    response = payload["response"]
    text, numeric = normalized(response), digits(response)
    errors = []
    active = analysis.get("active_signup_bonuses", [])
    for offer in active:
        facts, card = offer.get("facts", {}), offer["card"]
        if card.lower() not in text:
            errors.append("Missing active offer name: " + card)
        if not contains_number(numeric, offer["reward"]["amount"]):
            errors.append("Missing reward amount: " + card)
        for boundary in (offer["start"], offer["end"]):
            if boundary not in response:
                errors.append("Missing campaign date %s: %s" % (boundary, card))
        if facts.get("spend_amount") is not None and not contains_number(numeric, facts["spend_amount"]):
            errors.append("Missing spend threshold: " + card)
        if facts.get("months") is not None:
            expected = "%d month" % facts["months"]
            if expected not in text and not (facts["months"] == 1 and "first month" in text):
                errors.append("Missing qualification period: " + card)
        if facts.get("invitation_required") and not any(term in text for term in ("invitation", "invited", "invite-only", "invitation-only")):
            errors.append("Missing invitation restriction: " + card)
        if facts.get("new_customer_required") and "new customer" not in text and "new-customer" not in text:
            errors.append("Missing new-customer condition: " + card)
        if facts.get("good_standing") and "good standing" not in text:
            errors.append("Missing good-standing condition: " + card)
        if facts.get("annual_fee") is not None and not contains_number(numeric, facts["annual_fee"]):
            errors.append("Missing annual-fee context: " + card)
        if facts.get("fee_waiver") and "waiv" not in text:
            errors.append("Missing conditional fee-waiver context: " + card)
        if offer.get("scope") == "business" and "business" not in text:
            errors.append("Missing business-only context: " + card)
        if offer["reward"]["kind"] == "points" and offer.get("point_redemption_rate") is not None and offer["point_redemption_rate"] not in response:
            errors.append("Missing documented per-point redemption rate: " + card)

    consumer = [offer for offer in active if offer.get("scope") == "consumer"]
    if len(consumer) > 1 and not any(term in text for term in ("largest", "highest", "best", "top", "most valuable", "strongest")):
        errors.append("Missing explicit consumer-offer value comparison")
    if consumer and "recommend" not in text:
        errors.append("Missing practical recommendation")
    return {"ok": not errors, "errors": errors, "warnings": analysis.get("warnings", [])}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
