#!/usr/bin/env python3
"""Advisory calculator for ATM-decline triage.

Reads one JSON object from stdin and emits one JSON object to stdout. It never
calls banking tools and cannot authorize, request, or clear a banking action.
"""

import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation


def fail(message):
    print(json.dumps({"ok": False, "error": message}, separators=(",", ":")))
    raise SystemExit(0)


def as_money(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a non-negative number")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} must be a non-negative number")
    return amount


def money_text(value):
    return format(value.quantize(Decimal("0.01")), "f")


def parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a date string")
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError(f"{label} must be YYYY-MM-DD or MM/DD/YYYY")


def required_object(item, keys, label):
    if not isinstance(item, dict):
        raise ValueError(f"{label} must be an object")
    missing = [key for key in keys if key not in item]
    if missing:
        raise ValueError(f"{label} is missing: {', '.join(missing)}")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    for key in ("requested_amount", "current_date", "cards", "accounts", "transactions"):
        if key not in payload:
            raise ValueError(f"input is missing: {key}")
    if not isinstance(payload["cards"], list) or not isinstance(payload["accounts"], list) or not isinstance(payload["transactions"], list):
        raise ValueError("cards, accounts, and transactions must be arrays")

    requested = as_money(payload["requested_amount"], "requested_amount")
    today = parse_date(payload["current_date"], "current_date")
    accounts = {}
    for index, account in enumerate(payload["accounts"]):
        required_object(account, ("account_id", "status", "date_opened"), f"accounts[{index}]")
        if not isinstance(account["account_id"], str) or not account["account_id"]:
            raise ValueError(f"accounts[{index}].account_id must be a nonempty string")
        if account["account_id"] in accounts:
            raise ValueError("account_id values must be unique")
        opened = parse_date(account["date_opened"], f"accounts[{index}].date_opened")
        accounts[account["account_id"]] = {"raw": account, "opened": opened}

    cutoff = today - timedelta(days=30)
    overdraft_by_account = {account_id: False for account_id in accounts}
    malformed_transaction_dates = []
    for index, transaction in enumerate(payload["transactions"]):
        if not isinstance(transaction, dict):
            raise ValueError(f"transactions[{index}] must be an object")
        account_id = transaction.get("account_id")
        if account_id not in accounts:
            continue
        if transaction.get("type") != "overdraft_fee":
            continue
        if "date" not in transaction:
            malformed_transaction_dates.append(index)
            continue
        transaction_date = parse_date(transaction["date"], f"transactions[{index}].date")
        if cutoff <= transaction_date <= today:
            overdraft_by_account[account_id] = True

    results = []
    for index, card in enumerate(payload["cards"]):
        required_object(card, ("card_id", "account_id", "status", "daily_atm_limit", "daily_atm_used"), f"cards[{index}]")
        if not isinstance(card["card_id"], str) or not card["card_id"]:
            raise ValueError(f"cards[{index}].card_id must be a nonempty string")
        account_id = card["account_id"]
        if account_id not in accounts:
            raise ValueError(f"cards[{index}].account_id does not match an input account")
        limit = as_money(card["daily_atm_limit"], f"cards[{index}].daily_atm_limit")
        used = as_money(card["daily_atm_used"], f"cards[{index}].daily_atm_used")
        remaining = max(limit - used, Decimal("0"))
        account = accounts[account_id]
        age_days = (today - account["opened"]).days
        if age_days < 0:
            raise ValueError(f"cards[{index}] has an account opening date in the future")

        max_new_limit = limit * Decimal("1.5")
        proposed_limit = card.get("proposed_new_limit")
        proposed_ok = None
        if proposed_limit is not None:
            proposed = as_money(proposed_limit, f"cards[{index}].proposed_new_limit")
            proposed_ok = proposed <= max_new_limit

        alert = card.get("fraud_alert_active")
        source = card.get("alert_source")
        security_warning = None
        if alert is True and source == "bank_initiated":
            security_warning = "bank_initiated_fraud_alert: escalate; do_not_clear"
        elif alert is True and source == "customer_initiated":
            security_warning = "customer_initiated_fraud_alert: clear_only_after_identity_and_legitimacy_confirmation"
        elif card.get("velocity_blocked") is True:
            security_warning = "velocity_block: normally_expires_after_30_minutes; early_clear_requires_identity_and_confirmation"

        increase_preconditions = {
            "account_open": account["raw"].get("status") == "OPEN",
            "account_age_at_least_60_days": age_days >= 60,
            "no_overdraft_fee_in_previous_30_days": False if malformed_transaction_dates else not overdraft_by_account[account_id],
            "card_active": card.get("status") == "ACTIVE",
            "no_prior_temporary_increase_in_24_hours": "unknown",
            "customer_explicitly_confirmed_exact_limit": "unknown",
            "proposed_limit_within_150_percent_of_current": proposed_ok,
        }
        results.append({
            "card_id": card["card_id"],
            "account_id": account_id,
            "current_daily_atm_limit": money_text(limit),
            "daily_atm_used": money_text(used),
            "remaining_daily_atm_allowance": money_text(remaining),
            "requested_amount": money_text(requested),
            "requested_amount_exceeds_remaining_allowance": requested > remaining,
            "request_exceeds_current_daily_limit": requested > limit,
            "maximum_permitted_temporary_limit": money_text(max_new_limit),
            "security_warning": security_warning,
            "temporary_increase_preconditions": increase_preconditions,
            "advisory": "Daily-limit arithmetic does not prove available funds, ATM availability, ownership, authority, terminal limits, or action eligibility."
        })

    return {
        "ok": True,
        "current_date": today.isoformat(),
        "requested_amount": money_text(requested),
        "transaction_date_warnings": malformed_transaction_dates,
        "cards": results,
        "next_step": "Use live banking-tool results and complete identity, authority, and confirmation checks before any banking action."
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        output = main(data)
        print(json.dumps(output, separators=(",", ":"), sort_keys=True))
    except json.JSONDecodeError:
        fail("stdin must contain one valid JSON object")
    except ValueError as exc:
        fail(str(exc))
