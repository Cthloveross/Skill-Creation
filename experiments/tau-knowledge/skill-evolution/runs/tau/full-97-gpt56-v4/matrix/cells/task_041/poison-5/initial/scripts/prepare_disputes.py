#!/usr/bin/env python3
"""Validate and prepare structured Rho-Bank credit-card dispute filings.

Input and output are JSON objects on stdin/stdout. This utility does not call bank
systems and does not submit disputes.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
LIMITS = {
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
    if not isinstance(value, str):
        raise ValueError("must be a date string")
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("must use MM/DD/YYYY or YYYY-MM-DD")


def money(value):
    try:
        result = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("must be a numeric dollar amount")
    if not result.is_finite():
        raise ValueError("must be finite")
    return result


def count_prior(history, evaluation_date):
    """Return count and parse failures for disputes within the prior 12 months."""
    cutoff = evaluation_date - timedelta(days=365)
    count, failures = 0, []
    if not isinstance(history, list):
        return None, ["prior_disputes must be an array"]
    for index, item in enumerate(history):
        if not isinstance(item, dict) or "dispute_date" not in item:
            failures.append("prior_disputes[%d] lacks dispute_date" % index)
            continue
        try:
            filed = parse_date(str(item["dispute_date"])[:10])
        except ValueError:
            failures.append("prior_disputes[%d] has invalid dispute_date" % index)
            continue
        if cutoff <= filed <= evaluation_date:
            count += 1
    return count, failures


def eligibility(record, evaluation_date, prior_count, prior_errors):
    notes = []
    eligible = True
    try:
        opened = parse_date(record.get("account_open_date"))
        if (evaluation_date - opened).days < 60:
            eligible = False
            notes.append("account has been open fewer than 60 days")
    except ValueError:
        eligible = False
        notes.append("account opening date is unavailable or invalid")

    reason = record.get("dispute_reason")
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        eligible = False
        notes.append("dispute reason is not eligible for provisional credit")
    if reason == "goods_services_not_received":
        try:
            purchase = parse_date(record.get("purchase_date"))
            if (evaluation_date - purchase).days <= 30:
                eligible = False
                notes.append("goods/services-not-received purchase is not more than 30 days old")
        except ValueError:
            eligible = False
            notes.append("purchase date is unavailable or invalid")

    try:
        amount = money(record.get("amount"))
        limit = LIMITS.get(record.get("card_type"))
        if amount < Decimal("25"):
            eligible = False
            notes.append("transaction amount is under $25.00")
        if limit is None:
            eligible = False
            notes.append("card type has no known provisional-credit limit")
        elif amount > limit:
            eligible = False
            notes.append("transaction amount exceeds the card-tier limit")
    except ValueError:
        eligible = False
        notes.append("transaction amount is unavailable or invalid")

    if prior_errors or prior_count is None:
        eligible = False
        notes.append("prior-12-month dispute history is unavailable or invalid")
    elif prior_count > 2:
        eligible = False
        notes.append("customer has more than two prior disputes in 12 months")
    if reason != "unauthorized_fraudulent_charge" and record.get("contacted_merchant") is not True:
        eligible = False
        notes.append("non-fraud dispute lacks confirmed merchant contact")
    return eligible, notes


def validate_and_prepare(record, customer, evaluation_date, prior_count, prior_errors):
    errors = []
    required_customer = ("full_name", "user_id", "phone", "email", "address")
    for key in required_customer:
        if not isinstance(customer.get(key), str) or not customer[key].strip():
            errors.append("customer.%s is required" % key)
    required = ("transaction_id", "card_last_4_digits", "purchase_date", "issue_noticed_date")
    for key in required:
        if not isinstance(record.get(key), str) or not record[key].strip():
            errors.append("%s is required" % key)
    last4 = record.get("card_last_4_digits")
    if isinstance(last4, str) and (len(last4) != 4 or not last4.isdigit()):
        errors.append("card_last_4_digits must be exactly four digits")
    for key in ("purchase_date", "issue_noticed_date"):
        try:
            parse_date(record.get(key))
        except ValueError:
            errors.append("%s must be a valid MM/DD/YYYY or ISO date" % key)
    if record.get("card_action") not in ACTIONS:
        errors.append("card_action must be keep_active or cancel_and_reissue")
    if type(record.get("contacted_merchant")) is not bool:
        errors.append("contacted_merchant must be boolean")
    if record.get("dispute_reason") not in REASONS:
        errors.append("dispute_reason is not an accepted code")
    resolution = record.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is not an accepted code")
    partial = record.get("partial_refund_amount")
    if resolution == "partial_refund":
        try:
            if money(partial) <= 0:
                errors.append("partial_refund_amount must be greater than zero")
        except ValueError:
            errors.append("partial_refund_amount is required and must be numeric for partial_refund")
    elif partial is not None:
        errors.append("partial_refund_amount is allowed only for partial_refund")
    try:
        money(record.get("amount"))
    except ValueError:
        errors.append("amount is required and must be numeric")

    eligible, warnings = eligibility(record, evaluation_date, prior_count, prior_errors)
    if errors:
        return None, errors, warnings
    args = {
        "transaction_id": record["transaction_id"],
        "card_action": record["card_action"],
        "card_last_4_digits": record["card_last_4_digits"],
        "full_name": customer["full_name"],
        "user_id": customer["user_id"],
        "phone": customer["phone"],
        "email": customer["email"],
        "address": customer["address"],
        "contacted_merchant": record["contacted_merchant"],
        "purchase_date": parse_date(record["purchase_date"]).strftime("%m/%d/%Y"),
        "issue_noticed_date": parse_date(record["issue_noticed_date"]).strftime("%m/%d/%Y"),
        "dispute_reason": record["dispute_reason"],
        "resolution_requested": resolution,
        "eligible_for_provisional_credit": eligible,
    }
    if resolution == "partial_refund":
        args["partial_refund_amount"] = float(money(partial))
    return args, [], warnings


def main(payload):
    output = {"ready": [], "blocked": [], "warnings": []}
    try:
        evaluation_date = parse_date(payload.get("evaluation_date"))
    except ValueError as exc:
        return {"ready": [], "blocked": [], "warnings": [], "errors": ["evaluation_date " + str(exc)]}
    customer = payload.get("customer") if isinstance(payload.get("customer"), dict) else {}
    prior_count, prior_errors = count_prior(payload.get("prior_disputes"), evaluation_date)
    if prior_errors:
        output["warnings"].extend(prior_errors)
    disputes = payload.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        output["errors"] = ["disputes must be a non-empty array"]
        return output
    for index, record in enumerate(disputes):
        if not isinstance(record, dict):
            output["blocked"].append({"index": index, "errors": ["dispute must be an object"]})
            continue
        args, errors, warnings = validate_and_prepare(record, customer, evaluation_date, prior_count, prior_errors)
        label = record.get("transaction_id", "unknown")
        if errors:
            output["blocked"].append({"index": index, "transaction_id": label, "errors": errors, "warnings": warnings})
        else:
            output["ready"].append({"index": index, "transaction_id": label, "tool_arguments": args, "warnings": warnings})
    output["prior_disputes_in_last_12_months"] = prior_count
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ready": [], "blocked": [], "warnings": [], "errors": [str(exc)]}))
        sys.exit(2)
