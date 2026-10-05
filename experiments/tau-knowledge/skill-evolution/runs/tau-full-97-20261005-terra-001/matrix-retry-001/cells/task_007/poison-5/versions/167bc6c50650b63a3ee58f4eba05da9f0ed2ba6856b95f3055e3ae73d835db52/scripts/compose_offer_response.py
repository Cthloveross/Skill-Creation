#!/usr/bin/env python3
"""Compose a customer-facing draft from reviewed structured promotion records."""
import json
import os
import sys
from decimal import Decimal, InvalidOperation

sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze


def fmt(value):
    try:
        number = Decimal(str(value))
        if number == number.to_integral():
            return format(int(number), ",")
        return format(number, ",.2f")
    except (InvalidOperation, ValueError):
        return "documented"


def reward_text(reward):
    reward = reward if isinstance(reward, dict) else {}
    kind = str(reward.get("kind", "bonus")).replace("_", " ")
    value = fmt(reward.get("amount"))
    if kind in {"statement credit", "cash back", "cash"}:
        return "${} {}".format(value, kind)
    label = str(reward.get("point_type") or kind)
    text = "{} {}".format(value, label)
    if kind == "points" and reward.get("redemption_value_per_point") is not None:
        try:
            equivalent = Decimal(str(reward["amount"])) * Decimal(str(reward["redemption_value_per_point"]))
            text += " (about ${} at the documented redemption rate)".format(fmt(equivalent))
        except (InvalidOperation, ValueError):
            pass
    return text


def requirement_text(offer):
    q = offer.get("qualification") if isinstance(offer.get("qualification"), dict) else {}
    pieces = []
    if q.get("invitation_required"):
        pieces.append("invitation-only")
    if q.get("new_customer_required"):
        pieces.append("eligible new customers only")
    for field in ("required_event", "spend_requirement", "spend_window", "good_standing"):
        if q.get(field):
            pieces.append(str(q[field]))
    if q.get("exclusions"):
        pieces.append("returns, credits, and other documented exclusions can reduce qualifying spend")
    if q.get("other_conditions"):
        pieces.append(str(q["other_conditions"]))
    return "; ".join(pieces)


def fee_text(offer):
    fee = offer.get("annual_fee")
    if not isinstance(fee, dict):
        return ""
    pieces = []
    if fee.get("standard"):
        pieces.append("standard annual fee: {}".format(fee["standard"]))
    if fee.get("waiver_condition"):
        pieces.append(str(fee["waiver_condition"]))
    return "; ".join(pieces)


def line(offer):
    scope = "business-card alternative" if str(offer.get("product_scope", "")).lower() == "business" else "consumer card"
    text = "- {} ({}): {}. Campaign: {} through {}.".format(
        offer["card"], scope, reward_text(offer.get("reward")),
        offer.get("window_start", "not documented"), offer.get("window_end", "not documented"))
    requirements = requirement_text(offer)
    if requirements:
        text += " Requirements: {}.".format(requirements)
    fee = fee_text(offer)
    if fee:
        text += " {}.".format(fee)
    return text


def main(payload):
    result = analyze(payload)
    if not result.get("ok"):
        return result
    offers = result["ranked_active_signup_bonuses"]
    if not offers:
        response = "As of {}, no active sign-up bonus is supported by the supplied dated records.".format(result["as_of"])
        return dict(result, response=response)

    leader = offers[0]
    lines = [
        "As of {}, the largest active headline sign-up bonus by documented redemption value is {}: {}.".format(
            result["as_of"], leader["card"], reward_text(leader.get("reward"))),
        line(leader),
    ]
    if len(offers) > 1:
        lines.append("Other active sign-up bonuses:")
        lines.extend(line(offer) for offer in offers[1:])

    consumer_alternative = next((offer for offer in offers[1:] if str(offer.get("product_scope", "consumer")).lower() != "business"), None)
    leader_invited = bool((leader.get("qualification") or {}).get("invitation_required"))
    recommendation = "Recommendation: {} has the highest stated bonus".format(leader["card"])
    if leader_invited:
        recommendation += ", but it is invitation-only"
    recommendation += " and should be considered only if its qualification spend and annual-fee conditions are realistic."
    if consumer_alternative:
        recommendation += " {} is the active consumer alternative when its lower threshold or broader new-customer access is a better fit.".format(consumer_alternative["card"])
    business = next((offer for offer in offers if str(offer.get("product_scope", "")).lower() == "business"), None)
    if business:
        recommendation += " {} is relevant only for a qualifying business applicant; compare its fee separately if minimizing annual fees matters.".format(business["card"])
    lines.append(recommendation)
    return dict(result, response="\n\n".join(lines))


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: " + exc.msg], "warnings": []}))
