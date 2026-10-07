#!/usr/bin/env python3
"""Check a promotion-comparison draft for active-offer coverage."""
import json
import os
import re
import sys
sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze

def norm(value): return " ".join(str(value).lower().replace("$", " $").split())
def forms(value):
    try:
        number = float(value)
        return [str(int(number)), format(int(number), ",")] if number.is_integer() else [str(number)]
    except (ValueError, TypeError): return []
def present(text, values): return any(v.lower() in text for v in values if v)

def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
        return {"ok": False, "errors": ["response must be a string."], "warnings": []}
    result = analyze({"as_of": payload.get("as_of"), "offers": payload.get("offers")})
    if not result.get("ok"): return result
    text, errors, warnings = norm(payload["response"]), [], list(result["warnings"])
    refusals = ("don't have current promotion records", "do not have current promotion records", "cannot confirm which offers are active", "promotion records are unavailable")
    if result["ranked_active_signup_bonuses"] and present(text, refusals): errors.append("Draft incorrectly denies available current-promotion evidence.")
    for offer in result["ranked_active_signup_bonuses"]:
        card = norm(offer["card"])
        if card not in text: errors.append("Missing active card name: " + offer["card"])
        reward = offer.get("reward", {})
        if not present(text, forms(reward.get("amount"))): errors.append("Missing reward amount for " + offer["card"])
        q = offer.get("qualification") if isinstance(offer.get("qualification"), dict) else {}
        if q.get("invitation_required") and not present(text, ("invitation", "invited", "invite-only", "invitation-only")): errors.append("Missing invitation restriction for " + offer["card"])
        if q.get("new_customer_required") and "new customer" not in text: errors.append("Missing new-customer restriction for " + offer["card"])
        if str(offer.get("product_scope", "")).lower() == "business" and "business" not in text: errors.append("Missing business-card context for " + offer["card"])
    if len(result["ranked_active_signup_bonuses"]) > 1 and not present(text, ("largest", "highest", "best", "top", "most valuable", "strongest")): errors.append("Draft does not compare bonus value.")
    return {"ok": not errors, "errors": errors, "warnings": warnings}

if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc: print(json.dumps({"ok": False, "errors": ["Invalid JSON input: " + exc.msg], "warnings": []}))
