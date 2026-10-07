#!/usr/bin/env python3
"""Produce a non-executing CODE 05 disposition from runtime lookup facts.

Reads a JSON object from stdin and writes a JSON object to stdout. This helper
never calls banking tools and must not be treated as authority to alter a card.
"""
import json
import sys


def emit(checks, outcome, message, action):
    return {
        "checks_completed_in_order": checks,
        "outcome": outcome,
        "customer_message": message,
        "permitted_next_action": action,
    }


def required(data, name):
    return name in data and data[name] is not None


def plan(data):
    status = data.get("card_status")
    if not isinstance(status, str) or not status:
        return emit([], "needs_input", "Obtain the selected card's status first.", "look_up_card_status")
    status = status.upper()
    checks = ["card_status"]

    if status == "FROZEN":
        return emit(checks, "frozen_card", "The card is temporarily frozen.", "ask_whether_customer_wants_unfreeze")
    if status == "CLOSED":
        return emit(checks, "closed_card", "The card is no longer active.", "check_for_active_or_pending_replacement")
    if status == "PENDING":
        return emit(checks, "pending_card", "The card has not yet been activated.", "offer_activation_path_if_requested")
    if status != "ACTIVE":
        return emit(checks, "unknown_card_status", "The card status needs investigation.", "confirm_card_status")

    if not required(data, "account_status"):
        return emit(checks, "needs_input", "Check the linked checking account status next.", "look_up_linked_account_status")
    checks.append("linked_account_status")
    if str(data["account_status"]).upper() != "OPEN":
        return emit(
            checks,
            "account_not_open",
            "Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.",
            "do_not_disclose_specific_restriction_or_clear_security_controls",
        )

    if not required(data, "fraud_alert_active"):
        return emit(checks, "needs_input", "Check fraud-alert status next.", "look_up_fraud_alert_status")
    checks.append("fraud_alert_status")
    if bool(data["fraud_alert_active"]):
        source = data.get("alert_source")
        if source == "bank_initiated":
            return emit(
                checks,
                "bank_initiated_fraud_alert",
                "I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.",
                "transfer_to_human_agents:fraud_or_security_concern",
            )
        if source == "customer_initiated":
            if not data.get("identity_verified"):
                return emit(checks, "verification_required", "Identity verification is required before clearing the alert.", "verify_identity_and_log_verification")
            legitimacy = data.get("customer_confirms_transactions_legitimate")
            if legitimacy is False:
                return emit(
                    checks,
                    "reported_unrecognized_transaction",
                    "The customer reported an unfamiliar or unauthorized transaction; the alert must remain in place.",
                    "transfer_to_human_agents:fraud_or_security_concern",
                )
            if legitimacy is not True:
                return emit(checks, "legitimacy_confirmation_required", "Ask the customer to verify recent transactions and confirm they are legitimate.", "obtain_legitimacy_confirmation")
            if data.get("customer_consents_to_clear") is not True:
                return emit(checks, "consent_required", "Ask whether the customer wants the verified alert cleared.", "obtain_clear_consent")
            return emit(checks, "clear_customer_alert_allowed", "The verified customer confirmed legitimate transactions.", "clear_debit_card_fraud_alert_4892:customer_verified")
        return emit(checks, "unknown_fraud_alert_source", "The fraud-alert source must be confirmed before any action.", "confirm_alert_source_or_escalate")

    if not required(data, "velocity_blocked"):
        return emit(checks, "needs_input", "Check velocity-block status last.", "look_up_velocity_block_status")
    checks.append("velocity_block_status")
    if not bool(data["velocity_blocked"]):
        return emit(checks, "no_security_block_found", "No fraud alert or velocity block was found in this required sequence.", "continue_transaction_investigation_without_claiming_a_cause")
    if not data.get("identity_verified"):
        return emit(checks, "verification_required", "Identity verification is required before early velocity-block clearing.", "verify_identity_and_log_verification")
    if data.get("reasonable_velocity_explanation") is not True:
        return emit(checks, "explanation_required", "The block automatically lifts after 30 minutes; obtain a reasonable explanation before early clearing.", "obtain_velocity_explanation_or_wait")
    if data.get("customer_consents_to_clear") is not True:
        return emit(checks, "consent_required", "Ask whether the customer wants the velocity block lifted early.", "obtain_clear_consent")
    return emit(checks, "clear_velocity_block_allowed", "The verified customer supplied a reasonable explanation.", "clear_debit_card_fraud_alert_4892:velocity_clear")


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(plan(data), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
