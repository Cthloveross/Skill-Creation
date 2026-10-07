#!/usr/bin/env python3
"""Check that every currently selected dispute has a confirmed successful filing.

Input JSON: {"selected_transaction_ids": [str, ...],
             "filings": [{"transaction_id": str, "success": bool}, ...]}
Output JSON has ok, missing_or_unsuccessful, duplicate_selected_ids, and
invalid_filings. The script performs no bank action.
"""
import json
import sys


def main(data):
    if not isinstance(data, dict):
        return {"ok": False, "missing_or_unsuccessful": [], "duplicate_selected_ids": [], "invalid_filings": ["input must be an object"]}
    selected = data.get("selected_transaction_ids")
    filings = data.get("filings")
    invalid = []
    if not isinstance(selected, list) or not selected:
        invalid.append("selected_transaction_ids must be a nonempty list")
        selected = []
    if not isinstance(filings, list):
        invalid.append("filings must be a list")
        filings = []

    seen = set()
    duplicates = []
    ordered = []
    for transaction_id in selected:
        if not isinstance(transaction_id, str) or not transaction_id.strip():
            invalid.append("each selected transaction ID must be a nonempty string")
            continue
        if transaction_id in seen:
            duplicates.append(transaction_id)
        else:
            seen.add(transaction_id)
            ordered.append(transaction_id)

    successful = set()
    for filing in filings:
        if not isinstance(filing, dict):
            invalid.append("each filing must be an object")
            continue
        transaction_id = filing.get("transaction_id")
        success = filing.get("success")
        if not isinstance(transaction_id, str) or not transaction_id.strip() or not isinstance(success, bool):
            invalid.append("each filing requires nonempty transaction_id and boolean success")
            continue
        if success:
            successful.add(transaction_id)

    missing = [transaction_id for transaction_id in ordered if transaction_id not in successful]
    return {
        "ok": not invalid and not duplicates and not missing,
        "missing_or_unsuccessful": missing,
        "duplicate_selected_ids": duplicates,
        "invalid_filings": invalid,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "missing_or_unsuccessful": [], "duplicate_selected_ids": [], "invalid_filings": [str(exc)]}, separators=(",", ":")))
