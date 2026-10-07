#!/usr/bin/env python3
"""Validate that a proposed response covers source-supported active sign-up bonuses.
stdin is document JSON plus a string field `response`; stdout is JSON validation.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze
from extract_promotions import main as extract


def normal(text):
    return " ".join(text.lower().split())


def digits(text):
    return re.sub(r"[^0-9]", "", text)


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
        return {"ok": False, "errors": ["response must be a string"], "warnings": []}
    extracted = extract(payload)
    if not extracted.get("ok"):
        return extracted
    analysis = analyze({"as_of": extracted.get("as_of"), "offers": extracted.get("offers", [])})
    text, number_text = normal(payload["response"]), digits(payload["response"])
    errors = []
    for offer in analysis.get("active_signup_bonuses", []):
        name = offer.get("card", "")
        if name and name.lower() not in text:
            errors.append("Missing active card name: " + name)
        reward = offer.get("reward") or {}
        if str(reward.get("amount", "")) not in number_text:
            errors.append("Missing reward amount: " + name)
        q = offer.get("qualification") or {}
        if q.get("invitation_required") and not any(x in text for x in ("invitation", "invited", "invite-only")):
            errors.append("Missing invitation restriction: " + name)
        spend = q.get("spend_requirement", "")
        amount = re.search(r"\$([\d,]+)", spend)
        if amount and digits(amount.group(1)) not in number_text:
            errors.append("Missing spend requirement: " + name)
        period = q.get("spend_window")
        if period and period.lower() not in text:
            errors.append("Missing qualification period: " + name)
        if offer.get("product_scope") == "business" and "business" not in text:
            errors.append("Missing business context: " + name)
    active = analysis.get("active_signup_bonuses", [])
    if len(active) > 1 and not any(x in text for x in ("largest", "highest", "best", "top", "most valuable", "strongest")):
        errors.append("Missing value comparison")
    return {"ok": not errors, "errors": errors,
            "warnings": extracted.get("warnings", []) + analysis.get("warnings", [])}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
