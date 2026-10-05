#!/usr/bin/env python3
"""Validate credit-card dispute cases and prepare formal-filing arguments.

Reads the JSON schema in SKILL.md from stdin and writes one JSON object:
{"ready": bool, "errors": [{"case_index": int|null, "field": str,
"message": str}], "eligibility": [{"case_index": int, "eligible": bool|null,
"reasons": [str], "recent_dispute_count": int|null}], "tool_payloads":
[{"case_index": int, "arguments": object}]}.

This helper makes no banking-tool calls. The caller must retrieve profile, accounts,
last-four values, and dispute history before running it.
"""
import calendar
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
LIMITS = {
    "Bronze Rewards Card": Decimal("2500"), "EcoCard": Decimal("2500"),
    "Business Bronze Rewards Card": Decimal("2500"), "Crypto-Cash Back Card": Decimal("2500"),
    "Silver Rewards Card": Decimal("5000"), "Business Silver Rewards Card": Decimal("5000"),
    "Green Rewards Card": Decimal("5000"), "Silver Zoom Card": Decimal("5000"),
    "Gold Rewards Card": Decimal("10000"), "Business Gold Rewards Card": Decimal("10000"),
    "Platinum Rewards Card": Decimal("15000"), "Business Platinum Rewards Card": Decimal("15000"),
    "Diamond Elite Card": Decimal("25000"),
}
ELIGIBLE_REASONS = {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}


def error(errors, case_index, field, message):
    errors.append({"case_index": case_index, "field": field, "message": message})


def parse_date(value, strict=False):
    if not isinstance(value, str):
        raise ValueError("must be a date string")
    if strict:
        try:
            parsed = datetime.strptime(value, "%m/%d/%Y").date()
        except ValueError:
            raise ValueError("must use MM/DD/YYYY")
        if parsed.strftime("%m/%d/%Y") != value:
            raise ValueError("must use MM/DD/YYYY")
        return parsed
    try:
        return parse_date(value, True)
    except ValueError:
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
        except ValueError:
            raise ValueError("must be MM/DD/YYYY or an ISO timestamp")


def amount(value):
    if value is None or isinstance(value, bool):
        raise ValueError("must be a numeric amount")
    try:
        result = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("must be a numeric amount")
    if not result.is_finite():
        raise ValueError("must be finite")
    return result


def string(obj, key, errors, index=None):
    value = obj.get(key) if isinstance(obj, dict) else None
    if not isinstance(value, str) or not value.strip():
        error(errors, index, key, "is required and must be a nonempty string")
        return None
    return value.strip()


def one_year_before(day):
    year = day.year - 1
    return day.replace(year=year, day=min(day.day, calendar.monthrange(year, day.month)[1]))


def main(data):
    errors, eligibility, payloads = [], [], []
    if not isinstance(data, dict):
        return {"ready": False, "errors": [{"case_index": None, "field": "input", "message": "must be a JSON object"}], "eligibility": [], "tool_payloads": []}

    try:
        current = parse_date(data.get("current_date"), True)
    except ValueError as exc:
        current = None
        error(errors, None, "current_date", str(exc))

    customer = data.get("customer")
    if not isinstance(customer, dict):
        customer = {}
        error(errors, None, "customer", "must be an object")
    customer_values = {key: string(customer, key, errors) for key in ("full_name", "user_id", "phone", "email", "address")}

    history = data.get("dispute_history")
    recent_count = None
    if not isinstance(history, list):
        error(errors, None, "dispute_history", "must be a list, including [] when no prior disputes exist")
    elif current is not None:
        recent_count = 0
        cutoff = one_year_before(current)
        for record_number, record in enumerate(history):
            try:
                filed = parse_date(record.get("dispute_date") if isinstance(record, dict) else None)
            except ValueError as exc:
                error(errors, None, "dispute_history[%d].dispute_date" % record_number, str(exc))
                continue
            if cutoff <= filed <= current:
                recent_count += 1

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        error(errors, None, "cases", "must be a nonempty list")
        cases = []

    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            error(errors, index, "case", "must be an object")
            eligibility.append({"case_index": index, "eligible": None, "reasons": ["invalid case object"], "recent_dispute_count": recent_count})
            continue

        transaction_id = string(case, "transaction_id", errors, index)
        card_type = string(case, "card_type", errors, index)
        last4 = string(case, "card_last_4_digits", errors, index)
        if last4 is not None and not re.fullmatch(r"[0-9]{4}", last4):
            error(errors, index, "card_last_4_digits", "must contain exactly four digits")

        parsed_dates = {}
        for field in ("date_of_account_open", "purchase_date", "issue_noticed_date"):
            try:
                parsed_dates[field] = parse_date(case.get(field), True)
            except ValueError as exc:
                parsed_dates[field] = None
                error(errors, index, field, str(exc))

        try:
            transaction_amount = amount(case.get("transaction_amount"))
            if transaction_amount <= 0:
                raise ValueError("must be greater than zero")
        except ValueError as exc:
            transaction_amount = None
            error(errors, index, "transaction_amount", str(exc))

        reason = case.get("dispute_reason")
        if reason not in REASONS:
            error(errors, index, "dispute_reason", "must be a supported dispute reason")
        resolution = case.get("resolution_requested")
        if resolution not in RESOLUTIONS:
            error(errors, index, "resolution_requested", "must be a supported resolution")
        action = case.get("card_action")
        if action not in ACTIONS:
            error(errors, index, "card_action", "must be keep_active or cancel_and_reissue")
        contacted = case.get("contacted_merchant")
        if not isinstance(contacted, bool):
            error(errors, index, "contacted_merchant", "must be a boolean")

        partial = None
        if resolution == "partial_refund":
            try:
                partial = amount(case.get("partial_refund_amount"))
                if partial <= 0:
                    raise ValueError("must be greater than zero")
                if transaction_amount is not None and partial > transaction_amount:
                    raise ValueError("cannot exceed the transaction amount")
            except ValueError as exc:
                error(errors, index, "partial_refund_amount", str(exc))

        decision_notes = []
        decision_inputs = (current, recent_count, transaction_amount, parsed_dates["date_of_account_open"], parsed_dates["purchase_date"])
        can_decide = (all(value is not None for value in decision_inputs) and reason in REASONS and card_type in LIMITS and isinstance(contacted, bool))
        if card_type is not None and card_type not in LIMITS:
            error(errors, index, "card_type", "is not a recognized provisional-credit tier")
        eligible = None
        if can_decide:
            eligible = True
            if (current - parsed_dates["date_of_account_open"]).days < 60:
                eligible = False; decision_notes.append("account has been open fewer than 60 days")
            if reason not in ELIGIBLE_REASONS:
                eligible = False; decision_notes.append("reason is not eligible")
            if reason == "goods_services_not_received" and (current - parsed_dates["purchase_date"]).days <= 30:
                eligible = False; decision_notes.append("nonreceipt purchase is not more than 30 days old")
            if transaction_amount < Decimal("25") or transaction_amount > LIMITS[card_type]:
                eligible = False; decision_notes.append("amount is outside the tier limit")
            if recent_count > 2:
                eligible = False; decision_notes.append("more than two prior disputes were filed in 12 months")
            if reason != "unauthorized_fraudulent_charge" and not contacted:
                eligible = False; decision_notes.append("merchant was not contacted for a non-fraud dispute")
            if eligible:
                decision_notes.append("all provisional-credit criteria are satisfied")
        else:
            decision_notes.append("required eligibility inputs are incomplete or invalid")
        eligibility.append({"case_index": index, "eligible": eligible, "reasons": decision_notes, "recent_dispute_count": recent_count})

        has_case_error = any(item["case_index"] == index for item in errors)
        has_global_error = any(item["case_index"] is None for item in errors)
        if not has_case_error and not has_global_error and eligible is not None:
            arguments = {
                "transaction_id": transaction_id, "card_action": action,
                "card_last_4_digits": last4, "full_name": customer_values["full_name"],
                "user_id": customer_values["user_id"], "phone": customer_values["phone"],
                "email": customer_values["email"], "address": customer_values["address"],
                "contacted_merchant": contacted, "purchase_date": case["purchase_date"],
                "issue_noticed_date": case["issue_noticed_date"], "dispute_reason": reason,
                "resolution_requested": resolution, "eligible_for_provisional_credit": eligible,
            }
            if resolution == "partial_refund":
                arguments["partial_refund_amount"] = float(partial)
            payloads.append({"case_index": index, "arguments": arguments})

    ready = not errors and len(payloads) == len(cases)
    return {"ready": ready, "errors": errors, "eligibility": eligibility, "tool_payloads": payloads if ready else []}


if __name__ == "__main__":
    try:
        output = main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        output = {"ready": False, "errors": [{"case_index": None, "field": "input", "message": "invalid JSON: %s" % exc.msg}], "eligibility": [], "tool_payloads": []}
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
