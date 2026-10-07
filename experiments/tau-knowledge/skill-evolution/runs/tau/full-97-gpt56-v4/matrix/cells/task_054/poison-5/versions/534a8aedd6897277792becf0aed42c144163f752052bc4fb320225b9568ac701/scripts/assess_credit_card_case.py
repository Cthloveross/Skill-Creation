#!/usr/bin/env python3
"""Pure, advisory eligibility calculations for the credit-card case Skill.

Reads one JSON object from stdin and writes one JSON object to stdout. No bank action
is performed. Dates must be MM/DD/YYYY. Required values for a definitive provisional
result are current_date, account_open_date, tier, transaction_amount, purchase_date,
dispute_reason, contacted_merchant, and dispute_dates (which may be []).
"""
import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

DATE_FORMAT = "%m/%d/%Y"
TIER_LIMITS = {
    "entry": Decimal("2500"),
    "mid": Decimal("5000"),
    "premium": Decimal("10000"),
    "elite": Decimal("15000"),
    "invitation": Decimal("25000"),
}
TIER_ALIASES = {
    "entry": "entry", "entry-tier": "entry",
    "mid": "mid", "mid-tier": "mid",
    "premium": "premium", "premium-tier": "premium",
    "elite": "elite", "elite-tier": "elite",
    "invitation": "invitation", "invitation-tier": "invitation",
}
ALLOWED_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be an MM/DD/YYYY string")
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        errors.append(f"{field} must use MM/DD/YYYY")
        return None


def decimal_value(value, field, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return result


def normalize_tier(value, errors):
    if not isinstance(value, str):
        errors.append("tier is required")
        return None
    normalized = TIER_ALIASES.get(value.strip().lower())
    if normalized is None:
        errors.append("tier must be Entry, Mid, Premium, Elite, or Invitation")
    return normalized


def main(data):
    errors = []
    current = parse_date(data.get("current_date"), "current_date", errors)
    opened = parse_date(data.get("account_open_date"), "account_open_date", errors)
    purchase = parse_date(data.get("purchase_date"), "purchase_date", errors)
    tier = normalize_tier(data.get("tier"), errors)
    amount = decimal_value(data.get("transaction_amount"), "transaction_amount", errors)
    reason = data.get("dispute_reason")
    contacted = data.get("contacted_merchant")

    if reason not in ALLOWED_REASONS:
        errors.append("dispute_reason is missing or unsupported")
    if not isinstance(contacted, bool):
        errors.append("contacted_merchant must be boolean")

    dispute_dates = data.get("dispute_dates")
    parsed_disputes = []
    if not isinstance(dispute_dates, list):
        errors.append("dispute_dates must be an array, including an empty array when none exist")
    else:
        for index, item in enumerate(dispute_dates):
            parsed = parse_date(item, f"dispute_dates[{index}]", errors)
            if parsed:
                parsed_disputes.append(parsed)

    provisional = {"eligible": False, "reasons": []}
    if not errors:
        if opened > current:
            provisional["reasons"].append("account open date is in the future")
        elif (current - opened).days < 60:
            provisional["reasons"].append("account is less than 60 days old")
        if amount < Decimal("25"):
            provisional["reasons"].append("transaction amount is below $25")
        if amount > TIER_LIMITS[tier]:
            provisional["reasons"].append("transaction amount exceeds the tier maximum")
        if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
            provisional["reasons"].append("dispute reason is not eligible")
        if reason == "goods_services_not_received" and (current - purchase).days <= 30:
            provisional["reasons"].append("goods/services-not-received purchase is not more than 30 days old")
        if reason != "unauthorized_fraudulent_charge" and not contacted:
            provisional["reasons"].append("merchant was not contacted for a non-fraud dispute")
        window_start = current - timedelta(days=365)
        recent_count = sum(window_start <= item <= current for item in parsed_disputes)
        if recent_count > 2:
            provisional["reasons"].append("more than two disputes were filed in the past 12 months")
        provisional["recent_dispute_count"] = recent_count
        provisional["eligible"] = not provisional["reasons"]
    else:
        provisional["reasons"].append("required fields are invalid or missing")

    cli = {"within_pre_submission_cap": None, "maximum_increase": None, "reasons": []}
    current_limit = data.get("current_limit")
    requested = data.get("requested_increase")
    if current_limit is not None or requested is not None:
        if tier is None:
            cli["reasons"].append("tier is required to calculate CLI cap")
        limit_value = decimal_value(current_limit, "current_limit", errors) if current_limit is not None else None
        requested_value = decimal_value(requested, "requested_increase", errors) if requested is not None else None
        if limit_value is None or requested_value is None:
            cli["reasons"].append("current_limit and requested_increase are both required for CLI assessment")
        elif limit_value < 0 or requested_value <= 0:
            cli["reasons"].append("CLI amounts must be positive")
        elif tier:
            percent = Decimal("0.25") if tier == "entry" else Decimal("0.50")
            maximum = limit_value * percent
            cli["maximum_increase"] = float(maximum)
            cli["within_pre_submission_cap"] = requested_value <= maximum
            if requested_value > maximum:
                cli["reasons"].append("requested increase exceeds the tier pre-submission cap")

    return {
        "provisional_credit": provisional,
        "cli_amount": cli,
        "validation_errors": errors,
        "notice": "Advisory calculation only; perform required live bank-history, pending-order, and workflow checks before any action.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"provisional_credit": {"eligible": False, "reasons": ["input could not be assessed"]}, "cli_amount": {"within_pre_submission_cap": None, "maximum_increase": None, "reasons": []}, "validation_errors": [str(exc)]}, sort_keys=True))
        sys.exit(1)
