#!/usr/bin/env python3
"""Evaluate supplied credit-card closure prerequisites without making any actions.

Reads one JSON object from stdin and emits one JSON object to stdout. See SKILL.md
for the input schema. This helper intentionally treats missing or ambiguous facts as
blockers so an execution agent must obtain live confirmation before banking actions.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required and must be a date string")
    raw = value.strip()
    if len(raw) >= 10 and raw[4:5] == "-":
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field} must use MM/DD/YYYY or YYYY-MM-DD")


def parse_balance(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("account.current_balance is required")
    if isinstance(value, int):
        # Integer inputs represent cents so callers can avoid floating-point values.
        return Decimal(value) / Decimal(100)
    if isinstance(value, (str, float, Decimal)):
        text = str(value).strip().replace("$", "").replace(",", "")
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("account.current_balance is not a valid amount") from exc
    raise ValueError("account.current_balance has an unsupported type")


def replacement_result(orders):
    if orders is None:
        return False, "Replacement-order status has not been checked."
    if not isinstance(orders, list):
        return False, "Replacement-order response is ambiguous."
    non_final = []
    for order in orders:
        if not isinstance(order, dict):
            return False, "Replacement-order response contains an ambiguous order."
        status = order.get("status")
        if not isinstance(status, str) or status.strip().lower() not in FINAL_REPLACEMENT_STATUSES:
            non_final.append(str(status) if status is not None else "unknown")
    if non_final:
        return False, "Pending replacement-card activity blocks closure: " + ", ".join(non_final)
    return True, None


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account = payload.get("account")
    if not isinstance(account, dict):
        raise ValueError("account must be a JSON object")

    blockers = []
    facts = {}
    authenticated_user_id = payload.get("authenticated_user_id")
    account_user_id = account.get("user_id")
    account_id = account.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        blockers.append("The requested credit-card account ID is missing.")
    if not isinstance(authenticated_user_id, str) or not authenticated_user_id.strip():
        blockers.append("Authenticated customer identity is missing.")
    elif account_user_id != authenticated_user_id:
        blockers.append("The requested account does not match the authenticated customer.")

    if payload.get("identity_verified") is not True:
        blockers.append("Standard identity verification has not been completed.")

    balance = parse_balance(account.get("current_balance"))
    facts["current_balance"] = f"{balance:.2f}"
    if balance != Decimal("0.00"):
        blockers.append(f"Outstanding balance must be $0.00 (current supplied balance: ${balance:.2f}).")

    disputes = account.get("pending_disputes")
    if not isinstance(disputes, bool):
        blockers.append("Pending-dispute status is unknown or ambiguous.")
    elif disputes:
        blockers.append("Active or pending transaction disputes must be fully resolved.")
    facts["pending_disputes"] = disputes if isinstance(disputes, bool) else None

    today = parse_date(payload.get("as_of"), "as_of")
    opened = parse_date(account.get("date_opened"), "account.date_opened")
    age_days = (today - opened).days
    facts["account_age_days"] = age_days
    if age_days < 60:
        blockers.append("Account must be open for at least 60 days.")

    replacement_ok, replacement_message = replacement_result(payload.get("replacement_orders"))
    facts["replacement_orders_clear"] = replacement_ok
    if not replacement_ok:
        blockers.append(replacement_message)

    tenure = {"known": False, "at_least_two_years": None}
    tenure_start = payload.get("customer_tenure_start")
    if tenure_start is not None:
        start = parse_date(tenure_start, "customer_tenure_start")
        tenure_days = (today - start).days
        tenure = {
            "known": True,
            "days": tenure_days,
            "at_least_two_years": tenure_days >= 730,
        }
    facts["customer_tenure"] = tenure

    eligible = not blockers
    retention = {
        "permitted_now": eligible,
        "annual_fee_path": (
            "may_offer_one_year_waiver" if tenure["at_least_two_years"] is True
            else "may_offer_same_category_no_fee_downgrade" if tenure["at_least_two_years"] is False
            else "obtain_customer_tenure_before_deciding_waiver_eligibility"
        ),
    }
    return {
        "ok": True,
        "eligible": eligible,
        "blockers": blockers,
        "facts": facts,
        "retention": retention,
        "next_step": (
            "Eligibility passed; check prior closure-reason history before retention or closure."
            if eligible else
            "Explain the listed blockers and do not make retention offers or process closure."
        ),
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "eligible": False, "error": str(exc)}))
