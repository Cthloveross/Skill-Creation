#!/usr/bin/env python3
"""Validate that a proposed customer response covers extracted active offers.

Input: respond_from_documents.py input fields plus {"response":"..."}.
Output: {"ok": bool, "errors": [str], "warnings": [str]}.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from respond_from_documents import main as analyze_documents


def norm(value):
    return " ".join(value.lower().split())


def numeric(value):
    return re.sub(r"[^0-9]", "", str(value))


def has_number(response, value):
    expected = numeric(value)
    return bool(expected) and expected in numeric(response)


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
        return {"ok": False, "errors": ["response must be a string"], "warnings": []}
    analysis = analyze_documents(payload)
    if not analysis.get("ok"):
        return analysis

    response = payload["response"]
    text = norm(response)
    errors = []
    active = analysis.get("active_signup_bonuses", [])
    for offer in active:
        facts, card = offer["facts"], offer["card"]
        if card.lower() not in text:
            errors.append("Missing active offer name: " + card)
        if not has_number(response, offer["reward"]["amount"]):
            errors.append("Missing reward amount: " + card)
        if offer["start"] not in response or offer["end"] not in response:
            errors.append("Missing campaign-date context: " + card)
        if facts.get("spend_amount") is not None and not has_number(response, facts["spend_amount"]):
            errors.append("Missing spend threshold: " + card)
        if facts.get("months"):
            month_text = "%d month" % facts["months"]
            if month_text not in text and not (facts["months"] == 1 and "first month" in text):
                errors.append("Missing qualification period: " + card)
        if facts.get("invitation_required") and not any(word in text for word in ("invitation", "invited", "invite-only")):
            errors.append("Missing invitation restriction: " + card)
        if facts.get("new_customer_required") and not any(word in text for word in ("new customer", "new-customer")):
            errors.append("Missing new-customer condition: " + card)
        if facts.get("good_standing") and "good standing" not in text:
            errors.append("Missing good-standing condition: " + card)
        if facts.get("annual_fee") is not None and not has_number(response, facts["annual_fee"]):
            errors.append("Missing annual-fee context: " + card)
        if facts.get("fee_waiver") and "waiv" not in text:
            errors.append("Missing fee-waiver context: " + card)
        if offer["scope"] == "business" and "business" not in text:
            errors.append("Missing business-card context: " + card)
        if offer["reward"]["kind"] == "points" and offer.get("point_redemption_rate") and offer["point_redemption_rate"] not in response:
            errors.append("Missing documented point redemption rate: " + card)

    consumer = [offer for offer in active if offer["scope"] == "consumer"]
    if len(consumer) > 1 and not any(word in text for word in ("best", "largest", "highest", "top", "most valuable", "strongest")):
        errors.append("Missing explicit consumer-offer value comparison")
    if consumer and "recommend" not in text:
        errors.append("Missing practical recommendation")
    return {"ok": not errors, "errors": errors, "warnings": analysis.get("warnings", [])}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
