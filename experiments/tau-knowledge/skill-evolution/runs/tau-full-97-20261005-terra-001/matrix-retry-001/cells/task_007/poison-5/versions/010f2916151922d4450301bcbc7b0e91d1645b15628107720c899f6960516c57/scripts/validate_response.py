#!/usr/bin/env python3
"""Validate coverage of active source-supported offers in a proposed response.

stdin: document-helper input plus {"response":"customer-facing text"}
stdout: {"ok":bool, "errors":[...], "warnings":[...]}
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
        if name.lower() not in text:
            errors.append("Missing active offer name: " + name)
        reward_amount = str(offer["reward"]["amount"])
        if reward_amount not in numeric:
            errors.append("Missing reward amount: " + name)
        for boundary in (offer["start"], offer["end"]):
            if boundary not in payload["response"]:
                errors.append("Missing campaign date %s: %s" % (boundary, name))
        facts = offer.get("facts", {})
        if facts.get("spend_amount") is not None and str(facts["spend_amount"]) not in numeric:
            errors.append("Missing spend threshold: " + name)
        if facts.get("months") is not None:
            phrases = ("%d month" % facts["months"], "first month" if facts["months"] == 1 else "")
            if not any(phrase and phrase in text for phrase in phrases):
                errors.append("Missing qualification period: " + name)
        if facts.get("invitation_required") and not any(word in text for word in ("invitation", "invited", "invite-only")):
            errors.append("Missing invitation restriction: " + name)
        if offer.get("scope") == "business" and "business" not in text:
            errors.append("Missing business-only context: " + name)
    if len(active) > 1 and not any(word in text for word in ("largest", "highest", "best", "top", "most valuable", "strongest")):
        errors.append("Missing explicit value comparison")
    return {"ok": not errors, "errors": errors, "warnings": analysis.get("warnings", [])}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
