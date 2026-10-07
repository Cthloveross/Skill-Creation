#!/usr/bin/env python3
"""Produce deterministic debit-dispute intake recommendations from JSON stdin.

Input: {"issues": [issue, ...]}; see SKILL.md for fields.
Output: {"plans": [...], "has_security_concern": bool}.
This program has no network, filesystem, or bank-tool side effects.
"""
import json
import sys

KIND_CATEGORY = {
    "atm_cash": "atm_cash_discrepancy",
    "atm_deposit": "atm_deposit_not_credited",
    "duplicate": "duplicate_charge",
    "incorrect_amount": "incorrect_amount",
    "goods_not_received": "goods_services_not_received",
    "recurring_after_cancellation": "recurring_charge_after_cancellation",
}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active",
    "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active",
    "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active",
    "recurring_charge_after_cancellation": "keep_active",
}
VALID_PIN = {"yes_shared", "yes_observed", "no", "unknown"}


def category_for(issue):
    kind = issue.get("kind")
    if kind == "unauthorized":
        if issue.get("fraud_suspected") is True:
            return ("card_present_fraud" if issue.get("channel") == "physical"
                    else "card_not_present_fraud")
        return "unauthorized_transaction"
    return KIND_CATEGORY.get(kind)


def missing_fields(issue, category):
    missing = []
    for field in ("amount", "transaction_date", "discovery_date", "card_in_possession"):
        if issue.get(field) is None or issue.get(field) == "":
            missing.append(field)
    if not isinstance(issue.get("amount"), (int, float)) or isinstance(issue.get("amount"), bool):
        if "amount" not in missing:
            missing.append("amount (must be numeric)")
    elif issue["amount"] < 1:
        missing.append("amount must be at least 1.00")
    if issue.get("pin_compromised") not in VALID_PIN:
        missing.append("pin_compromised")
    if issue.get("written_statement_provided") is None:
        missing.append("written_statement_provided")
    if category in {"card_present_fraud", "card_not_present_fraud"}:
        if issue.get("channel") not in {"physical", "online_phone"}:
            missing.append("fraud channel (physical or online_phone)")
        if issue.get("amount", 0) > 500 and issue.get("police_report_filed") is None:
            missing.append("police_report_filed")
    elif category is not None and category not in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
        if issue.get("merchant_contacted") is None:
            missing.append("merchant_contacted")
    if category == "atm_cash_discrepancy":
        for field in ("atm_owner", "requested_amount", "cash_received"):
            if issue.get(field) is None:
                missing.append(field)
    return missing


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid JSON: " + str(exc)}))
        return 2
    issues = payload.get("issues")
    if not isinstance(issues, list):
        print(json.dumps({"error": "issues must be a list"}))
        return 2

    plans = []
    security = False
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            plans.append({"index": index, "category": None, "card_action": None,
                          "missing_fields": ["issue must be an object"]})
            continue
        category = category_for(issue)
        if category is None:
            missing = ["recognized kind"]
            action = None
        else:
            missing = missing_fields(issue, category)
            action = ACTIONS[category]
        is_security = (issue.get("kind") == "unauthorized" and
                       issue.get("fraud_suspected") is True) or \
                      issue.get("card_in_possession") is False
        security = security or is_security
        plans.append({
            "index": index,
            "category": category,
            "card_action": action,
            "security_escalation_indicated": is_security,
            "missing_fields": missing,
        })
    print(json.dumps({"plans": plans, "has_security_concern": security}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
