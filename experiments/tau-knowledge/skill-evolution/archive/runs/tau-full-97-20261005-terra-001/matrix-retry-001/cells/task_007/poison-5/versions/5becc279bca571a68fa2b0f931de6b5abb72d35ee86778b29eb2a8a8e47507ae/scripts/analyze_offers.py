#!/usr/bin/env python3
"""Classify structured promotion offers using an inclusive as-of date.
stdin: {"as_of":"YYYY-MM-DD", "offers":[...]}; stdout: JSON analysis.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def day(value):
    match = re.match(r"^\d{4}-\d{2}-\d{2}", str(value or ""))
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def value_usd(offer):
    reward = offer.get("reward") or {}
    try:
        amount = Decimal(str(reward.get("amount")))
    except (InvalidOperation, ValueError):
        return None
    kind = str(reward.get("kind", "")).lower()
    if kind in {"cash", "cash_back", "statement_credit"}:
        return amount
    if kind == "points" and reward.get("redemption_value_per_point") is not None:
        try:
            return amount * Decimal(str(reward["redemption_value_per_point"]))
        except (InvalidOperation, ValueError):
            return None
    return None


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("offers"), list):
        return {"ok": False, "errors": ["offers must be an array"], "warnings": []}
    as_of = day(payload.get("as_of"))
    if not as_of:
        return {"ok": False, "errors": ["as_of must be YYYY-MM-DD"], "warnings": []}
    active, other, warnings = [], [], []
    for raw in payload["offers"]:
        if not isinstance(raw, dict):
            continue
        offer = dict(raw)
        start, end = day(offer.get("window_start")), day(offer.get("window_end"))
        if not start or not end or start > end:
            offer["status"] = "date_unknown"
        elif as_of < start:
            offer["status"] = "upcoming"
        elif as_of > end:
            offer["status"] = "expired"
        else:
            offer["status"] = "active"
        if offer["status"] == "active" and offer.get("offer_type") == "signup_bonus":
            amount = value_usd(offer)
            offer["documented_usd_value"] = str(amount) if amount is not None else None
            if amount is None:
                warnings.append("No documented dollar comparison value for %s" % offer.get("card", "an offer"))
            active.append(offer)
        else:
            other.append(offer)

    def key(offer):
        amount = offer.get("documented_usd_value")
        return (amount is None, -(Decimal(amount) if amount is not None else Decimal(0)), offer.get("card", "").lower())

    active.sort(key=key)
    return {"ok": True, "as_of": as_of.isoformat(), "active_signup_bonuses": active,
            "inactive_or_nonbonus": other, "warnings": warnings, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
