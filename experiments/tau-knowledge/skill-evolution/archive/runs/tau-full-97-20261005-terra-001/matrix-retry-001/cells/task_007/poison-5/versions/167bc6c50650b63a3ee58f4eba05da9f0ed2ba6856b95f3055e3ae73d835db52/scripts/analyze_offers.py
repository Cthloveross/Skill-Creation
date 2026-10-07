#!/usr/bin/env python3
"""Classify and conservatively rank structured credit-card promotion records."""
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str):
        return None
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", value.strip())
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def amount(value):
    try:
        if isinstance(value, bool):
            return None
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def status(offer, as_of):
    start = parse_date(offer.get("window_start"))
    end = parse_date(offer.get("window_end"))
    if not start or not end or start > end:
        return "date_unknown"
    if as_of < start:
        return "upcoming"
    if as_of > end:
        return "expired"
    return "active"


def usd_value(offer):
    reward = offer.get("reward")
    if not isinstance(reward, dict):
        return None, "missing reward"
    value = amount(reward.get("amount"))
    kind = str(reward.get("kind", "")).lower()
    if value is None:
        return None, "non-numeric reward amount"
    if kind in {"statement_credit", "cash_back", "cash"}:
        if str(reward.get("currency", "")).upper() != "USD":
            return None, "direct reward is not documented in USD"
        return value, None
    if kind == "points":
        rate = amount(reward.get("redemption_value_per_point"))
        if rate is None:
            return None, "no documented point redemption value"
        return value * rate, None
    return None, "unrankable reward type"


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("offers"), list):
        return {"ok": False, "errors": ["Input requires an offers array."], "warnings": []}
    as_of = parse_date(payload.get("as_of"))
    if not as_of:
        return {"ok": False, "errors": ["as_of must begin with YYYY-MM-DD."], "warnings": []}

    active, inactive, non_signup, warnings = [], [], [], []
    for offer in payload["offers"]:
        if not isinstance(offer, dict) or not str(offer.get("card", "")).strip():
            inactive.append({"status": "invalid", "record": offer})
            continue
        record = dict(offer)
        record["status"] = status(offer, as_of)
        if record["status"] != "active":
            inactive.append(record)
            continue
        if str(offer.get("offer_type", "")).lower() != "signup_bonus":
            non_signup.append(record)
            continue
        value, warning = usd_value(offer)
        record["documented_usd_value"] = str(value) if value is not None else None
        if warning:
            warnings.append("{}: {}".format(record["card"], warning))
        active.append(record)

    active.sort(key=lambda item: (
        item["documented_usd_value"] is None,
        -(Decimal(item["documented_usd_value"]) if item["documented_usd_value"] else Decimal(0)),
        str(item["card"]).lower(),
    ))
    return {
        "ok": True,
        "as_of": as_of.isoformat(),
        "ranked_active_signup_bonuses": active,
        "active_non_signup_offers": non_signup,
        "inactive_or_unknown_offers": inactive,
        "warnings": warnings,
        "errors": [],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: " + exc.msg], "warnings": []}))
