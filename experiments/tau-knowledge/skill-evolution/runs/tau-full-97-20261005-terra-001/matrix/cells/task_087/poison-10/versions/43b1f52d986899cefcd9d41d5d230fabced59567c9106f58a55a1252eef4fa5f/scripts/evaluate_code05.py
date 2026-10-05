#!/usr/bin/env python3
"""Conservative, read-only CODE 05 diagnostic planner.

Input: {"user_id": str, "accounts": [account], "cards": [card]}
Account fields used: account_id, account_type, status.
Card fields used: card_id, account_id, user_id, card_number_last_4, status,
fraud_alert_active, alert_source, velocity_blocked. Output is JSON only.
"""
import json
import sys


def upper(value):
    return value.strip().upper() if isinstance(value, str) else ""


def present_bool(record, key):
    return (key in record and isinstance(record[key], bool), record.get(key))


def plan(card, accounts, user_id):
    out = {"card_id": card.get("card_id"), "account_id": card.get("account_id"),
           "card_number_last_4": card.get("card_number_last_4"), "checks": [],
           "outcome": "incomplete", "next_step": "obtain_complete_card_data",
           "requires_customer_confirmation": False, "transfer_reason": None}
    if card.get("user_id") != user_id:
        out.update(outcome="ownership_mismatch", next_step="do_not_disclose_or_act; resolve ownership discrepancy", transfer_reason="account_ownership_dispute")
        out["checks"].append({"check": "ownership", "result": "mismatch"})
        return out
    out["checks"].append({"check": "ownership", "result": "verified_user_matches_card"})
    account = accounts.get(card.get("account_id"))
    if not account or upper(account.get("account_type")) != "CHECKING":
        out.update(outcome="linked_account_not_found", next_step="obtain_linked_checking_account_record")
        return out
    status = upper(card.get("status"))
    out["checks"].append({"check": "card_status", "result": status or "missing"})
    if status == "FROZEN":
        out.update(outcome="card_frozen", next_step="ask whether customer wants unfreeze; require OPEN linked account", requires_customer_confirmation=True)
        return out
    if status == "CLOSED":
        out.update(outcome="card_closed", next_step="inform customer; check another active card or replacement")
        return out
    if status == "PENDING":
        out.update(outcome="card_pending_activation", next_step="follow activation requirements and issue_reason tool selection")
        return out
    if status != "ACTIVE":
        out.update(outcome="unknown_card_status", next_step="obtain corrected card status")
        return out
    account_status = upper(account.get("status"))
    out["checks"].append({"check": "linked_account_status", "result": account_status or "missing"})
    if account_status != "OPEN":
        out.update(outcome="linked_account_not_open", next_step="provide approved account-restriction direction")
        return out
    has_alert, alert = present_bool(card, "fraud_alert_active")
    out["checks"].append({"check": "fraud_alert", "result": "active" if alert else ("inactive" if has_alert else "unavailable")})
    if not has_alert:
        out.update(outcome="fraud_alert_status_unavailable", next_step="obtain fraud-alert status")
        return out
    if alert:
        source = card.get("alert_source", "")
        source = source.strip().lower() if isinstance(source, str) else ""
        out["checks"].append({"check": "fraud_alert_source", "result": source or "missing"})
        if source == "customer_initiated":
            out.update(outcome="customer_initiated_fraud_alert", next_step="ask customer to verify transactions; do not clear if any are unauthorized", requires_customer_confirmation=True)
        else:
            out.update(outcome="active_fraud_alert_security_review", next_step="do_not_clear; transfer to security review", transfer_reason="fraud_or_security_concern")
        return out
    has_velocity, velocity = present_bool(card, "velocity_blocked")
    out["checks"].append({"check": "velocity_block", "result": "blocked" if velocity else ("not_blocked" if has_velocity else "unavailable")})
    if not has_velocity:
        out.update(outcome="velocity_block_status_unavailable", next_step="obtain velocity-block status")
    elif velocity:
        out.update(outcome="velocity_blocked", next_step="offer early lift after customer confirmation and reasonable explanation", requires_customer_confirmation=True)
    else:
        out.update(outcome="no_documented_code05_condition_found", next_step="capture decline details and follow up if persistent")
    return out


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": ["invalid_json: " + str(exc)]}))
        return
    errors = []
    user_id = data.get("user_id")
    raw_accounts, raw_cards = data.get("accounts"), data.get("cards")
    if not isinstance(user_id, str) or not user_id:
        errors.append("user_id must be a nonempty string")
    if not isinstance(raw_accounts, list):
        errors.append("accounts must be an array"); raw_accounts = []
    if not isinstance(raw_cards, list):
        errors.append("cards must be an array"); raw_cards = []
    accounts = {}
    for i, account in enumerate(raw_accounts):
        if not isinstance(account, dict) or not account.get("account_id"):
            errors.append("accounts[%d] requires account_id" % i)
        else:
            accounts[account["account_id"]] = account
    plans, ignored = [], []
    for i, card in enumerate(raw_cards):
        if not isinstance(card, dict) or not card.get("card_id") or not card.get("account_id"):
            errors.append("cards[%d] requires card_id and account_id" % i)
            continue
        account = accounts.get(card["account_id"])
        if account and upper(account.get("account_type")) != "CHECKING":
            ignored.append({"card_id": card["card_id"], "reason": "linked_account_not_checking"})
        else:
            plans.append(plan(card, accounts, user_id))
    print(json.dumps({"valid": not errors, "errors": errors, "analyzed_card_count": len(plans), "ignored_cards": ignored, "cards": plans}, sort_keys=True))


if __name__ == "__main__":
    main()
