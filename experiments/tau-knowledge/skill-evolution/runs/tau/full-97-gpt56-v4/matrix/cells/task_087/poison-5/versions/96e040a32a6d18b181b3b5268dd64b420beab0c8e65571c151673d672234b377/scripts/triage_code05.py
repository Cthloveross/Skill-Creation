#!/usr/bin/env python3
"""Produce ordered, non-executing CODE 05 triage recommendations.

Reads one JSON object from stdin with:
  accounts: list of objects containing account_id and status
  cards: list of objects containing card_id, account_id, status,
         fraud_alert_active, alert_source, velocity_blocked
Writes JSON: {"triage": [ ... ]}.  No banking action is performed.
"""
import json
import sys


def normalized(value):
    return value.strip().upper() if isinstance(value, str) else None


def account_index(accounts):
    indexed = {}
    for account in accounts:
        if isinstance(account, dict) and account.get("account_id") is not None:
            indexed[str(account["account_id"])] = account
    return indexed


def triage_card(card, accounts):
    card_id = card.get("card_id")
    account_id = card.get("account_id")
    result = {
        "card_id": card_id,
        "account_id": account_id,
        "next_step": None,
        "reason": None,
        "requirements": [],
    }
    status = normalized(card.get("status"))
    if status is None:
        result.update(next_step="inspect_card_status", reason="Card status is missing.")
        return result
    if status == "FROZEN":
        result.update(
            next_step="offer_unfreeze",
            reason="Card is frozen.",
            requirements=["verified_identity", "card_owner_or_authority", "explicit_unfreeze_consent", "linked_account_OPEN"],
        )
        return result
    if status == "CLOSED":
        result.update(next_step="review_other_cards_or_replacement", reason="Card is closed and cannot be used.")
        return result
    if status == "PENDING":
        result.update(next_step="follow_activation_procedure", reason="Card is pending activation.")
        return result
    if status != "ACTIVE":
        result.update(next_step="inspect_card_status", reason="Card status is unrecognized: %s." % status)
        return result

    account = accounts.get(str(account_id))
    if account is None:
        result.update(next_step="retrieve_linked_account", reason="Linked checking account was not supplied.")
        return result
    account_status = normalized(account.get("status"))
    if account_status is None:
        result.update(next_step="inspect_account_status", reason="Linked account status is missing.")
        return result
    if account_status != "OPEN":
        result.update(next_step="account_restriction_message", reason="Linked account is not OPEN.")
        return result

    alert = card.get("fraud_alert_active")
    if alert is True:
        source = (card.get("alert_source") or "").strip().lower()
        if source == "bank_initiated":
            result.update(next_step="transfer_security", reason="Bank-initiated fraud alert must not be cleared.")
            return result
        if source == "customer_initiated":
            result.update(
                next_step="obtain_legitimacy_confirmation_then_clear_customer_alert",
                reason="Customer-initiated fraud alert is active.",
                requirements=["verified_identity", "customer_confirms_recent_transactions_legitimate"],
            )
            return result
        result.update(next_step="inspect_fraud_alert_source", reason="Active fraud alert has no recognized source.")
        return result
    if alert not in (False, None):
        result.update(next_step="inspect_fraud_alert", reason="Fraud alert state is unrecognized.")
        return result
    if alert is None:
        result.update(next_step="inspect_fraud_alert", reason="Fraud alert state is missing.")
        return result

    blocked = card.get("velocity_blocked")
    if blocked is True:
        result.update(
            next_step="offer_velocity_clear",
            reason="Velocity block is active.",
            requirements=["verified_identity", "reasonable_activity_explanation", "explicit_customer_consent"],
        )
        return result
    if blocked is False:
        result.update(next_step="collect_decline_details_and_escalate_if_repeated", reason="No CODE 05 cause found in required checks.")
        return result
    result.update(next_step="inspect_velocity_block", reason="Velocity-block state is missing or unrecognized.")
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return 2
    if not isinstance(payload, dict):
        print(json.dumps({"error": "invalid_input", "detail": "Top-level input must be an object."}))
        return 2
    accounts = payload.get("accounts", [])
    cards = payload.get("cards", [])
    if not isinstance(accounts, list) or not isinstance(cards, list) or not all(isinstance(c, dict) for c in cards):
        print(json.dumps({"error": "invalid_input", "detail": "accounts and cards must be lists of objects."}))
        return 2
    print(json.dumps({"triage": [triage_card(card, account_index(accounts)) for card in cards]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
