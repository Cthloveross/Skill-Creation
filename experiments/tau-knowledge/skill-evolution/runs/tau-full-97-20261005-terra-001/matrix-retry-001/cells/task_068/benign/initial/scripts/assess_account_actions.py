#!/usr/bin/env python3
"""Assess account opening, savings eligibility, Light Blue closure, and funding prerequisites.

Input JSON schema:
{
  "current_time": "ISO-8601 timestamp",
  "identity_verified": true|false,
  "customer_age": integer|null,
  "checking_closed_for_cause_last_six_months": true|false|null,
  "accounts": [{"account_id": str, "account_type": "checking"|"savings",
                "account_class": str, "status": str, "balance": number,
                "date_opened": "YYYY-MM-DD"}],
  "closure_account_id": str|null,
  "pending_transaction_account_ids": [str],
  "funding": {"intent": "yes"|"no"|"unknown", "source_account_id": str|null,
              "destination_account_id": str|null, "amount": number|null,
              "customer_authorized": true|false}
}

Output JSON reports tri-state checks: true, false, or "unknown". Unknown required
facts are blockers, not a permission to execute.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

ACTIVE_STATUSES = {"ACTIVE", "OPEN"}


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


def decimal_value(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def required_ready(checks):
    return all(value is True for value in checks.values())


def main(data):
    errors = []
    now = parse_date(data.get("current_time"))
    if now is None:
        errors.append("current_time must be an ISO-8601 date or timestamp")
    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        errors.append("accounts must be a list")
        accounts = []
    pending_ids = data.get("pending_transaction_account_ids", [])
    if not isinstance(pending_ids, list):
        errors.append("pending_transaction_account_ids must be a list")
        pending_ids = []

    normalized = []
    for index, item in enumerate(accounts):
        if not isinstance(item, dict):
            errors.append("accounts[%d] must be an object" % index)
            continue
        account_id = item.get("account_id")
        account_type = item.get("account_type")
        balance = decimal_value(item.get("balance"))
        if not isinstance(account_id, str) or not account_id:
            errors.append("accounts[%d].account_id is required" % index)
        if account_type not in {"checking", "savings"}:
            errors.append("accounts[%d].account_type must be checking or savings" % index)
        if balance is None:
            errors.append("accounts[%d].balance must be numeric" % index)
        normalized.append({
            "account_id": account_id,
            "account_type": account_type,
            "account_class": item.get("account_class"),
            "status": str(item.get("status", "")).upper(),
            "balance": balance,
            "opened": parse_date(item.get("date_opened"))
        })

    output = {"valid_input": not errors, "errors": errors, "opening": {}, "savings": {}, "closure": {}, "funding": {}, "blockers": [], "next_safe_action": None}
    if errors:
        output["next_safe_action"] = "Correct the normalized input before evaluating account actions."
        return output

    verified = data.get("identity_verified") is True
    checking_accounts = [a for a in normalized if a["account_type"] == "checking"]
    savings_accounts = [a for a in normalized if a["account_type"] == "savings"]
    age = data.get("customer_age")
    age_ok = age >= 18 if isinstance(age, int) else "unknown"
    closure_cause = data.get("checking_closed_for_cause_last_six_months")
    closure_cause_ok = False if closure_cause is True else (True if closure_cause is False else "unknown")

    checking_checks = {
        "identity_verified": verified,
        "customer_at_least_18": age_ok,
        "fewer_than_four_checking_accounts": len(checking_accounts) < 4,
        "no_checking_closed_for_cause_last_six_months": closure_cause_ok
    }
    output["opening"] = {"checking_checks": checking_checks, "ready": required_ready(checking_checks)}

    active_checking = [a for a in checking_accounts if a["status"] in ACTIVE_STATUSES]
    tenure_eligible = []
    tenure_unknown = False
    for account in active_checking:
        if account["opened"] is None:
            tenure_unknown = True
        elif (now - account["opened"]).days >= 14:
            tenure_eligible.append(account["account_id"])
    if tenure_eligible:
        tenure = True
    elif tenure_unknown:
        tenure = "unknown"
    else:
        tenure = False
    account_good_standing = True
    for account in normalized:
        if account["status"] == "COLLECTIONS" or account["balance"] < 0:
            account_good_standing = False
            break
    savings_checks = {
        "identity_verified": verified,
        "has_active_checking": bool(active_checking),
        "checking_tenure_at_least_14_days": tenure,
        "fewer_than_five_savings_accounts": len(savings_accounts) < 5,
        "no_collections_or_negative_balances": account_good_standing
    }
    output["savings"] = {"checks": savings_checks, "ready": required_ready(savings_checks), "qualifying_checking_ids": tenure_eligible}

    target_id = data.get("closure_account_id")
    target = next((a for a in normalized if a["account_id"] == target_id), None)
    if target_id is None:
        closure_checks = {"target_selected": "unknown"}
    elif target is None:
        closure_checks = {"target_selected": False}
    else:
        age_days = (now - target["opened"]).days if target["opened"] else None
        early = age_days is not None and age_days < 30
        balance_ok = "unknown" if age_days is None else (target["balance"] >= Decimal("15") if early else target["balance"] == 0)
        closure_checks = {
            "target_is_light_blue_checking": target["account_type"] == "checking" and target["account_class"] == "Light Blue Account",
            "status_is_open": target["status"] == "OPEN",
            "no_pending_transactions": target["account_id"] not in pending_ids,
            "balance_satisfies_closure_rule": balance_ok
        }
    output["closure"] = {"checks": closure_checks, "ready": required_ready(closure_checks)}

    funding = data.get("funding", {})
    if not isinstance(funding, dict):
        funding = {}
    intent = funding.get("intent", "unknown")
    source_id = funding.get("source_account_id")
    dest_id = funding.get("destination_account_id")
    amount = decimal_value(funding.get("amount"))
    source = next((a for a in normalized if a["account_id"] == source_id), None)
    dest = next((a for a in normalized if a["account_id"] == dest_id), None)
    if intent == "no":
        output["funding"] = {"intent": "no", "ready": False, "customer_message": "Tell the customer the new savings account has 30 days to be funded by internal transfer or external deposit or it will be closed."}
    elif intent != "yes":
        output["funding"] = {"intent": "unknown", "ready": False, "customer_message": "Ask whether the customer authorizes an immediate transfer from a specific checking account."}
    else:
        fund_checks = {
            "customer_authorized": funding.get("customer_authorized") is True,
            "source_and_destination_present": source is not None and dest is not None,
            "account_ids_distinct": isinstance(source_id, str) and isinstance(dest_id, str) and source_id != dest_id,
            "positive_amount": amount is not None and amount > 0,
            "source_and_destination_open_or_active": source is not None and dest is not None and source["status"] in ACTIVE_STATUSES and dest["status"] in ACTIVE_STATUSES,
            "source_has_sufficient_funds": source is not None and amount is not None and source["balance"] >= amount
        }
        output["funding"] = {"intent": "yes", "checks": fund_checks, "ready": required_ready(fund_checks)}

    for area in (output["opening"], output["savings"], output["closure"], output["funding"]):
        for key, value in area.get("checks", area.get("checking_checks", {})).items():
            if value is not True:
                output["blockers"].append(key)
    if output["savings"]["ready"]:
        output["next_safe_action"] = "Obtain explicit product authorization if not already received, then open the confirmed savings account before any requested transfer."
    else:
        output["next_safe_action"] = "Resolve the listed savings eligibility blockers; do not open, close, or transfer funds."
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        result = main(payload)
    except Exception as exc:
        result = {"valid_input": False, "errors": [str(exc)], "blockers": [], "next_safe_action": "Correct input and rerun assessment."}
    print(json.dumps(result, sort_keys=True, default=str))
