#!/usr/bin/env python3
"""Create a conservative, deterministic CODE 05 diagnostic plan.

Input JSON:
{
  "user_id": str,
  "accounts": [{"account_id": str, "account_type": str, "status": str}],
  "cards": [{"card_id": str, "account_id": str, "user_id": str,
             "card_number_last_4": str, "status": str,
             "fraud_alert_active": bool, "alert_source": str,
             "velocity_blocked": bool}]
}

Only user_id, accounts, and cards are required. Security fields are optional so
that the caller can see when the retrieved response is insufficient. Output is a
JSON object and this script never calls banking tools or changes state.
"""
import json
import sys


def norm(value):
    return value.strip().upper() if isinstance(value, str) else ""


def bool_value(record, key):
    """Return (is_present, boolean_value) without interpreting strings loosely."""
    if key not in record or not isinstance(record[key], bool):
        return False, False
    return True, record[key]


def add_check(result, name, value):
    result["checks"].append({"check": name, "result": value})


def plan_card(card, accounts, verified_user_id):
    result = {
        "card_id": card.get("card_id"),
        "card_number_last_4": card.get("card_number_last_4"),
        "account_id": card.get("account_id"),
        "checks": [],
        "outcome": "incomplete",
        "next_step": "obtain_complete_card_data",
        "requires_customer_confirmation": False,
        "transfer_reason": None,
    }
    if card.get("user_id") != verified_user_id:
        add_check(result, "ownership", "mismatch")
        result["outcome"] = "ownership_mismatch"
        result["next_step"] = "do_not_disclose_or_act; resolve ownership discrepancy"
        result["transfer_reason"] = "account_ownership_dispute"
        return result
    add_check(result, "ownership", "verified_user_matches_card")

    account = accounts.get(card.get("account_id"))
    if account is None:
        add_check(result, "linked_account", "not_found")
        result["outcome"] = "linked_account_not_found"
        result["next_step"] = "obtain_linked_checking_account_record"
        return result
    if norm(account.get("account_type")) != "CHECKING":
        add_check(result, "linked_account", "not_a_checking_account")
        result["outcome"] = "invalid_card_account_linkage"
        result["next_step"] = "do_not_act; resolve account linkage"
        return result

    status = norm(card.get("status"))
    add_check(result, "card_status", status or "missing")
    if status == "FROZEN":
        result["outcome"] = "card_frozen"
        result["next_step"] = "ask whether customer wants unfreeze; require OPEN linked account before unfreezing"
        result["requires_customer_confirmation"] = True
        return result
    if status == "CLOSED":
        result["outcome"] = "card_closed"
        result["next_step"] = "inform customer; check for another active card or discuss replacement"
        return result
    if status == "PENDING":
        result["outcome"] = "card_pending_activation"
        result["next_step"] = "follow activation requirements and select activation tool from issue_reason"
        return result
    if status != "ACTIVE":
        result["outcome"] = "unknown_card_status"
        result["next_step"] = "obtain corrected card status; do not infer a decline cause"
        return result

    account_status = norm(account.get("status"))
    add_check(result, "linked_account_status", account_status or "missing")
    if account_status != "OPEN":
        result["outcome"] = "linked_account_not_open"
        result["next_step"] = "provide approved account-restriction direction without specific restriction details"
        return result

    alert_present, alert_active = bool_value(card, "fraud_alert_active")
    add_check(result, "fraud_alert", "active" if alert_active else ("inactive" if alert_present else "unavailable"))
    if not alert_present:
        result["outcome"] = "fraud_alert_status_unavailable"
        result["next_step"] = "obtain fraud-alert status before concluding the CODE 05 review"
        return result
    if alert_active:
        source = card.get("alert_source")
        source_norm = source.strip().lower() if isinstance(source, str) else ""
        add_check(result, "fraud_alert_source", source_norm or "missing")
        if source_norm == "bank_initiated":
            result["outcome"] = "bank_initiated_fraud_alert"
            result["next_step"] = "do_not_clear; transfer to security team"
            result["transfer_reason"] = "fraud_or_security_concern"
            return result
        if source_norm == "customer_initiated":
            result["outcome"] = "customer_initiated_fraud_alert"
            result["next_step"] = "ask customer to verify recent transactions; clear only if legitimate and customer agrees"
            result["requires_customer_confirmation"] = True
            return result
        result["outcome"] = "active_fraud_alert_unknown_source"
        result["next_step"] = "do_not_clear; escalate for security review"
        result["transfer_reason"] = "fraud_or_security_concern"
        return result

    velocity_present, velocity_blocked = bool_value(card, "velocity_blocked")
    add_check(result, "velocity_block", "blocked" if velocity_blocked else ("not_blocked" if velocity_present else "unavailable"))
    if not velocity_present:
        result["outcome"] = "velocity_block_status_unavailable"
        result["next_step"] = "obtain velocity-block status before concluding the CODE 05 review"
    elif velocity_blocked:
        result["outcome"] = "velocity_blocked"
        result["next_step"] = "offer early lift; clear only after verified customer agrees and gives reasonable explanation"
        result["requires_customer_confirmation"] = True
    else:
        result["outcome"] = "no_documented_code05_condition_found"
        result["next_step"] = "capture decline details and follow up/escalate if persistent"
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": ["invalid_json: " + str(exc)]}))
        return
    errors = []
    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        errors.append("user_id must be a nonempty string")
    raw_accounts = payload.get("accounts")
    raw_cards = payload.get("cards")
    if not isinstance(raw_accounts, list):
        errors.append("accounts must be an array")
        raw_accounts = []
    if not isinstance(raw_cards, list):
        errors.append("cards must be an array")
        raw_cards = []

    accounts = {}
    for index, account in enumerate(raw_accounts):
        if not isinstance(account, dict) or not account.get("account_id"):
            errors.append("accounts[%d] requires account_id" % index)
            continue
        accounts[account["account_id"]] = account

    plans = []
    ignored = []
    for index, card in enumerate(raw_cards):
        if not isinstance(card, dict):
            errors.append("cards[%d] must be an object" % index)
            continue
        if not card.get("card_id"):
            errors.append("cards[%d] requires card_id" % index)
            continue
        if norm(card.get("account_id")) == "":
            errors.append("cards[%d] requires account_id" % index)
            continue
        # Cards tied to non-checking accounts are retained as ignored evidence,
        # rather than being presented as debit-card candidates.
        account = accounts.get(card.get("account_id"))
        if account is not None and norm(account.get("account_type")) != "CHECKING":
            ignored.append({"card_id": card.get("card_id"), "reason": "linked_account_not_checking"})
            continue
        plans.append(plan_card(card, accounts, user_id))

    output = {
        "valid": not errors,
        "errors": errors,
        "analyzed_card_count": len(plans),
        "ignored_cards": ignored,
        "cards": plans,
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
