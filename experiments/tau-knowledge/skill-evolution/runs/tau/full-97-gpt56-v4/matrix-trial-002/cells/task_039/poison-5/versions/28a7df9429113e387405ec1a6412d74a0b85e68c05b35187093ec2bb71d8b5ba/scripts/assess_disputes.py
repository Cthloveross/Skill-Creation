#!/usr/bin/env python3
"""Validate dispute records and calculate provisional-credit eligibility.

Input JSON:
{
  "as_of": "MM/DD/YYYY",
  "account_open_date": "MM/DD/YYYY",
  "card_type": "...",
  "prior_dispute_dates": ["MM/DD/YYYY"],
  "prior_dispute_count": 0,
  "disputes": [{"transaction_id": str, "amount": number,
                "purchase_date": "MM/DD/YYYY", "issue_noticed_date": "MM/DD/YYYY",
                "reason": str, "contacted_merchant": bool,
                "resolution_requested": str,
                "partial_refund_amount": number optional}]
}

Either prior_dispute_dates or prior_dispute_count is required. When dates are supplied,
the script derives a rolling-365-day pre-filing count. Output contains one assessment per
input dispute. It performs no banking actions.
"""
import json
import sys
from datetime import datetime, date, timedelta

DATE_FORMAT = "%m/%d/%Y"
VALID_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
VALID_RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be MM/DD/YYYY")
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        errors.append(f"{field} must be MM/DD/YYYY")
        return None


def tier_limit(card_type):
    value = (card_type or "").casefold()
    if "diamond elite" in value:
        return "invitation", 25000.0
    if "platinum" in value:
        return "elite", 15000.0
    if "gold" in value:
        return "premium", 10000.0
    if any(x in value for x in ("silver", "green rewards")):
        return "mid", 5000.0
    if any(x in value for x in ("bronze", "ecocard", "crypto-cash")):
        return "entry", 2500.0
    return None, None


def number(value):
    # bool is intentionally not a valid monetary amount.
    if isinstance(value, bool):
        raise ValueError
    return float(value)


def prior_count(data, as_of, errors):
    dates = data.get("prior_dispute_dates")
    if dates is not None:
        if not isinstance(dates, list):
            errors.append("prior_dispute_dates must be a list")
            return None
        start = as_of - timedelta(days=365)
        count = 0
        for i, item in enumerate(dates):
            d = parse_date(item, f"prior_dispute_dates[{i}]", errors)
            if d and start <= d <= as_of:
                count += 1
        return count
    if "prior_dispute_count" not in data:
        errors.append("provide prior_dispute_dates or prior_dispute_count")
        return None
    try:
        result = int(data["prior_dispute_count"])
        if result < 0 or result != data["prior_dispute_count"]:
            raise ValueError
        return result
    except (ValueError, TypeError):
        errors.append("prior_dispute_count must be a nonnegative integer")
        return None


def assess(dispute, as_of, account_open, limit, history_count):
    errors = []
    if not isinstance(dispute, dict):
        return {"transaction_id": None, "eligible_for_provisional_credit": False,
                "validation_errors": ["dispute must be an object"], "eligibility_failures": []}
    txid = dispute.get("transaction_id")
    if not isinstance(txid, str) or not txid:
        errors.append("transaction_id is required")
    purchase = parse_date(dispute.get("purchase_date"), "purchase_date", errors)
    parse_date(dispute.get("issue_noticed_date"), "issue_noticed_date", errors)
    reason = dispute.get("reason")
    if reason not in VALID_REASONS:
        errors.append("reason is not a permitted dispute reason")
    resolution = dispute.get("resolution_requested")
    if resolution not in VALID_RESOLUTIONS:
        errors.append("resolution_requested is not permitted")
    if resolution == "partial_refund":
        try:
            partial = number(dispute.get("partial_refund_amount"))
            if partial <= 0:
                errors.append("partial_refund_amount must be positive")
        except (ValueError, TypeError):
            errors.append("partial_refund_amount is required and must be numeric for partial_refund")
    elif "partial_refund_amount" in dispute and dispute["partial_refund_amount"] is not None:
        errors.append("partial_refund_amount is only allowed for partial_refund")
    contacted = dispute.get("contacted_merchant")
    if not isinstance(contacted, bool):
        errors.append("contacted_merchant must be boolean")
    try:
        amount = number(dispute.get("amount"))
        if amount < 0:
            errors.append("amount must not be negative")
    except (ValueError, TypeError):
        amount = None
        errors.append("amount must be numeric")

    failures = []
    if account_open is None:
        failures.append("account opening date unavailable")
    elif (as_of - account_open).days < 60:
        failures.append("account has been open fewer than 60 days")
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        failures.append("dispute reason is not eligible for provisional credit")
    if reason == "goods_services_not_received" and purchase is not None and (as_of - purchase).days <= 30:
        failures.append("goods/services-not-received purchase is not more than 30 days old")
    if amount is not None and (amount < 25 or limit is None or amount > limit):
        failures.append("amount is outside the applicable provisional-credit limit")
    if history_count is None:
        failures.append("prior dispute history is unavailable")
    elif history_count > 2:
        failures.append("more than two prior disputes in the past 12 months")
    if reason != "unauthorized_fraudulent_charge" and contacted is not True:
        failures.append("merchant was not contacted for a non-fraud dispute")
    return {
        "transaction_id": txid,
        "eligible_for_provisional_credit": not errors and not failures,
        "validation_errors": errors,
        "eligibility_failures": failures,
    }


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": [f"invalid JSON: {exc.msg}"], "disputes": []}))
        return
    errors = []
    as_of = parse_date(data.get("as_of"), "as_of", errors)
    account_open = parse_date(data.get("account_open_date"), "account_open_date", errors)
    tier, limit = tier_limit(data.get("card_type"))
    if limit is None:
        errors.append("unsupported or missing card_type; cannot determine provisional-credit limit")
    if as_of is None:
        print(json.dumps({"valid": False, "errors": errors, "disputes": []}))
        return
    history_count = prior_count(data, as_of, errors)
    disputes = data.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        errors.append("disputes must be a nonempty list")
        disputes = []
    result = [assess(d, as_of, account_open, limit, history_count) for d in disputes]
    print(json.dumps({
        "valid": not errors and all(not d["validation_errors"] for d in result),
        "errors": errors,
        "card_tier": tier,
        "provisional_credit_limit": limit,
        "prior_disputes_last_12_months": history_count,
        "disputes": result,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
