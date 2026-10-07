#!/usr/bin/env python3
"""Validate a credit-card dispute and determine provisional-credit eligibility.

Reads the schema documented in SKILL.md from stdin and emits one JSON result.
This helper never submits a dispute or calls a bank tool.
"""
import json
import re
import sys
from datetime import date, datetime
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
REQUIRED = (
    "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
    "phone", "email", "address", "contacted_merchant", "purchase_date",
    "issue_noticed_date", "dispute_reason", "resolution_requested",
)


def parse_mmddyyyy(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        raise ValueError(f"{field} must use MM/DD/YYYY")
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        raise ValueError(f"{field} is not a real calendar date")


def parse_history_date(value):
    if not isinstance(value, str):
        raise ValueError("a dispute_history dispute_date is missing or not a string")
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        return parse_mmddyyyy(value, "dispute_history.dispute_date")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        raise ValueError("a dispute_history dispute_date is not MM/DD/YYYY or ISO-8601")


def decimal_amount(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number")
    try:
        text = str(value).strip().replace("$", "").replace(",", "")
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return amount


def one_year_before(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # Feb 29
        return day.replace(year=day.year - 1, day=28)


def prior_dispute_count(history, as_of):
    if not isinstance(history, list):
        raise ValueError("eligibility.dispute_history must be a list returned by the history tool")
    cutoff = one_year_before(as_of)
    count = 0
    for record in history:
        if not isinstance(record, dict):
            raise ValueError("each dispute_history item must be an object")
        disputed_on = parse_history_date(record.get("dispute_date"))
        if cutoff <= disputed_on <= as_of:
            count += 1
    return count


def eligibility(submission, data, errors, missing):
    needed = ("account_open_date", "card_type", "transaction_amount", "dispute_history", "as_of_date")
    for key in needed:
        if key not in data or data[key] is None or data[key] == "":
            missing.append("eligibility." + key)
    if any("eligibility." + key in missing for key in needed):
        return None, [], None
    try:
        opened = parse_mmddyyyy(data["account_open_date"], "eligibility.account_open_date")
        as_of = parse_mmddyyyy(data["as_of_date"], "eligibility.as_of_date")
        purchased = parse_mmddyyyy(submission.get("purchase_date"), "purchase_date")
        amount = decimal_amount(data["transaction_amount"], "eligibility.transaction_amount")
        count = prior_dispute_count(data["dispute_history"], as_of)
    except ValueError as exc:
        errors.append(str(exc))
        return None, [], None

    card_type = data["card_type"]
    if card_type not in LIMITS:
        errors.append("eligibility.card_type is not a supported provisional-credit tier")
        return None, [], None

    reasons = []
    if opened > as_of or (as_of - opened).days < 60:
        reasons.append("account has not been open at least 60 days")
    reason = submission.get("dispute_reason")
    qualifying_reason = reason in {"unauthorized_fraudulent_charge", "duplicate_charge"}
    if reason == "goods_services_not_received":
        qualifying_reason = (as_of - purchased).days > 30
        if not qualifying_reason:
            reasons.append("goods/services-not-received purchase is not more than 30 days old")
    elif not qualifying_reason:
        reasons.append("dispute reason is not eligible for provisional credit")
    limit = LIMITS[card_type]
    if amount < Decimal("25.00") or amount > limit:
        reasons.append("transaction amount is outside the card tier provisional-credit limit")
    if count > 2:
        reasons.append("more than two disputes were filed in the preceding 12 months")
    if reason != "unauthorized_fraudulent_charge" and submission.get("contacted_merchant") is not True:
        reasons.append("merchant was not contacted for a non-fraud dispute")
    return len(reasons) == 0, reasons, count


def main():
    try:
        request = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"valid": False, "missing": [], "errors": [f"invalid input JSON: {exc}"], "payload": None}))
        return
    if not isinstance(request, dict):
        print(json.dumps({"valid": False, "missing": [], "errors": ["input must be a JSON object"], "payload": None}))
        return

    submission = request.get("submission")
    data = request.get("eligibility")
    if not isinstance(submission, dict):
        submission = {}
    if not isinstance(data, dict):
        data = {}

    missing, errors = [], []
    for field in REQUIRED:
        if field not in submission or submission[field] is None or submission[field] == "":
            missing.append("submission." + field)
    if "contacted_merchant" in submission and not isinstance(submission["contacted_merchant"], bool):
        errors.append("contacted_merchant must be boolean")
    if submission.get("card_action") not in ACTIONS and "submission.card_action" not in missing:
        errors.append("card_action is not an allowed value")
    if "card_last_4_digits" in submission and not re.fullmatch(r"\d{4}", str(submission["card_last_4_digits"])):
        errors.append("card_last_4_digits must be exactly four digits")
    if submission.get("dispute_reason") not in REASONS and "submission.dispute_reason" not in missing:
        errors.append("dispute_reason is not an allowed value")
    if submission.get("resolution_requested") not in RESOLUTIONS and "submission.resolution_requested" not in missing:
        errors.append("resolution_requested is not an allowed value")
    for field in ("purchase_date", "issue_noticed_date"):
        if field in submission and submission[field] not in (None, ""):
            try:
                parse_mmddyyyy(submission[field], field)
            except ValueError as exc:
                errors.append(str(exc))

    partial = submission.get("partial_refund_amount")
    if submission.get("resolution_requested") == "partial_refund":
        if partial is None or partial == "":
            missing.append("submission.partial_refund_amount")
        else:
            try:
                if decimal_amount(partial, "partial_refund_amount") <= 0:
                    errors.append("partial_refund_amount must be greater than zero")
            except ValueError as exc:
                errors.append(str(exc))

    eligible, eligibility_reasons, count = eligibility(submission, data, errors, missing)
    valid = not missing and not errors and eligible is not None
    payload = None
    if valid:
        payload = {field: submission[field] for field in REQUIRED}
        payload["eligible_for_provisional_credit"] = eligible
        if submission["resolution_requested"] == "partial_refund":
            payload["partial_refund_amount"] = float(decimal_amount(partial, "partial_refund_amount"))

    print(json.dumps({
        "valid": valid,
        "missing": missing,
        "errors": errors,
        "provisional_credit": {
            "eligible": eligible,
            "reasons": eligibility_reasons,
            "prior_disputes_last_12_months": count,
        },
        "payload": payload,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
