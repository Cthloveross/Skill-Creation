#!/usr/bin/env python3
"""Validate credit-card dispute cases and prepare filing-tool arguments.

Reads the JSON schema documented in SKILL.md from stdin. Writes:
{
  "ready": bool,
  "errors": [{"case_index": int|None, "field": str, "message": str}],
  "eligibility": [{"case_index": int, "eligible": bool|None,
                   "reasons": [str], "recent_dispute_count": int|None}],
  "tool_payloads": [{"case_index": int, "arguments": {...}}]
}
No tools are called by this program. The caller must retrieve current facts, card
last-four values, and dispute history before running it.
"""

import calendar
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
TIER_LIMITS = {
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
ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}


def parse_date(value):
    """Parse strict MM/DD/YYYY or the date portion of a standard ISO timestamp."""
    if not isinstance(value, str):
        raise ValueError("must be a date string")
    try:
        parsed = datetime.strptime(value, "%m/%d/%Y").date()
        if parsed.strftime("%m/%d/%Y") != value:
            raise ValueError
        return parsed
    except ValueError:
        pass
    iso_value = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso_value).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except (ValueError, TypeError):
            raise ValueError("must be MM/DD/YYYY or an ISO timestamp")


def decimal_value(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("must be a numeric amount")
    try:
        amount = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("must be a numeric amount")
    if not amount.is_finite():
        raise ValueError("must be finite")
    return amount


def twelve_months_before(day):
    year = day.year - 1
    return day.replace(year=year, day=min(day.day, calendar.monthrange(year, day.month)[1]))


def add_error(errors, case_index, field, message):
    errors.append({"case_index": case_index, "field": field, "message": message})


def required_string(obj, key, errors, case_index=None):
    value = obj.get(key) if isinstance(obj, dict) else None
    if not isinstance(value, str) or not value.strip():
        add_error(errors, case_index, key, "is required and must be a nonempty string")
        return None
    return value.strip()


def main(data):
    errors = []
    if not isinstance(data, dict):
        return {"ready": False, "errors": [{"case_index": None, "field": "input", "message": "must be a JSON object"}], "eligibility": [], "tool_payloads": []}

    try:
        current_day = parse_date(data.get("current_date"))
    except ValueError as exc:
        add_error(errors, None, "current_date", str(exc))
        current_day = None

    customer = data.get("customer")
    if not isinstance(customer, dict):
        add_error(errors, None, "customer", "must be an object")
        customer = {}
    customer_values = {key: required_string(customer, key, errors) for key in ("full_name", "user_id", "phone", "email", "address")}

    history = data.get("dispute_history")
    recent_count = None
    if not isinstance(history, list):
        add_error(errors, None, "dispute_history", "must be supplied as a list, including [] when no prior disputes exist")
    elif current_day is not None:
        cutoff = twelve_months_before(current_day)
        recent_count = 0
        for record_index, record in enumerate(history):
            value = record.get("dispute_date") if isinstance(record, dict) else None
            try:
                filed = parse_date(value)
            except ValueError:
                add_error(errors, None, "dispute_history[%d].dispute_date" % record_index, "must be a valid dispute date")
                continue
            if cutoff <= filed <= current_day:
                recent_count += 1

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        add_error(errors, None, "cases", "must be a nonempty list")
        cases = []

    eligibility = []
    payloads = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            add_error(errors, index, "case", "must be an object")
            eligibility.append({"case_index": index, "eligible": None, "reasons": ["invalid case object"], "recent_dispute_count": recent_count})
            continue

        transaction_id = required_string(case, "transaction_id", errors, index)
        card_type = required_string(case, "card_type", errors, index)
        last4 = required_string(case, "card_last_4_digits", errors, index)
        if last4 is not None and not re.fullmatch(r"\d{4}", last4):
            add_error(errors, index, "card_last_4_digits", "must contain exactly four digits")

        purchase = account_open = noticed = None
        for field, target in (("purchase_date", "purchase"), ("date_of_account_open", "account_open"), ("issue_noticed_date", "noticed")):
            try:
                parsed = parse_date(case.get(field))
                if not isinstance(case.get(field), str) or parsed.strftime("%m/%d/%Y") != case.get(field):
                    raise ValueError("must use MM/DD/YYYY")
                if target == "purchase": purchase = parsed
                elif target == "account_open": account_open = parsed
                else: noticed = parsed
            except ValueError as exc:
                add_error(errors, index, field, str(exc))

        amount = None
        try:
            amount = decimal_value(case.get("transaction_amount"))
            if amount <= 0:
                raise ValueError("must be greater than zero")
        except ValueError as exc:
            add_error(errors, index, "transaction_amount", str(exc))

        reason = case.get("dispute_reason")
        if reason not in REASONS:
            add_error(errors, index, "dispute_reason", "must be one of the supported reason codes")
        resolution = case.get("resolution_requested")
        if resolution not in RESOLUTIONS:
            add_error(errors, index, "resolution_requested", "must be one of the supported resolution codes")
        action = case.get("card_action")
        if action not in ACTIONS:
            add_error(errors, index, "card_action", "must be keep_active or cancel_and_reissue")
        contacted = case.get("contacted_merchant")
        if not isinstance(contacted, bool):
            add_error(errors, index, "contacted_merchant", "must be a boolean")

        partial = None
        if resolution == "partial_refund":
            try:
                partial = decimal_value(case.get("partial_refund_amount"))
                if partial <= 0:
                    raise ValueError("must be greater than zero")
                if amount is not None and partial > amount:
                    raise ValueError("cannot exceed the disputed transaction amount")
            except ValueError as exc:
                add_error(errors, index, "partial_refund_amount", str(exc))

        decision_reasons = []
        eligible = None
        eligibility_inputs_valid = all(x is not None for x in (current_day, recent_count, reason, card_type, amount, purchase, account_open, contacted)) and reason in REASONS and card_type in TIER_LIMITS and isinstance(contacted, bool)
        if card_type is not None and card_type not in TIER_LIMITS:
            add_error(errors, index, "card_type", "is not a recognized provisional-credit card tier")
        if eligibility_inputs_valid:
            eligible = True
            if (current_day - account_open).days < 60:
                eligible = False; decision_reasons.append("account has been open fewer than 60 days")
            if reason not in ELIGIBLE_REASONS:
                eligible = False; decision_reasons.append("dispute reason is not eligible")
            if reason == "goods_services_not_received" and (current_day - purchase).days <= 30:
                eligible = False; decision_reasons.append("goods/services nonreceipt purchase is not more than 30 days old")
            if amount < Decimal("25.00") or amount > TIER_LIMITS[card_type]:
                eligible = False; decision_reasons.append("amount is outside the card tier's eligible range")
            if recent_count > 2:
                eligible = False; decision_reasons.append("more than two disputes were filed in the preceding 12 months")
            if reason != "unauthorized_fraudulent_charge" and not contacted:
                eligible = False; decision_reasons.append("merchant was not contacted for a non-fraud dispute")
            if eligible:
                decision_reasons.append("all provisional-credit criteria are satisfied")
        else:
            decision_reasons.append("required eligibility inputs are incomplete or invalid")

        eligibility.append({"case_index": index, "eligible": eligible, "reasons": decision_reasons, "recent_dispute_count": recent_count})

        case_errors = [e for e in errors if e["case_index"] == index]
        global_errors = [e for e in errors if e["case_index"] is None]
        if not case_errors and not global_errors and eligible is not None:
            arguments = {
                "transaction_id": transaction_id,
                "card_action": action,
                "card_last_4_digits": last4,
                "full_name": customer_values["full_name"],
                "user_id": customer_values["user_id"],
                "phone": customer_values["phone"],
                "email": customer_values["email"],
                "address": customer_values["address"],
                "contacted_merchant": contacted,
                "purchase_date": case["purchase_date"],
                "issue_noticed_date": case["issue_noticed_date"],
                "dispute_reason": reason,
                "resolution_requested": resolution,
                "eligible_for_provisional_credit": eligible,
            }
            if resolution == "partial_refund":
                arguments["partial_refund_amount"] = float(partial)
            payloads.append({"case_index": index, "arguments": arguments})

    ready = not errors and len(payloads) == len(cases)
    return {"ready": ready, "errors": errors, "eligibility": eligibility, "tool_payloads": payloads if ready else []}


if __name__ == "__main__":
    try:
        supplied = json.load(sys.stdin)
        result = main(supplied)
    except json.JSONDecodeError as exc:
        result = {"ready": False, "errors": [{"case_index": None, "field": "input", "message": "invalid JSON: %s" % exc.msg}], "eligibility": [], "tool_payloads": []}
    print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))
