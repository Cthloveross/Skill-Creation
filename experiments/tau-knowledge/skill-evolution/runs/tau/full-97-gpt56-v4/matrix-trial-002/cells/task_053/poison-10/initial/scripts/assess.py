#!/usr/bin/env python3
"""Pure policy calculator for credit-card dispute and CLI reviews.
Reads one JSON object from stdin and emits a JSON object on stdout.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD or MM/DD/YYYY")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must be YYYY-MM-DD or MM/DD/YYYY")


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def tier_from_card(card_type):
    entry = {
        "Bronze Rewards Card", "EcoCard", "Business Bronze Rewards Card",
        "Crypto-Cash Back Card",
    }
    mid = {
        "Silver Rewards Card", "Business Silver Rewards Card",
        "Green Rewards Card", "Silver Zoom Card",
    }
    premium = {"Gold Rewards Card", "Business Gold Rewards Card"}
    elite = {"Platinum Rewards Card", "Business Platinum Rewards Card"}
    invitation = {"Diamond Elite Card"}
    if card_type in entry:
        return "entry"
    if card_type in mid:
        return "mid"
    if card_type in premium:
        return "premium"
    if card_type in elite:
        return "elite"
    if card_type in invitation:
        return "invitation"
    raise ValueError("unsupported card type")


def dispute(data):
    tier = tier_from_card(data["card_type"])
    opened = parse_date(data["account_open_date"])
    as_of = parse_date(data["as_of"])
    purchased = parse_date(data["purchase_date"])
    amount = money(data["transaction_amount"], "transaction_amount")
    reason = data["reason"]
    contacted = data["contacted_merchant"]
    if not isinstance(contacted, bool):
        raise ValueError("contacted_merchant must be boolean")
    previous = [parse_date(x) for x in data.get("prior_dispute_dates", [])]
    if as_of < opened or as_of < purchased:
        raise ValueError("as_of cannot precede account opening or purchase date")
    age_days = (as_of - opened).days
    purchase_age_days = (as_of - purchased).days
    prior_12_months = sum(1 for x in previous if 0 <= (as_of - x).days <= 365)
    caps = {"entry": 2500, "mid": 5000, "premium": 10000, "elite": 15000, "invitation": 25000}
    qualifying_reasons = {
        "unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"
    }
    reason_ok = reason in qualifying_reasons
    delivery_timing_ok = reason != "goods_services_not_received" or purchase_age_days > 30
    amount_ok = Decimal("25") <= amount <= Decimal(caps[tier])
    merchant_ok = reason == "unauthorized_fraudulent_charge" or contacted
    flags = {
        "account_age_ok": age_days >= 60,
        "reason_ok": reason_ok,
        "delivery_timing_ok": delivery_timing_ok,
        "amount_ok": amount_ok,
        "prior_disputes_ok": prior_12_months <= 2,
        "merchant_contact_ok": merchant_ok,
    }
    return {
        "ok": all(flags.values()), "errors": [], "tier": tier,
        "account_age_days": age_days, "purchase_age_days": purchase_age_days,
        "prior_disputes_in_12_months": prior_12_months,
        "provisional_credit_cap": caps[tier], "checks": flags,
    }


def cli(data):
    tier = str(data["tier"]).lower().replace("-tier", "")
    policies = {
        "entry": {"pct": Decimal("0.25"), "age": 120, "cooldown": 120, "util": Decimal("70"), "months": 6},
        "mid": {"pct": Decimal("0.50"), "age": 90, "cooldown": 90, "util": Decimal("80"), "months": 3},
        "premium": {"pct": Decimal("0.50"), "age": 60, "cooldown": 60, "util": Decimal("90"), "months": 3},
    }
    if tier not in policies:
        raise ValueError("unsupported CLI tier")
    p = policies[tier]
    limit = money(data["current_limit"], "current_limit")
    balance = money(data["current_balance"], "current_balance")
    requested = money(data["requested_increase"], "requested_increase")
    if limit == 0:
        raise ValueError("current_limit must be greater than zero")
    opened, as_of = parse_date(data["account_open_date"]), parse_date(data["as_of"])
    if as_of < opened:
        raise ValueError("as_of cannot precede account opening")
    last = data.get("last_approved_cli_date")
    last_date = parse_date(last) if last else None
    if last_date and last_date > as_of:
        raise ValueError("last_approved_cli_date cannot be in the future")
    statuses = data.get("replacement_statuses", [])
    if not isinstance(statuses, list):
        raise ValueError("replacement_statuses must be a list")
    nonfinal = [str(x) for x in statuses if str(x).lower() not in {"delivered", "cancelled"}]
    age_days = (as_of - opened).days
    elapsed = (as_of - last_date).days if last_date else None
    utilization = (balance / limit) * Decimal("100")
    months = data["consecutive_on_time_months"]
    if not isinstance(months, int) or months < 0:
        raise ValueError("consecutive_on_time_months must be a nonnegative integer")
    pending_dispute = data["has_pending_dispute"]
    if not isinstance(pending_dispute, bool):
        raise ValueError("has_pending_dispute must be boolean")
    max_increase = limit * p["pct"]
    flags = {
        "positive_whole_dollar_request": requested > 0 and requested == requested.to_integral_value(),
        "amount_within_limit": requested <= max_increase,
        "account_age_ok": age_days >= p["age"],
        "cooldown_ok": last_date is None or elapsed >= p["cooldown"],
        "no_pending_dispute": not pending_dispute,
        "no_pending_replacement": not nonfinal,
        "utilization_ok": utilization < p["util"],
        "payment_history_ok": months >= p["months"],
    }
    return {
        "ok": all(flags.values()), "errors": [], "tier": tier,
        "maximum_increase": float(max_increase), "new_credit_limit": float(limit + requested),
        "account_age_days": age_days, "days_since_last_approved_cli": elapsed,
        "utilization_percent": float(utilization), "required_payment_months": p["months"],
        "nonfinal_replacement_statuses": nonfinal, "checks": flags,
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        mode = data.get("mode")
        if mode == "dispute":
            output = dispute(data)
        elif mode == "cli":
            output = cli(data)
        else:
            raise ValueError("mode must be 'dispute' or 'cli'")
    except (KeyError, ValueError, TypeError) as exc:
        output = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(output, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
