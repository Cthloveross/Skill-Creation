#!/usr/bin/env python3
"""Compose a qualification-aware draft from structured, source-reviewed offers."""
import json
import os
import sys
from decimal import Decimal
sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze


def n(value):
    try:
        amount = Decimal(str(value))
        return format(int(amount), ",") if amount == amount.to_integral() else format(amount, ",.2f")
    except Exception: return "documented"

def reward_text(reward):
    reward = reward if isinstance(reward, dict) else {}
    kind, amount = str(reward.get("kind", "bonus")).replace("_", " "), n(reward.get("amount"))
    return ("$" if kind in {"statement credit", "cash back", "cash"} else "") + amount + " " + kind

def conditions(offer):
    q = offer.get("qualification") if isinstance(offer.get("qualification"), dict) else {}
    parts = []
    if q.get("invitation_required"): parts.append("an invitation")
    if q.get("new_customer_required"): parts.append("new-customer eligibility")
    for key in ("eligibility", "spend_requirement", "spend_window", "good_standing", "other_conditions"):
        if q.get(key): parts.append(str(q[key]))
    if q.get("exclusions"): parts.append("documented exclusions apply")
    return "; ".join(parts)

def fee(offer):
    value = offer.get("annual_fee")
    if isinstance(value, dict): return str(value.get("description") or value.get("standard") or "")
    return str(value or "")

def line(offer):
    text = "- {}: {}".format(offer["card"], reward_text(offer.get("reward")))
    cond = conditions(offer)
    if cond: text += " after/with " + cond
    charge = fee(offer)
    if charge: text += ". Documented annual fee: " + charge
    if str(offer.get("product_scope", "")).lower() == "business": text += ". This is a business-card option, not a consumer-card offer"
    return text + "."

def main(payload):
    result = analyze(payload)
    if not result.get("ok"): return result
    offers = result["ranked_active_signup_bonuses"]
    if not offers:
        return dict(result, response="As of {}, I found no active sign-up bonuses supported by the supplied records.".format(result["as_of"]))
    leader = offers[0]
    lines = ["As of {}, the largest active headline sign-up bonus by documented value is {}: {}.".format(result["as_of"], leader["card"], reward_text(leader.get("reward")))]
    lead_conditions = conditions(leader)
    if lead_conditions: lines.append("It requires " + lead_conditions + ".")
    if fee(leader): lines.append("Documented annual fee: " + fee(leader) + ".")
    if len(offers) > 1:
        lines.append("Other active sign-up options:")
        lines.extend(line(offer) for offer in offers[1:])
        alternative = offers[1]
        lines.append("Bottom line: {} has the highest stated value, but its eligibility and short-term spending requirement may make it less accessible. {} is a lower-value alternative when its documented eligibility and spending requirement are a better fit.".format(leader["card"], alternative["card"]))
    return dict(result, response="\n\n".join(lines))

if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc: print(json.dumps({"ok": False, "errors": ["Invalid JSON input: " + exc.msg], "warnings": []}))
