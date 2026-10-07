#!/usr/bin/env python3
"""Check whether a promotion-comparison response covers supplied active offers.

Input: {"response": string, "offers": [...], optional "as_of": "YYYY-MM-DD"}.
Offers use the analyze_offers schema. Output is JSON with ok, errors, warnings,
and checked_cards. This helper is deterministic and makes no external calls.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze


def normalized(value):
    return " ".join(str(value).lower().replace("$", " $").split())


def amount_forms(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return []
    if number.is_integer():
        integer = int(number)
        return [str(integer), format(integer, ",")]
    return [str(number), format(number, ",.2f")]


def contains_any(text, values):
    return any(value and value.lower() in text for value in values)


def condition_texts(record):
    q = record.get("qualification")
    return q if isinstance(q, dict) else {}


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
        return {"ok": False, "errors": ["response must be a string in a top-level JSON object."], "warnings": []}
    analysis_payload = {"as_of": payload.get("as_of"), "offers": payload.get("offers")}
    analysis = analyze(analysis_payload)
    if not analysis.get("ok"):
        return {"ok": False, "errors": analysis.get("errors", []), "warnings": analysis.get("warnings", [])}

    response = normalized(payload["response"])
    errors, warnings, checked = [], list(analysis.get("warnings", [])), []
    refusal_phrases = ("don't have current promotion records", "do not have current promotion records", "cannot confirm which offers are active", "promotion records are unavailable")
    if contains_any(response, refusal_phrases) and analysis["ranked_active_signup_bonuses"]:
        errors.append("Response denies current promotion records although active structured offers were supplied.")

    for record in analysis["ranked_active_signup_bonuses"]:
        card = str(record.get("card", ""))
        checked.append(card)
        if normalized(card) not in response:
            errors.append("Missing active card name: {}.".format(card))
        reward = record.get("reward") if isinstance(record.get("reward"), dict) else {}
        amount = amount_forms(reward.get("amount"))
        if amount and not contains_any(response, amount):
            errors.append("Missing reward amount for {}.".format(card))
        q = condition_texts(record)
        spend = q.get("spend_requirement")
        if spend and not contains_any(response, amount_forms_from_text(spend)):
            warnings.append("Check that {} includes its documented spend requirement.".format(card))
        if q.get("invitation_required") is True and not contains_any(response, ("invitation", "invited", "invite-only", "invitation-only")):
            errors.append("Missing invitation restriction for {}.".format(card))
        if q.get("new_customer_required") is True and "new customer" not in response:
            errors.append("Missing new-customer restriction for {}.".format(card))
        if str(record.get("product_scope", "")).lower() == "business" and "business" not in response:
            errors.append("Missing business-card context for {}.".format(card))
        fee = record.get("annual_fee")
        if fee and not any(token in response for token in ("annual fee", "fee waived", "fee waiver")):
            warnings.append("Check that {} includes documented annual-fee terms.".format(card))

    if len(analysis["ranked_active_signup_bonuses"]) > 1 and not contains_any(response, ("largest", "highest", "best", "top", "most valuable", "strongest")):
        errors.append("Response does not identify or compare the highest-value active bonus.")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "checked_cards": checked}


def amount_forms_from_text(value):
    if not isinstance(value, str):
        return []
    return re.findall(r"\d[\d,]*(?:\.\d+)?", value)


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: {}".format(exc.msg)], "warnings": []}))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["Unexpected processing error: {}".format(exc)], "warnings": []}))
