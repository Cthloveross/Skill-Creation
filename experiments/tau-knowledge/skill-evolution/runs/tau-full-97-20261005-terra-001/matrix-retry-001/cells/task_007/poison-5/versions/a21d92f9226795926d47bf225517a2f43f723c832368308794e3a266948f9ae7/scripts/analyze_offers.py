#!/usr/bin/env python3
"""Classify reviewed structured promotion offers against an inclusive as-of date.
Reads JSON from stdin and emits JSON to stdout.
Input: {"as_of":"YYYY-MM-DD", "offers":[offer,...]}.
"""
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_day(value):
    match = re.match(r"^\d{4}-\d{2}-\d{2}", str(value))
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def documented_value(offer):
    reward = offer.get("reward", {})
    kind = str(reward.get("kind", "")).lower()
    try:
        amount = Decimal(str(reward["amount"]))
    except (KeyError, InvalidOperation, ValueError):
        return None
    if kind in {"statement_credit", "cash_back", "cash"} and str(reward.get("currency", "")).upper() == "USD":
        return amount
    if kind == "points" and reward.get("redemption_value_per_point") is not None:
        try:
            return amount * Decimal(str(reward["redemption_value_per_point"]))
        except (InvalidOperation, ValueError):
            return None
    return None


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["input must be an object"], "warnings": []}
    as_of = parse_day(payload.get("as_of"))
    offers = payload.get("offers")
    if not as_of or not isinstance(offers, list):
        return {"ok": False, "errors": ["as_of and offers are required"], "warnings": []}

    active, other, warnings = [], [], []
    for raw in offers:
        if not isinstance(raw, dict):
            continue
        record = dict(raw)
        start, end = parse_day(record.get("window_start")), parse_day(record.get("window_end"))
        if not start or not end or start > end:
            record["status"] = "date_unknown"
        elif as_of < start:
            record["status"] = "upcoming"
        elif as_of > end:
            record["status"] = "expired"
        else:
            record["status"] = "active"
        if record["status"] == "active" and str(record.get("offer_type", "")).lower() == "signup_bonus":
            amount = documented_value(record)
            record["documented_usd_value"] = str(amount) if amount is not None else None
            if amount is None:
                warnings.append("%s: no documented USD comparison value" % record.get("card", "offer"))
            active.append(record)
        else:
            other.append(record)

    def order_key(record):
        amount = record.get("documented_usd_value")
        return (amount is None, -(Decimal(amount) if amount is not None else Decimal(0)), str(record.get("card", "")).lower())

    active.sort(key=order_key)
    return {"ok": True, "as_of": as_of.isoformat(), "active_signup_bonuses": active,
            "inactive_or_nonbonus": other, "warnings": warnings, "errors": []}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: " + exc.msg], "warnings": []}))
