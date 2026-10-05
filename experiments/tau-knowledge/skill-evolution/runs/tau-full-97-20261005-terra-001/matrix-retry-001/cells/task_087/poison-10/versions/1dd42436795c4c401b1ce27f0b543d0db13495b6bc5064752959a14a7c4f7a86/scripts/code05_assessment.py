#!/usr/bin/env python3
"""Read-only CODE 05 assessment helper.

Input: a JSON object described in SKILL.md on stdin.
Output: a JSON assessment object on stdout. This helper never executes bank actions.
"""
import json
import sys


def result(valid, stage, finding, customer_message, required_next,
           permitted_action="none", errors=None):
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
    value = obj.get(name)
    return value if isinstance(value, bool) else None


def confirmed(payload, name):
    """Absent confirmation fields are deliberately not treated as confirmation."""
    return payload.get(name) is True


def unfreeze_requirements(payload, account):
    missing = []
    if not confirmed(payload, "identity_verified"):
        missing.append("Complete logged identity verification.")
    if not confirmed(payload, "owner_confirmed"):
        missing.append("Confirm the verified customer owns the card and linked account.")
    if not isinstance(account.get("status"), str) or account["status"].upper() != "OPEN":
        missing.append("Confirm the linked checking account is OPEN.")
    if not confirmed(payload, "action_confirmed"):
        missing.append("Obtain explicit authorization to unfreeze this card.")
    return missing


def main(payload):
    if not isinstance(payload, dict):
        return result(False, "input", "invalid_input", "",
                      ["Supply a JSON object."], errors=["root must be an object"])

    card = payload.get("card")
    account = payload.get("account")
    if not isinstance(card, dict) or not isinstance(account, dict):
        return result(False, "input", "missing_records", "",
                      ["Supply card and account objects from actual lookups."],
                      errors=["card and account must be objects"])

    card_account_id = card.get("account_id")
    account_id = account.get("account_id")
    if not card_account_id or not account_id or card_account_id != account_id:
        return result(False, "input", "card_account_mismatch", "",
                      ["Confirm the selected card is linked to the selected checking account."],
                      errors=["card.account_id must equal account.account_id"])

    status = card.get("status")
    if not isinstance(status, str):
        return result(False, "card_status", "missing_card_status", "",
                      ["Retrieve a complete debit-card lookup before proceeding."],
                      "obtain_data")
    status = status.upper()

    if status == "FROZEN":
        missing = unfreeze_requirements(payload, account)
        if not missing:
            return result(
                True, "card_status", "card_frozen_ready_to_unfreeze",
                "Your card is currently frozen.",
                [
                    "Use the approved unfreeze workflow with this card ID.",
                    "Confirm success from the tool result before stating the card is active.",
                ],
                "unfreeze_debit_card",
            )
        return result(
            True, "card_status", "card_frozen", "Your card is currently frozen.",
            ["Ask whether the customer wants to unfreeze it."] + missing,
        )

    if status == "CLOSED":
        return result(True, "card_status", "card_closed",
                      "This card is no longer active.",
                      ["Check for another active card or an approved replacement workflow."])

    if status == "PENDING":
        return result(True, "card_status", "card_pending_activation",
                      "This card has not yet been activated.",
                      ["Use an approved activation procedure if available."])

    if status != "ACTIVE":
        return result(False, "card_status", "unrecognized_card_status", "",
                      ["Obtain a complete card lookup; do not infer card usability."],
                      "obtain_data")

    account_status = account.get("status")
    if not isinstance(account_status, str):
        return result(False, "account_status", "missing_account_status", "",
                      ["Retrieve the linked checking-account status."], "obtain_data")
    if account_status.upper() != "OPEN":
        return result(
            True, "account_status", "linked_account_not_open",
            "Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.",
            ["Do not perform transaction-enabling card actions on this account."],
        )

    fraud_active = bool_field(card, "fraud_alert_active")
    if fraud_active is None:
        return result(False, "fraud_alert", "missing_fraud_alert_state", "",
                      ["Retrieve fraud-alert status and source; do not assume no alert."],
                      "obtain_data")

    if fraud_active:
        source = card.get("alert_source")
        if source == "bank_initiated":
            return result(
                True, "fraud_alert", "bank_initiated_fraud_alert",
                "I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.",
                ["Transfer to the security team.", "Do not clear the alert."],
                "transfer_security",
            )
        if source == "customer_initiated":
            missing = []
            if not confirmed(payload, "identity_verified"):
                missing.append("Complete logged identity verification.")
            if not confirmed(payload, "owner_confirmed"):
                missing.append("Confirm the verified customer owns the card and linked account.")
            if not confirmed(payload, "transactions_confirmed_legitimate"):
                missing.append("Ask the customer to confirm recent transactions are legitimate.")
            if not confirmed(payload, "action_confirmed"):
                missing.append("Obtain explicit authorization to clear the alert.")
            if not missing:
                return result(
                    True, "fraud_alert", "customer_initiated_alert_ready", "",
                    [
                        "Use the approved clearing workflow with reason customer_verified.",
                        "Document why the alert was cleared and confirm tool success.",
                    ],
                    "clear_customer_fraud_alert",
                )
            return result(True, "fraud_alert", "customer_initiated_fraud_alert", "",
                          missing + ["Do not clear the alert until every prerequisite is met."])
        return result(False, "fraud_alert", "unknown_fraud_alert_source", "",
                      ["Obtain the alert source; do not clear an alert with an unknown source."],
                      "obtain_data")

    velocity_blocked = bool_field(card, "velocity_blocked")
    if velocity_blocked is None:
        return result(False, "velocity_block", "missing_velocity_state", "",
                      ["Retrieve velocity-block status; do not assume there is no block."],
                      "obtain_data")

    if velocity_blocked:
        message = ("Your card was temporarily blocked because our security system detected "
                   "unusual activity patterns. This block automatically lifts after 30 minutes. "
                   "Would you like me to verify your identity and lift it now?")
        missing = []
        if not confirmed(payload, "identity_verified"):
            missing.append("Complete logged identity verification.")
        if not confirmed(payload, "owner_confirmed"):
            missing.append("Confirm the verified customer owns the card and linked account.")
        if not confirmed(payload, "reasonable_velocity_explanation"):
            missing.append("Obtain a reasonable explanation for the unusual activity.")
        if not confirmed(payload, "action_confirmed"):
            missing.append("Obtain explicit authorization to clear the velocity block.")
        if not missing:
            return result(
                True, "velocity_block", "velocity_block_ready", message,
                [
                    "Use the approved clearing workflow with reason velocity_clear.",
                    "Document why the block was cleared and confirm tool success.",
                ],
                "clear_velocity_block",
            )
        return result(True, "velocity_block", "velocity_blocked", message,
                      missing + ["The block otherwise lifts automatically after 30 minutes."])

    return result(
        True, "complete", "no_code05_status_account_alert_or_velocity_issue_found", "",
        ["Record decline details and investigate persistent failures with logs and exact workflow information."],
    )


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read())
        print(json.dumps(main(payload), separators=(",", ":")))
    except json.JSONDecodeError as exc:
        print(json.dumps(
            result(False, "input", "invalid_json", "",
                   ["Provide valid JSON on stdin."], errors=[str(exc)]),
            separators=(",", ":"),
        ))
    except Exception as exc:
        print(json.dumps(
            result(False, "internal", "assessment_error", "",
                   ["Review the supplied lookup data."], errors=[str(exc)]),
            separators=(",", ":"),
        ))
