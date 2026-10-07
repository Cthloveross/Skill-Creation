#!/usr/bin/env python3
"""Assess credit-card provisional-credit eligibility from JSON on stdin.

Input schema is documented in SKILL.md. Output is a JSON object with:
  eligible: true, false, or null when data is insufficient
  disqualifying_reasons: known policy failures
  missing_fields: required inputs not supplied
  validation_errors: malformed supplied inputs
  prior_disputes_in_last_12_months: integer when dates were usable
  card_limit: decimal string when card tier was recognized

This helper does not make banking calls and does not submit disputes.
"""

import calendar
import json
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

LIMITS = {
    "Bronze Rewards Card": Decimal("2500.00"),
    "EcoCard": Decimal("2500.00"),
    "Business Bronze Rewards Card": Decimal("2500.00"),
    "Crypto-Cash Back Card": Decimal("2500.00"),
    "Silver Rewards Card": Decimal("5000.00"),
    "Business Silver Rewards Card": Decimal("5000.00"),
    "Green Rewards Card": Decimal("5000.00"),
    "Silver Zoom Card": Decimal("5000.00"),
    "Gold Rewards Card": Decimal("10000.00"),
    "Business Gold Rewards Card": Decimal("10000.00"),
    "Platinum Rewards Card": Decimal("15000.00"),
    "Business Platinum Rewards Card": Decimal("15000.00"),
    "Diamond Elite Card": Decimal("25000.00"),
}

QUALIFYING_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
VALID_REASONS = QUALIFYING_REASONS | {
    "incorrect_amount",
    "goods_services_not_as_described",
    "canceled_subscription_still_charging",
    "refund_never_processed",
}


def parse_date(value):
    """Parse required MM/DD/YYYY or common ISO date/timestamp input."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be a nonempty date string")
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19] if "T" in text else text, fmt).date()
        except ValueError:
            pass
    raise ValueError("must use MM/DD/YYYY or an ISO date")


def parse_amount(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("must be a numeric amount")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip().replace("$", "").replace(",", "")
    else:
        raise ValueError("must be a numeric amount")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("must be a numeric amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("must be a nonnegative finite amount")
    return amount


def one_year_before(day):
    """Calendar-year boundary, adjusted safely for February 29."""
    year = day.year - 1
    return date(year, day.month, min(day.day, calendar.monthrange(year, day.month)[1]))


def assess(data):
    if not isinstance(data, dict):
        return {"eligible": None, "validation_errors": ["input must be a JSON object"],
                "missing_fields": [], "disqualifying_reasons": []}

    required = [
        "current_date", "account_open_date", "card_type", "transaction_amount",
        "purchase_date", "dispute_reason", "contacted_merchant", "prior_dispute_dates",
    ]
    missing = [field for field in required if field not in data or data[field] in (None, "")]
    errors = []
    parsed = {}

    for field in ("current_date", "account_open_date", "purchase_date"):
        if field not in missing:
            try:
                parsed[field] = parse_date(data[field])
            except ValueError as exc:
                errors.append(f"{field}: {exc}")

    if "transaction_amount" not in missing:
        try:
            parsed["transaction_amount"] = parse_amount(data["transaction_amount"])
        except ValueError as exc:
            errors.append(f"transaction_amount: {exc}")

    card_type = data.get("card_type")
    limit = LIMITS.get(card_type) if isinstance(card_type, str) else None
    if "card_type" not in missing and limit is None:
        errors.append("card_type: unsupported or unrecognized card tier")

    reason = data.get("dispute_reason")
    if "dispute_reason" not in missing and reason not in VALID_REASONS:
        errors.append("dispute_reason: unsupported reason code")

    contacted = data.get("contacted_merchant")
    if "contacted_merchant" not in missing and type(contacted) is not bool:
        errors.append("contacted_merchant: must be boolean")

    history_dates = []
    if "prior_dispute_dates" not in missing:
        source = data.get("prior_dispute_dates")
        if not isinstance(source, list):
            errors.append("prior_dispute_dates: must be an array of dates")
        else:
            for index, raw in enumerate(source):
                try:
                    history_dates.append(parse_date(raw))
                except ValueError as exc:
                    errors.append(f"prior_dispute_dates[{index}]: {exc}")

    result = {
        "eligible": None,
        "disqualifying_reasons": [],
        "missing_fields": missing,
        "validation_errors": errors,
        "prior_disputes_in_last_12_months": None,
        "card_limit": f"{limit:.2f}" if limit is not None else None,
    }
    if errors:
        return result

    failures = result["disqualifying_reasons"]
    current = parsed.get("current_date")
    opened = parsed.get("account_open_date")
    purchase = parsed.get("purchase_date")
    amount = parsed.get("transaction_amount")

    if current and opened and opened > current - timedelta(days=60):
        failures.append("account_open_less_than_60_days")
    if reason in VALID_REASONS and reason not in QUALIFYING_REASONS:
        failures.append("reason_not_eligible")
    if reason == "goods_services_not_received" and current and purchase:
        if (current - purchase).days <= 30:
            failures.append("goods_not_received_purchase_not_more_than_30_days_ago")
    if amount is not None:
        if amount < Decimal("25.00"):
            failures.append("amount_below_25")
        if limit is not None and amount > limit:
            failures.append("amount_exceeds_card_tier_limit")
    if reason != "unauthorized_fraudulent_charge" and type(contacted) is bool and not contacted:
        failures.append("merchant_not_contacted_for_non_fraud_dispute")

    if current and "prior_dispute_dates" not in missing:
        cutoff = one_year_before(current)
        count = sum(cutoff <= disputed_on <= current for disputed_on in history_dates)
        result["prior_disputes_in_last_12_months"] = count
        if count > 2:
            failures.append("more_than_two_prior_disputes_in_last_12_months")

    # A definite policy failure establishes false even if an unrelated fact is
    # missing. True requires every prerequisite to have been supplied.
    if failures:
        result["eligible"] = False
    elif not missing:
        result["eligible"] = True
    return result


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "eligible": None,
            "disqualifying_reasons": [],
            "missing_fields": [],
            "validation_errors": [f"invalid JSON input: {exc.msg}"],
        }))
        return
    print(json.dumps(assess(data), sort_keys=True))


if __name__ == "__main__":
    main()
