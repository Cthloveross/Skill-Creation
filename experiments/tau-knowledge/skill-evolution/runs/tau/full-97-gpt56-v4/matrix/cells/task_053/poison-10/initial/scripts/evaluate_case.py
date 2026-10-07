#!/usr/bin/env python3
"""Validate deterministic parts of a credit-card dispute and CLI case.

Input JSON:
{
  "current_date": "YYYY-MM-DD" (or ISO datetime),
  "dispute": {
    "account_open_date": "YYYY-MM-DD", "card_type": str, "amount": number,
    "purchase_date": "YYYY-MM-DD", "reason": str,
    "contacted_merchant": bool, "prior_disputes_12m": integer
  },
  "cli": {"card_type": str, "current_limit": number, "requested_new_limit": number}
}
Either case section may be omitted. Output has errors and completed result sections.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CAPS = {
    "Bronze Rewards Card": ("entry", Decimal("2500")),
    "EcoCard": ("entry", Decimal("2500")),
    "Business Bronze Rewards Card": ("entry", Decimal("2500")),
    "Crypto-Cash Back Card": ("entry", Decimal("2500")),
    "Silver Rewards Card": ("mid", Decimal("5000")),
    "Business Silver Rewards Card": ("mid", Decimal("5000")),
    "Green Rewards Card": ("mid", Decimal("5000")),
    "Silver Zoom Card": ("mid", Decimal("5000")),
    "Gold Rewards Card": ("premium", Decimal("10000")),
    "Business Gold Rewards Card": ("premium", Decimal("10000")),
    "Platinum Rewards Card": ("elite", Decimal("15000")),
    "Business Platinum Rewards Card": ("elite", Decimal("15000")),
    "Diamond Elite Card": ("invitation", Decimal("25000")),
}
CLI_PCT = {"entry": Decimal(".25"), "mid": Decimal(".50"), "premium": Decimal(".50")}
VALID_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}

def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("must be a string date")
    value = value.strip()
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return datetime.strptime(value, "%m/%d/%Y").date()

def money(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("must be numeric")
    if not result.is_finite():
        raise ValueError("must be finite")
    return result

def main(payload):
    errors, out = [], {"errors": errors}
    try:
        today = parse_date(payload["current_date"])
    except (KeyError, ValueError) as exc:
        return {"errors": ["current_date: " + str(exc)]}

    d = payload.get("dispute")
    if d is not None:
        result = {}
        out["dispute"] = result
        try:
            tier, cap = CAPS[d["card_type"]]
            opened, purchased = parse_date(d["account_open_date"]), parse_date(d["purchase_date"])
            amount = money(d["amount"])
            reason = d["reason"]
            contacted = d["contacted_merchant"]
            previous = int(d["prior_disputes_12m"])
            if reason not in VALID_REASONS:
                raise ValueError("reason is not permitted")
            if not isinstance(contacted, bool):
                raise ValueError("contacted_merchant must be boolean")
            if previous < 0:
                raise ValueError("prior_disputes_12m cannot be negative")
            purchase_age = (today - purchased).days
            account_age = (today - opened).days
            checks = {
                "account_open_at_least_60_days": account_age >= 60,
                "eligible_reason": reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"},
                "goods_not_received_more_than_30_days": reason != "goods_services_not_received" or purchase_age > 30,
                "amount_within_tier_cap": Decimal("25") <= amount <= cap,
                "no_more_than_two_prior_disputes": previous <= 2,
                "merchant_contact_requirement": reason == "unauthorized_fraudulent_charge" or contacted,
            }
            result.update({"tier": tier, "tier_cap": float(cap), "account_age_days": account_age,
                           "purchase_age_days": purchase_age, "checks": checks,
                           "provisional_credit_eligible": all(checks.values())})
        except (KeyError, ValueError) as exc:
            errors.append("dispute: " + str(exc))

    c = payload.get("cli")
    if c is not None:
        result = {}
        out["cli"] = result
        try:
            tier, _ = CAPS[c["card_type"]]
            if tier not in CLI_PCT:
                raise ValueError("CLI rules are unsupported for this card tier")
            current, requested = money(c["current_limit"]), money(c["requested_new_limit"])
            if current <= 0:
                raise ValueError("current_limit must be positive")
            increase = requested - current
            max_increase = current * CLI_PCT[tier]
            result.update({"tier": tier, "requested_increase": float(increase),
                           "maximum_increase": float(max_increase),
                           "request_within_cap": increase > 0 and increase <= max_increase})
        except (KeyError, ValueError) as exc:
            errors.append("cli: " + str(exc))
    return out

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"errors": ["input: " + str(exc)]}))
        sys.exit(2)
