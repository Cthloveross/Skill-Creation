#!/usr/bin/env python3
"""Check a proposed promotion comparison for active-offer coverage."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze


def norm(value):
    return " ".join(str(value).lower().replace("$", " $").split())


def numeric_forms(value):
    try:
        integer = int(float(value))
        return (str(integer), format(integer, ","))
    except (TypeError, ValueError):
        return ()


def contains_any(text, values):
    return any(str(value).lower() in text for value in values if value is not None)


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
        return {"ok": False, "errors": ["response must be a string."], "warnings": []}
    result = analyze({"as_of": payload.get("as_of"), "offers": payload.get("offers")})
    if not result.get("ok"):
        return result

    text = norm(payload["response"])
    errors, warnings = [], list(result["warnings"])
    active = result["ranked_active_signup_bonuses"]
    denials = (
        "don't have current promotion records", "do not have current promotion records",
        "promotion records are unavailable", "cannot confirm which offers are active",
        "no dated promotion records", "don't have any current promotion",
    )
    if active and contains_any(text, denials):
        errors.append("Draft incorrectly denies supplied current-promotion evidence.")

    for offer in active:
        card = norm(offer["card"])
        if card not in text:
            errors.append("Missing active card name: " + offer["card"])
        reward = offer.get("reward") if isinstance(offer.get("reward"), dict) else {}
        if not contains_any(text, numeric_forms(reward.get("amount"))):
            errors.append("Missing reward amount for " + offer["card"])
        for field in ("window_start", "window_end"):
            if offer.get(field) and str(offer[field]) not in text:
                errors.append("Missing {} for {}.".format(field, offer["card"]))
        q = offer.get("qualification") if isinstance(offer.get("qualification"), dict) else {}
        if q.get("invitation_required") and not contains_any(text, ("invitation", "invited", "invite-only", "invitation-only")):
            errors.append("Missing invitation restriction for " + offer["card"])
        if q.get("new_customer_required") and not contains_any(text, ("new customer", "new-customer")):
            errors.append("Missing new-customer restriction for " + offer["card"])
        if q.get("spend_requirement"):
            nums = re.findall(r"[\d,]+", str(q["spend_requirement"]))
            if nums and not contains_any(text, tuple(nums) + tuple(n.replace(",", "") for n in nums)):
                errors.append("Missing spend requirement for " + offer["card"])
        if q.get("spend_window") and not contains_any(text, ("one month", "1 month", "first month", "two months", "2 months", "first two months")):
            errors.append("Missing qualification period for " + offer["card"])
        if str(offer.get("product_scope", "")).lower() == "business" and "business" not in text:
            errors.append("Missing business-card context for " + offer["card"])
        fee = offer.get("annual_fee") if isinstance(offer.get("annual_fee"), dict) else {}
        if fee.get("standard") and str(fee["standard"]).replace("$", " $").lower() not in text:
            warnings.append("Response may omit standard annual fee for " + offer["card"])

    if len(active) > 1 and not contains_any(text, ("largest", "highest", "best", "top", "most valuable", "strongest")):
        errors.append("Draft does not compare sign-up-bonus value.")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: " + exc.msg], "warnings": []}))
