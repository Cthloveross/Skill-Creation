#!/usr/bin/env python3
"""Compose a customer-facing comparison from reviewed structured offers.
Reads {as_of, offers} JSON from stdin and emits analysis plus response JSON.
"""
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze


def number(value):
    amount = Decimal(str(value))
    return format(int(amount), ",") if amount == amount.to_integral() else format(amount, ",.2f")


def reward_text(reward):
    reward = reward or {}
    kind = str(reward.get("kind", "bonus")).replace("_", " ")
    amount = number(reward.get("amount", 0))
    if kind in {"statement credit", "cash back", "cash"}:
        return "$%s %s" % (amount, kind)
    text = "%s %s" % (amount, reward.get("point_type") or kind)
    if reward.get("redemption_value_per_point") is not None:
        value = Decimal(str(reward["amount"])) * Decimal(str(reward["redemption_value_per_point"]))
        text += " (about $%s at the documented $%s-per-point redemption rate)" % (number(value), reward["redemption_value_per_point"])
    return text


def offer_detail(offer):
    qualification = offer.get("qualification") or {}
    fee = offer.get("annual_fee") or {}
    conditions = []
    if qualification.get("invitation_required"):
        conditions.append("invitation-only")
    if qualification.get("new_customer_required"):
        conditions.append("eligible new customers only")
    for field in ("required_event", "spend_requirement", "spend_window", "good_standing"):
        if qualification.get(field):
            conditions.append(str(qualification[field]))
    if qualification.get("exclusions"):
        conditions.append("returns, credits, and other documented exclusions reduce qualifying spend")
    scope = "business-card alternative" if offer.get("product_scope") == "business" else "consumer card"
    text = "%s (%s): %s. Campaign: %s through %s." % (offer["card"], scope, reward_text(offer.get("reward")), offer.get("window_start"), offer.get("window_end"))
    if conditions:
        text += " Requirements: %s." % "; ".join(conditions)
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
        result["response"] = "As of %s, no active sign-up bonus is supported by the supplied dated records." % result["as_of"]
        return result
    lead = offers[0]
    lines = [
        "As of %s, the largest active headline sign-up bonus by documented redemption value is %s: %s." % (result["as_of"], lead["card"], reward_text(lead.get("reward"))),
        offer_detail(lead),
    ]
    if len(offers) > 1:
        lines.append("Other active sign-up bonuses:")
        lines.extend(offer_detail(offer) for offer in offers[1:])
    alternative = next((offer for offer in offers[1:] if offer.get("product_scope") != "business"), None)
    recommendation = "Recommendation: %s has the highest stated bonus" % lead["card"]
    if (lead.get("qualification") or {}).get("invitation_required"):
        recommendation += ", but it is invitation-only"
    recommendation += " and is practical only if its spend requirement and annual-fee conditions are realistic."
    if alternative:
        recommendation += " %s is the more accessible active consumer alternative when its lower threshold or new-customer access is a better fit." % alternative["card"]
    business = next((offer for offer in offers if offer.get("product_scope") == "business"), None)
    if business:
        recommendation += " %s is relevant only for a qualifying business applicant and should be compared separately on annual fee." % business["card"]
    result["response"] = "\n\n".join(lines + [recommendation])
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
