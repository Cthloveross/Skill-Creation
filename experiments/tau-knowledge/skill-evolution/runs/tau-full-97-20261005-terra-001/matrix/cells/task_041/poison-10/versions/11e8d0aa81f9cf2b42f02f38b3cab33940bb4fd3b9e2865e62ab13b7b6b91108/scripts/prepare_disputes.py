#!/usr/bin/env python3
"""Validate dispute records and calculate provisional-credit eligibility.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
performs no external calls and never submits a dispute.
"""
import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "incorrect_amount",
    "goods_services_not_received",
    "goods_services_not_as_described",
    "canceled_subscription_still_charging",
    "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
TIER_LIMITS = {
    "Bronze Rewards Card": Decimal("2500"),
    "EcoCard": Decimal("2500"),
    "Business Bronze Rewards Card": Decimal("2500"),
    "Crypto-Cash Back Card": Decimal("2500"),
    "Silver Rewards Card": Decimal("5000"),
    "Business Silver Rewards Card": Decimal("5000"),
    "Green Rewards Card": Decimal("5000"),
    "Silver Zoom Card": Decimal("5000"),
    "Gold Rewards Card": Decimal("10000"),
    "Business Gold Rewards Card": Decimal("10000"),
    "Platinum Rewards Card": Decimal("15000"),
    "Business Platinum Rewards Card": Decimal("15000"),
    "Diamond Elite Card": Decimal("25000"),
}


def parse_date(value):
    """Accept MM/DD/YYYY, YYYY-MM-DD, or timestamps beginning YYYY-MM-DD."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:10] if fmt == "%Y-%m-%d" else value, fmt).date()
        except ValueError:
            pass
    raise ValueError("invalid date: %s" % value)


def mmddyyyy(value):
    return parse_date(value).strftime("%m/%d/%Y")


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("%s must be a number" % field)
    if not result.is_finite():
        raise ValueError("%s must be finite" % field)
    return result


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def history_count(history, current):
    start = current - timedelta(days=365)
    count = 0
    invalid = 0
    for record in history:
        try:
            dispute_date = parse_date(record.get("dispute_date"))
            if start <= dispute_date <= current:
                count += 1
        except (AttributeError, ValueError):
            invalid += 1
    return count, invalid


def eligibility(row, current, previous_count):
    """Return eligibility boolean and explicit failed guideline conditions."""
    failures = []
    amount = money(row.get("transaction_amount"), "transaction_amount")
    limit = TIER_LIMITS.get(row.get("card_type"))
    if limit is None:
        failures.append("unsupported or missing card_type prevents tier-limit determination")
    try:
        open_date = parse_date(row.get("account_open_date"))
        if (current - open_date).days < 60:
            failures.append("account has been open fewer than 60 days")
    except ValueError:
        failures.append("invalid or missing account_open_date")
    reason = row.get("dispute_reason")
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        failures.append("dispute reason is not eligible for provisional credit")
    if reason == "goods_services_not_received":
        try:
            purchase = parse_date(row.get("purchase_date"))
            if (current - purchase).days <= 30:
                failures.append("goods/services-not-received purchase is not more than 30 days old")
        except ValueError:
            failures.append("invalid or missing purchase_date")
    if amount < Decimal("25"):
        failures.append("transaction amount is below $25.00")
    if limit is not None and amount > limit:
        failures.append("transaction amount exceeds the card tier provisional-credit limit")
    if previous_count > 2:
        failures.append("more than two previous disputes in the past 12 months")
    if reason != "unauthorized_fraudulent_charge" and row.get("contacted_merchant") is not True:
        failures.append("non-fraud dispute requires prior merchant contact")
    return len(failures) == 0, failures


def validate_and_build(row, user, current, history_ready, previous_count):
    errors = []
    for field in ("transaction_id", "card_last_4_digits", "card_action", "purchase_date",
                  "issue_noticed_date", "dispute_reason", "resolution_requested"):
        if field not in row or row.get(field) in (None, ""):
            errors.append("missing %s" % field)
    for field in ("full_name", "user_id", "phone", "email", "address"):
        if not nonempty(user.get(field)):
            errors.append("missing user.%s" % field)
    if not (isinstance(row.get("card_last_4_digits"), str) and row.get("card_last_4_digits").isdigit()
            and len(row.get("card_last_4_digits")) == 4):
        errors.append("card_last_4_digits must be exactly four digits")
    if row.get("card_action") not in ACTIONS:
        errors.append("card_action is not permitted")
    if not isinstance(row.get("contacted_merchant"), bool):
        errors.append("contacted_merchant must be boolean")
    if row.get("dispute_reason") not in REASONS:
        errors.append("dispute_reason is not permitted")
    if row.get("resolution_requested") not in RESOLUTIONS:
        errors.append("resolution_requested is not permitted")
    try:
        purchase_date = mmddyyyy(row.get("purchase_date"))
    except ValueError:
        purchase_date = None
        errors.append("purchase_date must be a valid date")
    try:
        noticed_date = mmddyyyy(row.get("issue_noticed_date"))
    except ValueError:
        noticed_date = None
        errors.append("issue_noticed_date must be a valid date")
    partial = None
    if row.get("resolution_requested") == "partial_refund":
        try:
            partial = money(row.get("partial_refund_amount"), "partial_refund_amount")
            if partial <= 0:
                errors.append("partial_refund_amount must be greater than zero")
        except ValueError as exc:
            errors.append(str(exc))
    elif row.get("partial_refund_amount") is not None:
        errors.append("partial_refund_amount is only allowed for partial_refund")

    eligibility_value = None
    eligibility_failures = []
    if not history_ready:
        errors.append("complete prior-dispute history is required to determine provisional credit")
    else:
        try:
            eligibility_value, eligibility_failures = eligibility(row, current, previous_count)
        except ValueError as exc:
            errors.append(str(exc))

    payload = None
    if not errors and eligibility_value is not None:
        payload = {
            "transaction_id": row["transaction_id"],
            "card_action": row["card_action"],
            "card_last_4_digits": row["card_last_4_digits"],
            "full_name": user["full_name"],
            "user_id": user["user_id"],
            "phone": user["phone"],
            "email": user["email"],
            "address": user["address"],
            "contacted_merchant": row["contacted_merchant"],
            "purchase_date": purchase_date,
            "issue_noticed_date": noticed_date,
            "dispute_reason": row["dispute_reason"],
            "resolution_requested": row["resolution_requested"],
            "eligible_for_provisional_credit": eligibility_value,
        }
        if partial is not None:
            payload["partial_refund_amount"] = float(partial)
    return {
        "transaction_id": row.get("transaction_id"),
        "eligible_for_provisional_credit": eligibility_value,
        "eligibility_failures": eligibility_failures,
        "errors": errors,
        "payload_ready": payload is not None,
        "filing_payload": payload,
    }


def main(data):
    try:
        current = parse_date(data.get("current_date"))
    except (AttributeError, ValueError) as exc:
        return {"error": "current_date is required and must be valid: %s" % exc}
    history = data.get("history", [])
    if not isinstance(history, list):
        return {"error": "history must be a list"}
    disputes = data.get("disputes", [])
    if not isinstance(disputes, list):
        return {"error": "disputes must be a list"}
    user = data.get("user", {})
    if not isinstance(user, dict):
        return {"error": "user must be an object"}
    previous_count, invalid_history_dates = history_count(history, current)
    history_ready = data.get("history_complete") is True and invalid_history_dates == 0
    results = [validate_and_build(row if isinstance(row, dict) else {}, user, current,
                                  history_ready, previous_count) for row in disputes]
    return {
        "current_date": current.isoformat(),
        "prior_disputes_in_past_12_months": previous_count,
        "history_ready": history_ready,
        "history_warnings": ([] if history_ready else [
            "history_complete must be true and every history record must have a valid dispute_date"
        ]),
        "results": results,
        "summary": {
            "total": len(results),
            "ready_to_file": sum(1 for result in results if result["payload_ready"]),
            "blocked": sum(1 for result in results if not result["payload_ready"]),
            "provisional_credit_eligible": sum(
                1 for result in results if result["eligible_for_provisional_credit"] is True
            ),
        },
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("top-level input must be an object")
        print(json.dumps(main(incoming), ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
