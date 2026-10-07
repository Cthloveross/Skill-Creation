#!/usr/bin/env python3
"""Produce deterministic debit-card replacement recommendations.

Input is one JSON object on stdin. Output is one JSON object on stdout. This utility
never calls bank tools and does not establish eligibility beyond tier limits/waiting.
"""
import json
import sys
from datetime import datetime, timedelta


def parse_time(value):
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp is required and must be an ISO-8601 string")
    value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def result_error(message):
    return {"ok": False, "may_order_now": False, "blocker": message}


def main(data):
    try:
        tier = str(data["tier"]).upper()
        count = data["replacement_count_last_12_months"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("replacement_count_last_12_months must be a nonnegative integer")
        now = parse_time(data["now"])
        closed_at = parse_time(data["closed_at"])
        preference = data.get("preference", "free_best")
        if preference not in ("free_best", "paid_confirmed"):
            raise ValueError("preference must be free_best or paid_confirmed")
    except (KeyError, TypeError, ValueError) as exc:
        return result_error(str(exc))

    # delivery, delivery fee, design, design fee. CUSTOM is excluded unless an
    # actual upload is supplied; PREMIUM is the best available non-upload design.
    rules = {
        "ENTRY": {"limit": 2, "wait": timedelta(hours=48), "choice": ("STANDARD", 0, "CLASSIC", 0), "excess": 25},
        "MID": {"limit": 3, "wait": timedelta(0), "choice": ("STANDARD", 0, "CLASSIC", 0), "excess": 15},
        "PREMIUM": {"limit": 5, "wait": timedelta(0), "choice": ("EXPEDITED", 0, "PREMIUM", 0), "excess": None},
        "ELITE": {"limit": None, "wait": timedelta(0), "choice": ("RUSH", 0, "PREMIUM", 0), "excess": None},
    }
    if tier not in rules:
        return result_error("unsupported or missing checking-account tier")
    rule = rules[tier]

    if now < closed_at:
        return result_error("current time precedes closure time")
    if rule["wait"] and now < closed_at + rule["wait"]:
        return {
            "ok": True, "may_order_now": False,
            "blocker": "ENTRY replacements require a 48-hour wait after closure",
            "eligible_at": (closed_at + rule["wait"]).isoformat(),
            "tier": tier,
        }

    exceeded = rule["limit"] is not None and count >= rule["limit"]
    if exceeded:
        if rule["excess"] is None:
            return {
                "ok": True, "may_order_now": False, "tier": tier,
                "blocker": "replacement limit reached; this tier must wait until the oldest qualifying replacement leaves the rolling 12-month window",
            }
        if preference != "paid_confirmed":
            return {
                "ok": True, "may_order_now": False, "tier": tier,
                "blocker": "replacement limit reached; customer must either wait or explicitly confirm the excess replacement fee",
                "excess_replacement_fee": rule["excess"],
            }
        delivery, delivery_fee, design, design_fee = rule["choice"]
        return {
            "ok": True, "may_order_now": True, "tier": tier,
            "delivery_option": delivery, "delivery_fee": delivery_fee,
            "design_option": design, "design_fee": design_fee,
            "excess_replacement_fee": rule["excess"],
            "total_fee": delivery_fee + design_fee + rule["excess"],
            "note": "Excess fee requires prior explicit informed customer confirmation.",
        }

    delivery, delivery_fee, design, design_fee = rule["choice"]
    return {
        "ok": True, "may_order_now": True, "tier": tier,
        "delivery_option": delivery, "delivery_fee": delivery_fee,
        "design_option": design, "design_fee": design_fee,
        "excess_replacement_fee": 0, "total_fee": delivery_fee + design_fee,
        "note": "Recommendation is fee-free under the tier policy; still verify all live ordering prerequisites.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps(result_error("invalid JSON input: " + str(exc)), separators=(",", ":")))
