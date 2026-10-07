#!/usr/bin/env python3
"""Classify whether a requested card type exists in supplied account records.

Reads one JSON object from stdin and writes one JSON object to stdout.
No network, filesystem, or banking-tool access is performed.
"""

import json
import sys
from typing import Any, Dict, List


def normalize_label(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).casefold()


def error(message: str) -> Dict[str, Any]:
    return {"status": "error", "error": message}


def safe_account(account: Dict[str, Any]) -> Dict[str, Any]:
    """Return only fields useful for a later verified response or disambiguation."""
    result: Dict[str, Any] = {
        "account_id": account["account_id"],
        "card_type": account["card_type"],
    }
    if "current_balance" in account:
        result["current_balance"] = account["current_balance"]
    if "date_of_account_open" in account:
        result["date_of_account_open"] = account["date_of_account_open"]
    return result


def reconcile(payload: Dict[str, Any]) -> Dict[str, Any]:
    requested = payload.get("requested_card_type")
    user_id = payload.get("resolved_user_id")
    alternate_id = payload.get("alternate_lookup_user_id")
    accounts = payload.get("accounts")

    if not isinstance(requested, str) or not normalize_label(requested):
        return error("requested_card_type must be a nonempty string")
    if not isinstance(user_id, str) or not user_id.strip():
        return error("resolved_user_id must be a nonempty string")
    if alternate_id is not None and (not isinstance(alternate_id, str) or not alternate_id.strip()):
        return error("alternate_lookup_user_id must be a nonempty string or null")
    if not isinstance(accounts, list):
        return error("accounts must be an array")

    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            return error(f"accounts[{index}] must be an object")
        for field in ("account_id", "user_id", "card_type"):
            if not isinstance(account.get(field), str) or not account[field].strip():
                return error(f"accounts[{index}].{field} must be a nonempty string")
        if account["user_id"] != user_id:
            return error("account data includes an account for a different user")

    if alternate_id is None:
        consistency = "not_checked"
    elif alternate_id == user_id:
        consistency = "same_user"
    else:
        consistency = "different_user"

    target = normalize_label(requested)
    matches: List[Dict[str, Any]] = [
        account for account in accounts if normalize_label(account["card_type"]) == target
    ]
    listed_types = sorted({account["card_type"] for account in accounts}, key=normalize_label)

    if len(matches) == 0:
        match_status = "not_found"
    elif len(matches) == 1:
        match_status = "found"
    else:
        match_status = "ambiguous"

    return {
        "status": "ok",
        "lookup_consistency": consistency,
        "match_status": match_status,
        "requested_card_type": " ".join(requested.split()),
        "matching_accounts": [safe_account(account) for account in matches],
        "listed_card_types": listed_types,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        json.dump(error(f"invalid JSON input: {exc.msg}"), sys.stdout)
        sys.stdout.write("\n")
        return
    if not isinstance(payload, dict):
        json.dump(error("input must be a JSON object"), sys.stdout)
        sys.stdout.write("\n")
        return
    json.dump(reconcile(payload), sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
