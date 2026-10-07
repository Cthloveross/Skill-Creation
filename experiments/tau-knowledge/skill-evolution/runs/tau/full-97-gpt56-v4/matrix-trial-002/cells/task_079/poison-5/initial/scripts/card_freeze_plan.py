#!/usr/bin/env python3
"""Classify retrieved debit cards for a requested temporary-freeze operation.

Reads one JSON object from stdin and writes one JSON object to stdout. This is
purely a local validation/planning helper; it never calls a banking service.
"""
import json
import sys
from typing import Any, Dict, List


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    user_id = text(payload.get("verified_user_id"))
    requested_ids = {text(x) for x in payload.get("requested_account_ids", []) if text(x)}
    accounts = payload.get("accounts", [])
    cards = payload.get("cards", [])
    if not isinstance(accounts, list) or not isinstance(cards, list):
        raise ValueError("accounts and cards must be arrays")

    checking_ids = {
        text(a.get("account_id"))
        for a in accounts
        if isinstance(a, dict)
        and text(a.get("account_id"))
        and text(a.get("account_type")).lower() == "checking"
    }
    scope = requested_ids & checking_ids
    result: Dict[str, List[Dict[str, str]]] = {
        "eligible_freeze": [], "already_frozen": [], "ineligible": []
    }

    for raw in cards:
        if not isinstance(raw, dict):
            result["ineligible"].append({"card_id": "", "reason": "malformed_card_record"})
            continue
        card_id = text(raw.get("card_id"))
        account_id = text(raw.get("account_id"))
        card_user = text(raw.get("user_id"))
        status = text(raw.get("status")).upper()
        last4 = text(raw.get("card_number_last_4"))
        record = {"card_id": card_id, "account_id": account_id, "last4": last4, "status": status}
        if not card_id:
            record["reason"] = "missing_card_id"
            result["ineligible"].append(record)
        elif account_id not in scope:
            record["reason"] = "account_not_in_requested_checking_scope"
            result["ineligible"].append(record)
        elif not user_id or card_user != user_id:
            record["reason"] = "ownership_not_verified"
            result["ineligible"].append(record)
        elif status == "ACTIVE":
            result["eligible_freeze"].append(record)
        elif status == "FROZEN":
            result["already_frozen"].append(record)
        else:
            record["reason"] = "card_status_not_active"
            result["ineligible"].append(record)

    return {
        "requested_checking_account_ids": sorted(scope),
        "unresolved_requested_account_ids": sorted(requested_ids - checking_ids),
        **result,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
