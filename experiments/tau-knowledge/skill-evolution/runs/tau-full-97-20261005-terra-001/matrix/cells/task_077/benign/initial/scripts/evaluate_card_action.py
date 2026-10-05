#!/usr/bin/env python3
"""Validate normalized debit-card lookup data for a requested freeze or unfreeze.

Input JSON:
{
  "action": "freeze" | "unfreeze",
  "verified_user_id": string,
  "requested_account_ids": [string],
  "all_checking_accounts_requested": boolean (optional),
  "accounts": [{"account_id": string, "account_type": string, "status": string, ...}],
  "cards_by_account": {account_id: [
    {"card_id": string, "account_id": string, "user_id": string,
     "status": string, "card_number_last_4": string, ...}
  ]}
}

Output JSON contains:
- ok: true when at least one card is eligible
- eligible_cards: normalized action candidates
- rejected_cards: cards/accounts excluded with machine-readable reasons
- errors: malformed or insufficient-request errors

This helper is deliberately read-only. The executor must live-recheck card status before
calling the relevant banking tool.
"""

import json
import sys
from typing import Any, Dict, List


def normalized(value: Any) -> str:
    return str(value or "").strip().upper()


def card_summary(card: Dict[str, Any], account_id: str, reason: str) -> Dict[str, Any]:
    return {
        "card_id": card.get("card_id"),
        "account_id": card.get("account_id") or account_id,
        "card_number_last_4": card.get("card_number_last_4"),
        "observed_status": card.get("status"),
        "reason": reason,
    }


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = str(payload.get("action", "")).strip().lower()
    verified_user_id = str(payload.get("verified_user_id", "")).strip()
    accounts = payload.get("accounts", [])
    cards_by_account = payload.get("cards_by_account", {})
    requested_ids = payload.get("requested_account_ids", [])
    all_checking = payload.get("all_checking_accounts_requested", False)

    errors: List[str] = []
    eligible: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    if action not in {"freeze", "unfreeze"}:
        errors.append("action must be 'freeze' or 'unfreeze'")
    if not verified_user_id:
        errors.append("verified_user_id is required; do not use this helper before verification")
    if not isinstance(accounts, list):
        errors.append("accounts must be an array")
        accounts = []
    if not isinstance(cards_by_account, dict):
        errors.append("cards_by_account must be an object keyed by account_id")
        cards_by_account = {}
    if not isinstance(requested_ids, list):
        errors.append("requested_account_ids must be an array")
        requested_ids = []

    account_index = {
        str(a.get("account_id")): a
        for a in accounts
        if isinstance(a, dict) and a.get("account_id") is not None
    }

    if all_checking:
        target_ids = [
            account_id for account_id, account in account_index.items()
            if normalized(account.get("account_type")) == "CHECKING"
        ]
    else:
        target_ids = [str(x) for x in requested_ids if str(x).strip()]
        if not target_ids:
            errors.append(
                "Specify requested_account_ids, or set all_checking_accounts_requested only when the customer explicitly requested all debit cards"
            )

    required_status = "ACTIVE" if action == "freeze" else "FROZEN"

    for account_id in target_ids:
        account = account_index.get(account_id)
        if account is None:
            rejected.append({
                "card_id": None,
                "account_id": account_id,
                "card_number_last_4": None,
                "observed_status": None,
                "reason": "account_not_found",
            })
            continue
        if normalized(account.get("account_type")) != "CHECKING":
            rejected.append({
                "card_id": None,
                "account_id": account_id,
                "card_number_last_4": None,
                "observed_status": account.get("status"),
                "reason": "not_a_checking_account",
            })
            continue

        cards = cards_by_account.get(account_id, [])
        if not isinstance(cards, list) or not cards:
            rejected.append({
                "card_id": None,
                "account_id": account_id,
                "card_number_last_4": None,
                "observed_status": None,
                "reason": "no_debit_cards_returned",
            })
            continue

        for card in cards:
            if not isinstance(card, dict):
                rejected.append({
                    "card_id": None,
                    "account_id": account_id,
                    "card_number_last_4": None,
                    "observed_status": None,
                    "reason": "malformed_card_record",
                })
                continue
            if not card.get("card_id"):
                rejected.append(card_summary(card, account_id, "missing_card_id"))
                continue
            if str(card.get("account_id") or account_id) != account_id:
                rejected.append(card_summary(card, account_id, "card_account_mismatch"))
                continue
            if str(card.get("user_id", "")) != verified_user_id:
                rejected.append(card_summary(card, account_id, "card_not_owned_by_verified_customer"))
                continue
            if normalized(card.get("status")) != required_status:
                rejected.append(card_summary(card, account_id, "card_not_in_required_status_" + required_status.lower()))
                continue
            if action == "unfreeze" and normalized(account.get("status")) != "OPEN":
                rejected.append(card_summary(card, account_id, "linked_checking_account_not_open"))
                continue
            eligible.append({
                "card_id": card["card_id"],
                "account_id": account_id,
                "card_number_last_4": card.get("card_number_last_4"),
                "observed_status": card.get("status"),
                "required_status": required_status,
                "recommended_action": action,
            })

    return {
        "ok": not errors and bool(eligible),
        "action": action,
        "required_card_status": required_status if action in {"freeze", "unfreeze"} else None,
        "eligible_cards": eligible,
        "rejected_cards": rejected,
        "errors": errors,
        "live_recheck_required": True,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON must be an object")
        result = main(raw)
    except Exception as exc:
        result = {
            "ok": False,
            "eligible_cards": [],
            "rejected_cards": [],
            "errors": ["invalid_input: " + str(exc)],
            "live_recheck_required": True,
        }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
