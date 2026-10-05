#!/usr/bin/env python3
"""Compose a customer-facing promotion comparison from reviewed structured offers."""
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze


def amount(value):
    n = Decimal(str(value))
    return format(int(n), ",") if n == n.to_integral() else format(n, ",.2f")


def reward_text(reward):
    reward = reward or {}
    kind = str(reward.get("kind", "bonus")).replace("_", " ")
    if kind in {"statement credit", "cash back", "cash"}:
        return "$%s %s" % (amount(reward.get("amount", 0)), kind)
    text = "%s %s" % (amount(reward.get("amount", 0)), reward.get("point_type") or kind)
    if reward.get("redemption_value_per_point") is not None:
        redeemed = Decimal(str(reward["amount"])) * Decimal(str(reward["redemption_value_per_point"]))
        text += " (about $%s when redeemed at the documented $%s-per-point rate)" % (amount(redeemed), reward["redemption_value_per_point"])
    return text


def detail(offer):
    q, fee = offer.get("qualification") or {}, offer.get("annual_fee") or {}
    requirements = []
    if q.get("invitation_required"):
        requirements.append("invitation-only")
    if q.get("new_customer_required"):
        requirements.append("eligible new customers only")
    for key in ("required_event", "spend_requirement", "spend_window", "good_standing"):
        if q.get(key):
            requirements.append(str(q[key]))
    if q.get("exclusions"):
        requirements.append("documented exclusions, including returns or credits where applicable, reduce qualifying spend")
    scope = "business-card alternative" if offer.get("product_scope") == "business" else "consumer card"
    text = "%s (%s): %s. Campaign: %s through %s." % (offer["card"], scope, reward_text(offer.get("reward")), offer["window_start"], offer["window_end"])
    if requirements:
        text += " Requirements: %s." % "; ".join(requirements)
    if fee.get("standard"):
        text += " Standard annual fee: %s." % fee["standard"]
    if fee.get("waiver_condition"):
        text += " %s." % fee["waiver_condition"]
    return text


def main(payload):
    result = analyze(payload)
    if not result.get("ok"):
        return result
    offers = result["active_signup_bonuses"]
    if not offers:
        result["response"] = "As of %s, the supplied dated records do not support an active sign-up bonus." % result["as_of"]
        return result
    leader = offers[0]
    lines = [
        "As of %s, the largest active headline sign-up bonus by documented redemption value is %s: %s." % (result["as_of"], leader["card"], reward_text(leader.get("reward"))),
        detail(leader)
    ]
    if len(offers) > 1:
        lines.append("Other active sign-up bonuses:")
        lines.extend(detail(offer) for offer in offers[1:])
    consumer_alternative = next((x for x in offers[1:] if x.get("product_scope") != "business"), None)
    recommendation = "Recommendation: %s has the highest stated bonus" % leader["card"]
    if (leader.get("qualification") or {}).get("invitation_required"):
        recommendation += ", but it is invitation-only"
    recommendation += " and is suitable only if the stated spend requirement, timeframe, and annual-fee conditions are realistic."
    if consumer_alternative:
        recommendation += " %s is the more accessible active consumer alternative when its new-customer terms and lower spending burden are a better fit." % consumer_alternative["card"]
    business = next((x for x in offers if x.get("product_scope") == "business"), None)
    if business:
        recommendation += " %s is a business-card option only and should be compared separately for a qualifying business applicant, including its annual fee." % business["card"]
    result["response"] = "\n\n".join(lines + [recommendation])
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
