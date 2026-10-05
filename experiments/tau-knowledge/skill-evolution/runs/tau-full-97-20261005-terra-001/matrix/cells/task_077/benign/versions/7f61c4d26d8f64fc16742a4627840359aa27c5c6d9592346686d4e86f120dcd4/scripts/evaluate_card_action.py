#!/usr/bin/env python3
"""Read-only eligibility planning for normalized debit-card lookup data.

Input JSON:
{
  "action": "freeze" | "unfreeze",
  "verified_user_id": string,
  "requested_account_ids": [string],
  "all_checking_accounts_requested": boolean (optional),
  "accounts": [{"account_id": string, "account_type": string, "status": string}],
  "cards_by_account": {account_id: [{"card_id": string, "account_id": string,
    "user_id": string, "status": string, "card_number_last_4": string}]}
}

Output JSON includes eligible and rejected candidates. This script does not call tools;
the executor must recheck live state before any mutation.
"""
import json
import sys


def upper(value):
    return str(value or "").strip().upper()


def summary(card, account_id, reason):
    return {
        "card_id": card.get("card_id"),
        "account_id": card.get("account_id") or account_id,
        "card_number_last_4": card.get("card_number_last_4"),
        "observed_status": card.get("status"),
        "reason": reason,
    }


def main(payload):
    action = str(payload.get("action", "")).strip().lower()
    verified_user_id = str(payload.get("verified_user_id", "")).strip()
    accounts = payload.get("accounts", [])
    cards_by_account = payload.get("cards_by_account", {})
    requested_ids = payload.get("requested_account_ids", [])
    all_checking = payload.get("all_checking_accounts_requested", False)
    errors, eligible, rejected = [], [], []

    if action not in {"freeze", "unfreeze"}:
        errors.append("action must be 'freeze' or 'unfreeze'")
    if not verified_user_id:
        errors.append("verified_user_id is required")
    if not isinstance(accounts, list):
        errors.append("accounts must be an array")
        accounts = []
    if not isinstance(cards_by_account, dict):
        errors.append("cards_by_account must be an object")
        cards_by_account = {}
    if not isinstance(requested_ids, list):
        errors.append("requested_account_ids must be an array")
        requested_ids = []

    index = {str(a.get("account_id")): a for a in accounts
             if isinstance(a, dict) and a.get("account_id") is not None}
    if all_checking:
        targets = [aid for aid, account in index.items()
                   if upper(account.get("account_type")) == "CHECKING"]
    else:
        targets = [str(item) for item in requested_ids if str(item).strip()]
        if not targets:
            errors.append("specify requested_account_ids or explicitly request all checking accounts")

    required = "ACTIVE" if action == "freeze" else "FROZEN"
    for account_id in targets:
        account = index.get(account_id)
        if account is None:
            rejected.append({"card_id": None, "account_id": account_id,
                             "reason": "account_not_found"})
            continue
        if upper(account.get("account_type")) != "CHECKING":
            rejected.append({"card_id": None, "account_id": account_id,
                             "reason": "not_a_checking_account"})
            continue
        cards = cards_by_account.get(account_id, [])
        if not isinstance(cards, list) or not cards:
            rejected.append({"card_id": None, "account_id": account_id,
                             "reason": "no_debit_cards_returned"})
            continue
        for card in cards:
            if not isinstance(card, dict):
                rejected.append({"card_id": None, "account_id": account_id,
                                 "reason": "malformed_card_record"})
            elif not card.get("card_id"):
                rejected.append(summary(card, account_id, "missing_card_id"))
            elif str(card.get("account_id") or account_id) != account_id:
                rejected.append(summary(card, account_id, "card_account_mismatch"))
            elif str(card.get("user_id", "")) != verified_user_id:
                rejected.append(summary(card, account_id, "card_not_owned_by_verified_customer"))
            elif upper(card.get("status")) != required:
                rejected.append(summary(card, account_id,
                                        "card_not_in_required_status_" + required.lower()))
            elif action == "unfreeze" and upper(account.get("status")) != "OPEN":
                rejected.append(summary(card, account_id, "linked_checking_account_not_open"))
            else:
                eligible.append({"card_id": card["card_id"], "account_id": account_id,
                                 "card_number_last_4": card.get("card_number_last_4"),
                                 "observed_status": card.get("status"),
                                 "required_status": required,
                                 "recommended_action": action})

    return {"ok": not errors and bool(eligible), "action": action,
            "required_card_status": required if action in {"freeze", "unfreeze"} else None,
            "eligible_cards": eligible, "rejected_cards": rejected, "errors": errors,
            "live_recheck_required": True}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
        output = main(data)
    except Exception as exc:
        output = {"ok": False, "eligible_cards": [], "rejected_cards": [],
                  "errors": ["invalid_input: " + str(exc)], "live_recheck_required": True}
    print(json.dumps(output, separators=(",", ":"), sort_keys=True))
