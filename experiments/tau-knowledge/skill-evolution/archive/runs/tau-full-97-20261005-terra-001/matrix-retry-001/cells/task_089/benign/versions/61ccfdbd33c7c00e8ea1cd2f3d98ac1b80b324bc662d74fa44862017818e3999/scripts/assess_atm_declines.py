#!/usr/bin/env python3
"""Read-only helper for normalized multi-card ATM decline investigations.

Read one JSON object from stdin and write one JSON object to stdout. No banking
calls or state-changing actions are performed. Account-level withdrawal history
is attributed to a card only when that account has exactly one ACTIVE card.
"""
import json
import sys
from datetime import datetime


def text(value):
    return "" if value is None else str(value).strip()


def money(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(text(value).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def date_value(value):
    raw = text(value)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            continue
    return None


def truth(value):
    return value is True or text(value).upper() == "TRUE"


def output(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def main():
    try:
        raw = json.load(sys.stdin)
    except Exception as exc:
        output({"errors": ["stdin must contain one JSON object: %s" % exc], "cards": []})
        return
    if not isinstance(raw, dict):
        output({"errors": ["top-level JSON value must be an object"], "cards": []})
        return

    errors, warnings = [], []
    collections = {}
    for name in ("accounts", "cards", "attempts", "transactions"):
        value = raw.get(name, [])
        if not isinstance(value, list):
            errors.append("%s must be an array" % name)
            value = []
        collections[name] = value
    current_date = date_value(raw.get("current_time"))
    if current_date is None:
        errors.append("current_time must begin with YYYY-MM-DD or be MM/DD/YYYY")
    if errors:
        output({"errors": errors, "warnings": warnings, "cards": []})
        return

    accounts = {
        text(item.get("account_id")): item
        for item in collections["accounts"]
        if isinstance(item, dict) and text(item.get("account_id"))
    }
    cards = [item for item in collections["cards"] if isinstance(item, dict)]

    active_card_ids_by_account = {}
    for card in cards:
        account_id, card_id = text(card.get("account_id")), text(card.get("card_id"))
        if account_id and card_id and text(card.get("status")).upper() == "ACTIVE":
            active_card_ids_by_account.setdefault(account_id, []).append(card_id)

    attempts = {}
    for item in collections["attempts"]:
        if not isinstance(item, dict):
            warnings.append("ignored non-object attempt")
            continue
        card_id, amount = text(item.get("card_id")), money(item.get("requested_amount"))
        if not card_id or amount is None or amount <= 0:
            warnings.append("ignored attempt lacking card_id and positive requested_amount")
            continue
        attempts[card_id] = amount

    card_usage, account_usage = {}, {}
    for transaction in collections["transactions"]:
        if not isinstance(transaction, dict):
            continue
        if text(transaction.get("type")).lower() != "atm_withdrawal":
            continue
        if date_value(transaction.get("date")) != current_date:
            continue
        amount = money(transaction.get("amount"))
        if amount is None or amount == 0:
            warnings.append("ignored same-day ATM withdrawal with nonnumeric/zero amount")
            continue
        amount = abs(amount)
        card_id, account_id = text(transaction.get("card_id")), text(transaction.get("account_id"))
        if card_id:
            card_usage[card_id] = card_usage.get(card_id, 0.0) + amount
        elif account_id:
            account_usage[account_id] = account_usage.get(account_id, 0.0) + amount

    results = []
    for card in cards:
        card_id, account_id = text(card.get("card_id")), text(card.get("account_id"))
        if not card_id:
            warnings.append("ignored card without card_id")
            continue
        account = accounts.get(account_id)
        item_warnings = []
        direct_limit = money(card.get("daily_atm_limit"))
        policy_limit = money(account.get("published_daily_atm_limit")) if account else None
        if direct_limit is not None and direct_limit >= 0:
            limit, limit_source = direct_limit, "card.daily_atm_limit"
        elif policy_limit is not None and policy_limit >= 0:
            limit, limit_source = policy_limit, "account.published_daily_atm_limit"
        else:
            limit, limit_source = None, None
            item_warnings.append("no returned or supplied published daily ATM limit")

        returned_used = money(card.get("daily_atm_used"))
        if returned_used is not None and returned_used >= 0:
            used, usage_source = returned_used, "card.daily_atm_used"
        elif card_id in card_usage:
            used, usage_source = card_usage[card_id], "same-day card-tagged transaction history"
        elif account_id in account_usage and len(active_card_ids_by_account.get(account_id, [])) == 1:
            used = account_usage[account_id]
            usage_source = "same-day account history; account has exactly one active card"
        else:
            used, usage_source = None, None
            if account_id in account_usage:
                item_warnings.append("account-level ATM usage cannot be assigned because multiple/no active cards were returned")
            else:
                item_warnings.append("no card-specific or sole-active-card ATM usage is available")

        card_status = text(card.get("status")).upper() or "UNKNOWN"
        account_status = text(account.get("status")).upper() if account else "UNKNOWN"
        requested = attempts.get(card_id)
        remaining = max(0.0, limit - used) if limit is not None and used is not None else None
        alert = truth(card.get("fraud_alert_active"))
        alert_source = text(card.get("alert_source")).lower()

        if card_status == "FROZEN":
            next_step = "ask_verified_owner_whether_to_unfreeze"
        elif card_status in ("CLOSED", "PENDING"):
            next_step = "resolve_card_status_before_limit_analysis"
        elif card_status != "ACTIVE":
            next_step = "confirm_card_status_before_any_action"
        elif account is None:
            next_step = "retrieve_linked_account_status"
        elif account_status != "OPEN":
            next_step = "nonopen_account_no_transaction_action"
        elif alert and alert_source == "bank_initiated":
            next_step = "security_transfer_do_not_clear_bank_initiated_alert"
        elif alert:
            next_step = "resolve_alert_source_and_required_verification"
        elif truth(card.get("velocity_blocked")):
            next_step = "offer_wait_or_verified_velocity_clear"
        elif truth(card.get("pin_locked")):
            next_step = "complete_pin_lock_risk_assessment"
        elif requested is not None and remaining is not None and requested > remaining:
            next_step = "requested_amount_exceeds_remaining_atm_limit"
        else:
            next_step = "review_available_balance_pending_activity_and_terminal_conditions"

        results.append({
            "card_id": card_id,
            "account_id": account_id or None,
            "card_status": card_status,
            "account_status": account_status,
            "requested_amount": requested,
            "daily_atm_limit": limit,
            "limit_source": limit_source,
            "daily_atm_used": used,
            "usage_source": usage_source,
            "remaining_atm_limit": remaining,
            "preliminary_next_step": next_step,
            "warnings": item_warnings,
        })

    output({"current_date": current_date.isoformat(), "errors": [], "warnings": warnings, "cards": results})


if __name__ == "__main__":
    main()
