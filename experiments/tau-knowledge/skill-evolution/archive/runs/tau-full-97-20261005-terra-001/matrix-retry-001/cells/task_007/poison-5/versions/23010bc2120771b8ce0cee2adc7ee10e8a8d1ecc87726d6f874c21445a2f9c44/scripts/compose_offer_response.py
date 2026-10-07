#!/usr/bin/env python3
"""Compose a source-reviewed promotion-comparison draft from structured offers."""
import json
import os
import sys
from decimal import Decimal, InvalidOperation

sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze


def number(value):
    try:
        amount = Decimal(str(value))
        if amount == amount.to_integral():
            return format(int(amount), ",")
        return format(amount, ",.2f")
    except (InvalidOperation, ValueError):
        return "documented"


def reward_text(reward):
    reward = reward if isinstance(reward, dict) else {}
    kind = str(reward.get("kind", "bonus")).replace("_", " ")
    prefix = "$" if kind in {"statement credit", "cash back", "cash"} else ""
    text = prefix + number(reward.get("amount")) + " " + kind
    if kind == "points" and reward.get("point_type"):
        text = number(reward.get("amount")) + " " + str(reward["point_type"])
    rate = reward.get("redemption_value_per_point")
    if kind == "points" and rate is not None:
        try:
            equivalent = Decimal(str(reward.get("amount"))) * Decimal(str(rate))
            text += " (documented redemption value: about ${})".format(number(equivalent))
        except (InvalidOperation, ValueError):
            pass
    return text


def conditions(offer):
    q = offer.get("qualification") if isinstance(offer.get("qualification"), dict) else {}
    parts = []
    if q.get("invitation_required"):
        parts.append("invitation-only eligibility")
    if q.get("new_customer_required"):
        parts.append("eligible new-customer status")
    for key in ("spend_requirement", "spend_window", "good_standing", "other_conditions"):
        if q.get(key):
            parts.append(str(q[key]))
    if q.get("exclusions"):
        parts.append("documented transaction exclusions apply")
    return "; ".join(parts)


def fee_text(offer):
    fee = offer.get("annual_fee")
    if isinstance(fee, dict):
        return str(fee.get("description") or fee.get("standard") or "")
    return str(fee or "")


def offer_line(offer):
    scope = "business-card alternative" if str(offer.get("product_scope", "")).lower() == "business" else "consumer card"
    line = "- {} ({}): {}. Campaign: {} through {}.".format(
        offer["card"], scope, reward_text(offer.get("reward")), offer.get("window_start", "not documented"), offer.get("window_end", "not documented"))
    required = conditions(offer)
    if required:
        line += " Requirements: {}.".format(required)
    fee = fee_text(offer)
    if fee:
        line += " Documented standard annual fee: {}.".format(fee)
    return line


def main(payload):
    result = analyze(payload)
    if not result.get("ok"):
        return result
    offers = result["ranked_active_signup_bonuses"]
    if not offers:
        return dict(result, response="As of {}, no active sign-up bonus is supported by the supplied dated records.".format(result["as_of"]))

    leader = offers[0]
    lines = [
        "As of {}, the largest active headline sign-up bonus by documented redemption value is {}: {}.".format(
            result["as_of"], leader["card"], reward_text(leader.get("reward"))),
        offer_line(leader),
    ]
    if len(offers) > 1:
        lines.append("Other active sign-up bonuses:")
        lines.extend(offer_line(offer) for offer in offers[1:])
        consumer = next((x for x in offers if str(x.get("product_scope", "consumer")).lower() != "business" and x is not leader), None)
        if consumer:
            lines.append("Recommendation: {} has the highest stated value, but its invitation or eligibility terms and short qualification spend may make it impractical. {} is the active consumer alternative when its requirements are a better fit.".format(leader["card"], consumer["card"]))
        else:
            lines.append("Recommendation: {} has the highest stated value, but confirm that its eligibility terms, spend requirement, and annual-fee conditions fit before applying.".format(leader["card"]))
    else:
        lines.append("Recommendation: confirm that the eligibility terms, qualifying spend, and annual-fee conditions fit before applying.")
    return dict(result, response="\n\n".join(lines))


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: " + exc.msg], "warnings": []}))
