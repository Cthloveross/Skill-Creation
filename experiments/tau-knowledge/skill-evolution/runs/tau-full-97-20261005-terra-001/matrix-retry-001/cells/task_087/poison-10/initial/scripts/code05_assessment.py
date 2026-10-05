#!/usr/bin/env python3
"""Read-only CODE 05 assessment helper.

Input: JSON object described in SKILL.md on stdin.
Output: JSON object.  This helper does not execute banking actions.
"""
import json
import sys


def result(valid, stage, finding, customer_message, required_next, permitted_action="none", errors=None):
    output = {
        "valid": valid,
        "stage": stage,
        "finding": finding,
        "customer_message": customer_message,
        "required_next": required_next,
        "permitted_action": permitted_action,
    }
    if errors:
        output["errors"] = errors
    return output


def bool_field(obj, name):
    if name not in obj or not isinstance(obj[name], bool):
        return None
    return obj[name]


def main(payload):
    if not isinstance(payload, dict):
        return result(False, "input", "invalid_input", "", ["Supply a JSON object."], errors=["root must be an object"])
    card = payload.get("card")
    account = payload.get("account")
    if not isinstance(card, dict) or not isinstance(account, dict):
        return result(False, "input", "missing_records", "", ["Supply card and account objects from actual lookups."], errors=["card and account must be objects"])

    card_account_id = card.get("account_id")
    account_id = account.get("account_id")
    if not card_account_id or not account_id or card_account_id != account_id:
        return result(False, "input", "card_account_mismatch", "", ["Confirm the selected card is linked to the selected checking account."], errors=["card.account_id must equal account.account_id"])

    status = card.get("status")
    if not isinstance(status, str):
        return result(False, "card_status", "missing_card_status", "", ["Retrieve a complete debit-card lookup before proceeding."], "obtain_data")
    status = status.upper()
    if status == "FROZEN":
        return result(True, "card_status", "card_frozen", "Your card is currently frozen.", ["Ask whether the customer wants to unfreeze it.", "Before unfreezing, verify identity, ownership, linked account OPEN status, and customer confirmation."])
    if status == "CLOSED":
        return result(True, "card_status", "card_closed", "This card is no longer active.", ["Check for another active card or an approved replacement workflow."])
    if status == "PENDING":
        return result(True, "card_status", "card_pending_activation", "This card has not yet been activated.", ["Use the approved activation procedure if available."])
    if status != "ACTIVE":
        return result(False, "card_status", "unrecognized_card_status", "", ["Obtain a complete card lookup; do not infer card usability."], "obtain_data")

    account_status = account.get("status")
    if not isinstance(account_status, str):
        return result(False, "account_status", "missing_account_status", "", ["Retrieve the linked checking-account status."], "obtain_data")
    if account_status.upper() != "OPEN":
        return result(True, "account_status", "linked_account_not_open", "Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.", ["Do not perform transaction-enabling card actions on this account."])

    fraud_active = bool_field(card, "fraud_alert_active")
    if fraud_active is None:
        return result(False, "fraud_alert", "missing_fraud_alert_state", "", ["Retrieve fraud-alert status and source; do not assume no alert."], "obtain_data")
    if fraud_active:
        source = card.get("alert_source")
        if source == "bank_initiated":
            return result(True, "fraud_alert", "bank_initiated_fraud_alert", "I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.", ["Transfer to the security team.", "Do not clear the alert."], "transfer_security")
        if source == "customer_initiated":
            verified = payload.get("identity_verified") is True
            legitimate = payload.get("transactions_confirmed_legitimate") is True
            if verified and legitimate:
                return result(True, "fraud_alert", "customer_initiated_alert_ready", "", ["Obtain explicit consent and use the approved clear-alert workflow with reason customer_verified.", "Document why the alert was cleared."], "clear_customer_fraud_alert")
            missing = []
            if not verified:
                missing.append("Complete logged identity verification.")
            if not legitimate:
                missing.append("Ask the customer to confirm recent transactions are legitimate.")
            return result(True, "fraud_alert", "customer_initiated_fraud_alert", "", missing + ["Do not clear the alert until every prerequisite is met."])
        return result(False, "fraud_alert", "unknown_fraud_alert_source", "", ["Obtain the alert source; do not clear an alert with an unknown source."], "obtain_data")

    velocity_blocked = bool_field(card, "velocity_blocked")
    if velocity_blocked is None:
        return result(False, "velocity_block", "missing_velocity_state", "", ["Retrieve velocity-block status; do not assume there is no block."], "obtain_data")
    if velocity_blocked:
        verified = payload.get("identity_verified") is True
        explanation = payload.get("reasonable_velocity_explanation") is True
        message = "Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?"
        if verified and explanation:
            return result(True, "velocity_block", "velocity_block_ready", message, ["Obtain explicit consent and use the approved clear-alert workflow with reason velocity_clear.", "Document why the block was cleared."], "clear_velocity_block")
        missing = []
        if not verified:
            missing.append("Complete logged identity verification.")
        if not explanation:
            missing.append("Obtain a reasonable explanation for the unusual activity.")
        return result(True, "velocity_block", "velocity_blocked", message, missing + ["The block otherwise lifts automatically after 30 minutes."])

    return result(True, "complete", "no_code05_status_account_alert_or_velocity_issue_found", "", ["Record the decline details and investigate persistent failures using logs and exact workflow information."])


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        print(json.dumps(main(payload), separators=(",", ":")))
    except json.JSONDecodeError as exc:
        print(json.dumps(result(False, "input", "invalid_json", "", ["Provide valid JSON on stdin."], errors=[str(exc)]), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps(result(False, "internal", "assessment_error", "", ["Review the supplied lookup data."], errors=[str(exc)]), separators=(",", ":")))
