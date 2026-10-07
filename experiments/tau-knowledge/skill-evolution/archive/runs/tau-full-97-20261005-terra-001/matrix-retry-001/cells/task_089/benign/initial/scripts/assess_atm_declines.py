#!/usr/bin/env python3
"""Read-only normalization helper for multi-card ATM decline investigations.

Reads one JSON object from stdin and writes one JSON object to stdout. It does
not call banking tools and never authorizes an action.
"""
import json
import re
import sys
from datetime import datetime


def as_text(value):
    return "" if value is None else str(value).strip()


def money(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = as_text(value).replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def date_key(value):
    text = as_text(value)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return None


def true(value):
    return value is True or as_text(value).upper() == "TRUE"


def emit(payload):
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def main():
    try:
        raw = json.load(sys.stdin)
    except Exception as exc:
        emit({"errors": ["stdin must contain one JSON object: %s" % exc], "cards": []})
        return
    if not isinstance(raw, dict):
        emit({"errors": ["top-level JSON value must be an object"], "cards": []})
        return

    errors = []
    warnings = []
    accounts = raw.get("accounts", [])
    cards = raw.get("cards", [])
    attempts = raw.get("attempts", [])
    transactions = raw.get("transactions", [])
    for label, value in (("accounts", accounts), ("cards", cards), ("attempts", attempts), ("transactions", transactions)):
        if not isinstance(value, list):
            errors.append("%s must be an array" % label)
    if errors:
        emit({"errors": errors, "cards": []})
        return

    today = date_key(raw.get("current_time"))
    if not today:
        errors.append("current_time must begin with YYYY-MM-DD or be MM/DD/YYYY")

    account_by_id = {as_text(a.get("account_id")): a for a in accounts if isinstance(a, dict) and as_text(a.get("account_id"))}
    attempt_by_card = {}
    for attempt in attempts:
        if not isinstance(attempt, dict):
            warnings.append("ignored non-object attempt")
            continue
        card_id = as_text(attempt.get("card_id"))
        amount = money(attempt.get("requested_amount"))
        if not card_id or amount is None or amount <= 0:
            warnings.append("ignored attempt lacking a card_id and positive requested_amount")
            continue
        attempt_by_card[card_id] = amount

    # Only transactions explicitly tagged with a card can establish card usage.
    tx_used = {}
    unassigned_atm_by_account = {}
    for tx in transactions:
        if not isinstance(tx, dict) or as_text(tx.get("type")).lower() != "atm_withdrawal":
            continue
        if today and date_key(tx.get("date")) != today:
            continue
        amount = money(tx.get("amount"))
        if amount is None or amount == 0:
            continue
        withdrawal = abs(amount)
        card_id = as_text(tx.get("card_id"))
        account_id = as_text(tx.get("account_id"))
        if card_id:
            tx_used[card_id] = tx_used.get(card_id, 0.0) + withdrawal
        elif account_id:
            unassigned_atm_by_account[account_id] = unassigned_atm_by_account.get(account_id, 0.0) + withdrawal

    results = []
    for card in cards:
        if not isinstance(card, dict):
            warnings.append("ignored non-object card")
            continue
        card_id = as_text(card.get("card_id"))
        account_id = as_text(card.get("account_id"))
        if not card_id:
            warnings.append("ignored card without card_id")
            continue
        account = account_by_id.get(account_id)
        card_status = as_text(card.get("status")).upper() or "UNKNOWN"
        account_status = as_text(account.get("status")).upper() if account else "UNKNOWN"
        item_warnings = []
        limit = money(card.get("daily_atm_limit"))
        used_field = money(card.get("daily_atm_used"))
        usage_source = None
        used = None
        if used_field is not None and used_field >= 0:
            used, usage_source = used_field, "card.daily_atm_used"
        elif card_id in tx_used:
            used, usage_source = tx_used[card_id], "same-day card-tagged transaction history"
        elif account_id in unassigned_atm_by_account:
            item_warnings.append("same-day ATM withdrawals exist only at account level; do not assign them to this card")
        else:
            item_warnings.append("no card-specific daily ATM usage is available")

        requested = attempt_by_card.get(card_id)
        remaining = max(0.0, limit - used) if limit is not None and used is not None else None
        alert_active = true(card.get("fraud_alert_active"))
        alert_source = as_text(card.get("alert_source")).lower()
        velocity = true(card.get("velocity_blocked"))
        pin_locked = true(card.get("pin_locked"))

        if card_status == "FROZEN":
            next_step = "ask_verified_owner_whether_to_unfreeze"
        elif card_status in ("CLOSED", "PENDING"):
            next_step = "resolve_card_status_before_limit_or_retry_analysis"
        elif card_status != "ACTIVE":
            next_step = "confirm_unknown_card_status_before_any_action"
        elif account is None:
            next_step = "retrieve_and_confirm_linked_checking_account_status"
        elif account_status != "OPEN":
            next_step = "account_restriction_or_nonopen_status_no_transaction_action"
        elif alert_active and alert_source == "bank_initiated":
            next_step = "security_transfer_do_not_clear_bank_initiated_alert"
        elif alert_active and alert_source == "customer_initiated":
            next_step = "after_identity_and_legitimacy_confirmation_may_clear_customer_alert"
        elif alert_active:
            next_step = "alert_source_unknown_do_not_clear_until_resolved"
        elif velocity:
            next_step = "offer_wait_or_verified_early_velocity_clear"
        elif pin_locked:
            next_step = "complete_pin_lock_fraud_risk_assessment_before_unlock"
        elif requested is not None and remaining is not None and requested > remaining:
            next_step = "requested_amount_exceeds_reliable_remaining_atm_limit"
        else:
            next_step = "review_available_balance_pending_activity_and_terminal_conditions"

        result = {
            "card_id": card_id,
            "account_id": account_id or None,
            "card_status": card_status,
            "account_status": account_status,
            "requested_amount": requested,
            "daily_atm_limit": limit,
            "daily_atm_used": used,
            "usage_source": usage_source,
            "remaining_atm_limit": remaining,
            "fraud_alert_active": alert_active,
            "alert_source": alert_source or None,
            "velocity_blocked": velocity,
            "pin_locked": pin_locked,
            "preliminary_next_step": next_step,
            "warnings": item_warnings,
        }
        results.append(result)

    if not attempts:
        warnings.append("no attempts supplied; card results do not compare requested amounts")
    emit({"current_date": today, "errors": errors, "warnings": warnings, "cards": results})


if __name__ == "__main__":
    main()
