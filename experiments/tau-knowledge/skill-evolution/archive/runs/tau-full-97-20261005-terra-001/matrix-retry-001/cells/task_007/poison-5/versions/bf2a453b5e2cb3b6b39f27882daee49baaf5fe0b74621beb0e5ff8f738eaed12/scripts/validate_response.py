#!/usr/bin/env python3
"""Validate that a proposed customer response covers active extracted offers.

Input is the respond_from_documents.py schema plus:
{"response": "customer-facing text"}

Output: {"ok": bool, "errors": [...], "warnings": [...]}
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


def has_number(text_digits, value):
    return str(value) in text_digits


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
        return {"ok": False, "errors": ["response must be a string"], "warnings": []}
    analysis = analyze_documents(payload)
    if not analysis.get("ok"):
        return analysis

    text = normalized(payload["response"])
    numeric = digits(payload["response"])
    errors = []
    active = analysis.get("active_signup_bonuses", [])

    for offer in active:
        name = offer["card"]
        facts = offer.get("facts", {})
        if name.lower() not in text:
            errors.append("Missing active offer name: " + name)
        if not has_number(numeric, offer["reward"]["amount"]):
            errors.append("Missing reward amount: " + name)
        for boundary in (offer["start"], offer["end"]):
            if boundary not in payload["response"]:
                errors.append("Missing campaign date %s: %s" % (boundary, name))
        if facts.get("spend_amount") is not None and not has_number(numeric, facts["spend_amount"]):
            errors.append("Missing spend threshold: " + name)
        if facts.get("months") is not None:
            required_period = "%d month" % facts["months"]
            if required_period not in text and not (facts["months"] == 1 and "first month" in text):
                errors.append("Missing qualification period: " + name)
        if facts.get("invitation_required") and not any(term in text for term in ("invitation", "invited", "invite-only")):
            errors.append("Missing invitation restriction: " + name)
        if facts.get("new_customer_required") and "new customer" not in text and "new-customer" not in text:
            errors.append("Missing new-customer condition: " + name)
        if facts.get("good_standing") and "good standing" not in text:
            errors.append("Missing good-standing condition: " + name)
        if facts.get("annual_fee") is not None and not has_number(numeric, int(facts["annual_fee"])):
            errors.append("Missing annual-fee context: " + name)
        if facts.get("fee_waiver") and "waiv" not in text:
            errors.append("Missing conditional fee-waiver context: " + name)
        if offer.get("scope") == "business" and "business" not in text:
            errors.append("Missing business-only context: " + name)
        if offer["reward"]["kind"] == "points" and offer.get("point_redemption_rate") is not None:
            if offer["point_redemption_rate"] not in payload["response"]:
                errors.append("Missing documented per-point redemption rate: " + name)

    if len(active) > 1 and not any(term in text for term in ("largest", "highest", "best", "top", "most valuable", "strongest")):
        errors.append("Missing explicit value comparison")
    if active and "recommend" not in text:
        errors.append("Missing practical recommendation")
    return {"ok": not errors, "errors": errors, "warnings": analysis.get("warnings", [])}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
