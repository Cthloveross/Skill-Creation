#!/usr/bin/env python3
"""Assess supplied credit-card closure prerequisite data.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
program is pure: it neither invokes bank tools nor changes any records.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "finalized"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def parse_money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("current_balance is required")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("current_balance must be numeric or a currency string") from exc


def status_of(item):
    if isinstance(item, str):
        return item.strip().lower()
    if isinstance(item, dict) and isinstance(item.get("status"), str):
        return item["status"].strip().lower()
    return None


def check_disputes(disputes):
    if disputes is None:
        return None, "Dispute history has not been checked."
    if not isinstance(disputes, list):
        return None, "Dispute history is not a list and requires review."
    statuses = [status_of(item) for item in disputes]
    if any(status is None for status in statuses):
        return None, "At least one dispute has no clear status and requires review."
    active = [status for status in statuses if status not in FINAL_DISPUTE_STATUSES]
    if active:
        return False, "Active or non-final dispute status blocks closure: " + ", ".join(active)
    return True, None


def check_replacements(orders):
    if orders is None:
        return None, "Replacement-order status has not been checked."
    if not isinstance(orders, list):
        return None, "Replacement-order data is not a list and requires review."
    statuses = [status_of(item) for item in orders]
    if any(status is None for status in statuses):
        return None, "At least one replacement order has no clear status and requires review."
    pending = [status for status in statuses if status not in FINAL_REPLACEMENT_STATUSES]
    if pending:
        return False, "Pending or non-final replacement order blocks closure: " + ", ".join(pending)
    return True, None


def main(payload):
    current = parse_date(payload.get("current_date"), "current_date")
    opened = parse_date(payload.get("account_open_date"), "account_open_date")
    balance = parse_money(payload.get("current_balance"))

    age_days = (current - opened).days
    age_ok = age_days >= 60
    balance_ok = balance == Decimal("0")
    disputes_ok, dispute_message = check_disputes(payload.get("disputes"))
    replacements_ok, replacement_message = check_replacements(payload.get("replacement_orders"))

    blockers = []
    review_required = []
    if not balance_ok:
        blockers.append("Outstanding balance must be exactly $0.00.")
    if not age_ok:
        blockers.append("Account must have been open for at least 60 days.")
    for result, message in ((disputes_ok, dispute_message), (replacements_ok, replacement_message)):
        if result is False:
            blockers.append(message)
        elif result is None:
            review_required.append(message)

    output = {
        "account_age_days": age_days,
        "checks": {
            "zero_balance": balance_ok,
            "minimum_account_age_60_days": age_ok,
            "no_active_or_pending_disputes": disputes_ok,
            "no_pending_replacement_orders": replacements_ok,
        },
        "blockers": blockers,
        "review_required": review_required,
        "eligible": not blockers and not review_required,
    }

    if "reward_points" in payload and payload["reward_points"] is not None:
        try:
            points = Decimal(str(payload["reward_points"]))
        except InvalidOperation as exc:
            raise ValueError("reward_points must be numeric") from exc
        output["rewards"] = {
            "points": str(points),
            "cash_value_at_0_01_per_point": str(
                (points * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            ),
        }

    request_value = payload.get("closure_request_date")
    if request_value is not None:
        request_date = parse_date(request_value, "closure_request_date")
        output["rewards_redemption_deadline"] = (request_date + timedelta(days=45)).isoformat()

    fee_value = payload.get("annual_fee_posted_date")
    if fee_value is not None:
        fee_date = parse_date(fee_value, "annual_fee_posted_date")
        elapsed = (current - fee_date).days
        output["annual_fee_refund"] = {
            "days_since_posting": elapsed,
            "eligible_within_37_days": 0 <= elapsed <= 37,
        }
    return output


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
