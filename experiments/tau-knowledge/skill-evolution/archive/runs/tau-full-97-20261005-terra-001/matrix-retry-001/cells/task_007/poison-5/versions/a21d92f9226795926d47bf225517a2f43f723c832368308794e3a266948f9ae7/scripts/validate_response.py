#!/usr/bin/env python3
"""Check a proposed response for coverage of source-supported active bonuses.
Input: document JSON plus a string field named response. Output: {ok, errors, warnings}.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze
from extract_promotions import main as extract


def normalized(value):
    return " ".join(value.lower().replace("$", " $").split())


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
        return {"ok": False, "errors": ["response must be a string"], "warnings": []}
    extracted = extract(payload)
    if not extracted.get("ok"):
        return extracted
    analysis = analyze({"as_of": extracted.get("as_of"), "offers": extracted.get("offers", [])})
    text = normalized(payload["response"])
    errors = []
    for offer in analysis.get("active_signup_bonuses", []):
        card = offer["card"]
        if card.lower() not in text:
            errors.append("Missing active card name: " + card)
        amount = str(offer.get("reward", {}).get("amount", ""))
        comma_amount = format(int(amount), ",") if amount.isdigit() else amount
        if amount and amount not in text and comma_amount not in text:
            errors.append("Missing reward amount: " + card)
        qualification = offer.get("qualification") or {}
        if qualification.get("invitation_required") and not any(term in text for term in ("invitation", "invited", "invite-only")):
            errors.append("Missing invitation restriction: " + card)
        spend = qualification.get("spend_requirement")
        if spend:
            digits = spend.split()[0].replace("$", "").replace(",", "")
            if digits not in text.replace(",", ""):
                errors.append("Missing spend requirement: " + card)
        if qualification.get("spend_window") and qualification["spend_window"] not in text:
            errors.append("Missing qualification period: " + card)
        if offer.get("product_scope") == "business" and "business" not in text:
            errors.append("Missing business context: " + card)
    active = analysis.get("active_signup_bonuses", [])
    if len(active) > 1 and not any(term in text for term in ("largest", "highest", "best", "top", "most valuable", "strongest")):
        errors.append("Missing value comparison")
    return {"ok": not errors, "errors": errors,
            "warnings": extracted.get("warnings", []) + analysis.get("warnings", [])}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
