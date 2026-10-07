#!/usr/bin/env python3
"""Build a conservative, non-executing debit-card freeze plan from JSON input."""
import json
import sys


def norm(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.casefold().split())


def account_labels(account):
    fields = ("label", "account_name", "account_nickname", "display_name", "name", "account_class", "level")
    return {norm(account.get(field)) for field in fields if norm(account.get(field))}


def is_checking(account):
    values = [norm(account.get("account_type")), norm(account.get("account_class")), norm(account.get("class"))]
    return any("checking" in value for value in values)


def main(payload):
    user_id = payload.get("user_id")
    labels = payload.get("requested_account_labels")
    accounts = payload.get("accounts")
    cards_by_account = payload.get("cards_by_account")
    result = {"freeze_actions": [], "not_actionable": []}

    if not isinstance(user_id, str) or not user_id:
        return {"freeze_actions": [], "not_actionable": [{"reason": "missing_verified_user_id"}]}
    if not isinstance(labels, list) or not labels:
        return {"freeze_actions": [], "not_actionable": [{"reason": "missing_requested_account_labels"}]}
    if not isinstance(accounts, list) or not isinstance(cards_by_account, dict):
        return {"freeze_actions": [], "not_actionable": [{"reason": "invalid_accounts_or_cards_by_account"}]}

    chosen_ids = set()
    for raw_label in labels:
        label = norm(raw_label)
        if not label:
            result["not_actionable"].append({"requested_label": raw_label, "reason": "blank_requested_account_label"})
            continue
        matches = [a for a in accounts if isinstance(a, dict) and label in account_labels(a)]
        checking_matches = [a for a in matches if is_checking(a)]
        if len(checking_matches) != 1:
            reason = "requested_account_not_found" if not checking_matches else "requested_account_ambiguous"
            result["not_actionable"].append({"requested_label": raw_label, "reason": reason})
            continue
        account = checking_matches[0]
        account_id = account.get("account_id")
        if not isinstance(account_id, str) or not account_id:
            result["not_actionable"].append({"requested_label": raw_label, "reason": "matched_account_missing_id"})
            continue
        for card in cards_by_account.get(account_id, []):
            if not isinstance(card, dict):
                result["not_actionable"].append({"account_id": account_id, "reason": "malformed_card_record"})
                continue
            card_id = card.get("card_id")
            if not isinstance(card_id, str) or not card_id:
                result["not_actionable"].append({"account_id": account_id, "reason": "card_missing_id"})
                continue
            if card_id in chosen_ids:
                continue
            if card.get("account_id") != account_id:
                result["not_actionable"].append({"card_id": card_id, "reason": "card_account_mismatch"})
            elif card.get("user_id") != user_id:
                result["not_actionable"].append({"card_id": card_id, "reason": "card_not_owned_by_verified_user"})
            elif card.get("status") != "ACTIVE":
                result["not_actionable"].append({"card_id": card_id, "reason": "card_not_active", "status": card.get("status")})
            else:
                chosen_ids.add(card_id)
                result["freeze_actions"].append({
                    "card_id": card_id,
                    "account_id": account_id,
                    "requested_label": raw_label,
                    "card_number_last_4": card.get("card_number_last_4"),
                    "status": "ACTIVE"
                })
    return result


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(data), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"freeze_actions": [], "not_actionable": [{"reason": "invalid_input", "detail": str(exc)}]}, separators=(",", ":")))
        sys.exit(2)
