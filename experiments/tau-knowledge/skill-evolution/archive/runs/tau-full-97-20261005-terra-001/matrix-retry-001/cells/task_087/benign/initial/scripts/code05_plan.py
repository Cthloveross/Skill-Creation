#!/usr/bin/env python3
"""Produce a safe next-step plan for a normalized debit-card CODE 05 lookup.

Input and output are JSON objects on stdin/stdout. This script does not call tools,
change accounts, or verify identity; its `verified` input may be true only after the
caller completed two-field verification and logged it with log_verification.
"""
import json
import sys
from typing import Any, Dict, List

RESTRICTION_MESSAGE = (
    "Your account has a restriction that is preventing transactions. Please visit "
    "a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance."
)
BANK_ALERT_MESSAGE = (
    "I see there's a security flag on your account that requires additional review. "
    "I'm transferring you to our security team."
)
VELOCITY_MESSAGE = (
    "Your card was temporarily blocked because our security system detected unusual "
    "activity patterns. This block automatically lifts after 30 minutes. Would you "
    "like me to verify your identity and lift it now?"
)


def emit(**data: Any) -> None:
    print(json.dumps(data, separators=(",", ":"), sort_keys=True))


def value(obj: Dict[str, Any], key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else None


def missing_plan(stage: str, fields: List[str], message: str) -> Dict[str, Any]:
    return {
        "stage": stage,
        "next_step": "obtain_missing_data",
        "required_before_action": fields,
        "recommended_tool": None,
        "tool_arguments": None,
        "customer_message": message,
    }


def normalized_upper(item: Any) -> str:
    return item.strip().upper() if isinstance(item, str) else ""


def plan(data: Dict[str, Any]) -> Dict[str, Any]:
    card = data.get("card")
    account = data.get("account")
    if not isinstance(card, dict):
        return missing_plan(
            "card_lookup", ["selected debit-card lookup result"],
            "I need to identify the affected debit card before I can investigate this decline.",
        )

    card_id = value(card, "card_id")
    card_account_id = value(card, "account_id")
    status = normalized_upper(value(card, "status"))
    if not card_id or not card_account_id or not status:
        return missing_plan(
            "card_status", ["card_id", "linked account_id", "card status"],
            "The card lookup is incomplete, so no card action should be taken yet.",
        )

    expected_user_id = data.get("expected_user_id")
    card_user_id = value(card, "user_id")
    if expected_user_id and card_user_id and expected_user_id != card_user_id:
        return {
            "stage": "ownership_validation",
            "next_step": "transfer_to_human",
            "required_before_action": ["resolve cardholder/profile ownership mismatch"],
            "recommended_tool": "transfer_to_human_agents",
            "tool_arguments": None,
            "transfer_reason": "account_ownership_dispute",
            "customer_message": "I need to have the account ownership reviewed before any action can be taken on this card.",
        }

    verified = data.get("verified") is True

    # Card status is intentionally assessed before the general active-card account path.
    if status == "FROZEN":
        choice = data.get("wants_unfreeze")
        if choice is None:
            return {
                "stage": "card_status",
                "next_step": "ask_customer",
                "required_before_action": ["customer consent to unfreeze"],
                "recommended_tool": None,
                "tool_arguments": None,
                "customer_message": "Your card is frozen. Would you like me to unfreeze it?",
            }
        if choice is not True:
            return {
                "stage": "card_status",
                "next_step": "no_unfreeze_requested",
                "required_before_action": [],
                "recommended_tool": None,
                "tool_arguments": None,
                "customer_message": "I will leave the card frozen. Transactions will continue to be declined while it remains frozen.",
            }
        if not verified:
            return missing_plan(
                "unfreeze_verification", ["two-field identity verification and verification audit record"],
                "I can help unfreeze the card after I verify your identity.",
            )
        if not isinstance(account, dict) or value(account, "account_id") != card_account_id:
            return missing_plan(
                "unfreeze_account_check", ["linked checking account lookup"],
                "I need to confirm that the linked checking account is open before unfreezing the card.",
            )
        if normalized_upper(value(account, "status")) != "OPEN":
            return {
                "stage": "linked_account_status",
                "next_step": "do_not_unfreeze",
                "required_before_action": [],
                "recommended_tool": None,
                "tool_arguments": None,
                "customer_message": RESTRICTION_MESSAGE,
            }
        return {
            "stage": "unfreeze",
            "next_step": "unfreeze_card",
            "required_before_action": ["verified card owner", "FROZEN card", "OPEN linked checking account"],
            "recommended_tool": "unfreeze_debit_card_3893",
            "tool_arguments": {"card_id": card_id},
            "customer_message": "I can now unfreeze the card and confirm it is ready to use.",
        }

    if status == "CLOSED":
        return {
            "stage": "card_status",
            "next_step": "review_replacement_options",
            "required_before_action": ["review other cards on this checking account"],
            "recommended_tool": None,
            "tool_arguments": None,
            "customer_message": "This card is no longer active. I can check whether another card is active or pending and help with the appropriate next step.",
        }

    if status == "PENDING":
        return {
            "stage": "card_status",
            "next_step": "follow_activation_protocol",
            "required_before_action": ["verified identity", "physical card", "OPEN linked checking account", "nonexpired PENDING card", "issue reason", "card details", "compliant new PIN"],
            "recommended_tool": None,
            "tool_arguments": None,
            "customer_message": "This card is pending activation. I can help activate it using the procedure for its issue reason.",
        }

    if status != "ACTIVE":
        return {
            "stage": "card_status",
            "next_step": "investigate_data_error",
            "required_before_action": ["a valid card status from a fresh card lookup"],
            "recommended_tool": None,
            "tool_arguments": None,
            "customer_message": "The card status is unavailable or unexpected, so I need to verify the card record before taking action.",
        }

    if not isinstance(account, dict) or value(account, "account_id") != card_account_id:
        return missing_plan(
            "linked_account_status", ["linked checking account record and status"],
            "I need to check the status of the checking account linked to this active card.",
        )
    if normalized_upper(value(account, "account_type")) not in ("", "CHECKING"):
        return {
            "stage": "linked_account_status",
            "next_step": "investigate_data_error",
            "required_before_action": ["confirm a linked checking account"],
            "recommended_tool": None,
            "tool_arguments": None,
            "customer_message": "I need to verify the account linked to this debit card before proceeding.",
        }
    if normalized_upper(value(account, "status")) != "OPEN":
        return {
            "stage": "linked_account_status",
            "next_step": "stop_for_account_restriction",
            "required_before_action": [],
            "recommended_tool": None,
            "tool_arguments": None,
            "customer_message": RESTRICTION_MESSAGE,
        }

    alert_active = value(card, "fraud_alert_active")
    if not isinstance(alert_active, bool):
        return missing_plan(
            "fraud_alert", ["fraud_alert_active state from debit-card lookup"],
            "I need to confirm the card's security-alert status before proceeding.",
        )
    if alert_active:
        source = str(value(card, "alert_source") or "").strip().lower()
        if source == "bank_initiated":
            return {
                "stage": "fraud_alert",
                "next_step": "transfer_to_human",
                "required_before_action": [],
                "recommended_tool": "transfer_to_human_agents",
                "tool_arguments": None,
                "transfer_reason": "fraud_or_security_concern",
                "customer_message": BANK_ALERT_MESSAGE,
            }
        if source != "customer_initiated":
            return missing_plan(
                "fraud_alert", ["fraud alert source"],
                "I need to confirm the alert type before any security action can be considered.",
            )
        legitimate = data.get("recent_transactions_legitimate")
        if legitimate is None:
            return {
                "stage": "fraud_alert",
                "next_step": "ask_customer",
                "required_before_action": ["customer confirmation that recent transactions are legitimate"],
                "recommended_tool": None,
                "tool_arguments": None,
                "customer_message": "Before I can continue, please verify whether your recent transactions are legitimate.",
            }
        if legitimate is not True:
            return {
                "stage": "fraud_alert",
                "next_step": "transfer_to_human",
                "required_before_action": [],
                "recommended_tool": "transfer_to_human_agents",
                "tool_arguments": None,
                "transfer_reason": "fraud_or_security_concern",
                "customer_message": "For your security, I need to have this reviewed by our security team.",
            }
        if not verified:
            return missing_plan(
                "fraud_alert_verification", ["two-field identity verification and verification audit record"],
                "I can clear this customer-requested alert after I verify your identity.",
            )
        return {
            "stage": "fraud_alert",
            "next_step": "clear_customer_initiated_alert",
            "required_before_action": ["verified identity", "customer confirmation that recent transactions are legitimate", "interaction note documenting the reason"],
            "recommended_tool": "clear_debit_card_fraud_alert_4892",
            "tool_arguments": {"card_id": card_id, "reason": "customer_verified"},
            "customer_message": "I can now clear the customer-requested security alert.",
        }

    blocked = value(card, "velocity_blocked")
    if not isinstance(blocked, bool):
        return missing_plan(
            "velocity_block", ["velocity_blocked state from debit-card lookup"],
            "I need to confirm whether a temporary security block is affecting the card.",
        )
    if not blocked:
        return {
            "stage": "complete",
            "next_step": "collect_decline_details",
            "required_before_action": ["decline amount, time, merchant, and any screenshots before further investigation"],
            "recommended_tool": None,
            "tool_arguments": None,
            "customer_message": "The required card, account, fraud-alert, and velocity-block checks found no listed block. I need a few decline details to continue investigating.",
        }

    wants_clear = data.get("wants_velocity_clear")
    if wants_clear is None:
        return {
            "stage": "velocity_block",
            "next_step": "ask_customer",
            "required_before_action": ["customer consent to lift the temporary block"],
            "recommended_tool": None,
            "tool_arguments": None,
            "customer_message": VELOCITY_MESSAGE,
        }
    if wants_clear is not True:
        return {
            "stage": "velocity_block",
            "next_step": "wait_for_automatic_expiry",
            "required_before_action": [],
            "recommended_tool": None,
            "tool_arguments": None,
            "customer_message": "The temporary block will lift automatically after 30 minutes.",
        }
    if data.get("velocity_explanation_acceptable") is not True:
        return {
            "stage": "velocity_block",
            "next_step": "obtain_explanation",
            "required_before_action": ["reasonable explanation for unusual activity"],
            "recommended_tool": None,
            "tool_arguments": None,
            "customer_message": "Before I can lift the block early, please tell me what caused the unusual activity.",
        }
    if not verified:
        return missing_plan(
            "velocity_verification", ["two-field identity verification and verification audit record"],
            "I can lift the temporary block early after I verify your identity.",
        )
    return {
        "stage": "velocity_block",
        "next_step": "clear_velocity_block",
        "required_before_action": ["verified identity", "reasonable explanation for unusual activity", "interaction note documenting the reason"],
        "recommended_tool": "clear_debit_card_fraud_alert_4892",
        "tool_arguments": {"card_id": card_id, "reason": "velocity_clear"},
        "customer_message": "I can now lift the temporary security block early.",
    }


def main() -> None:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON value must be an object")
        emit(**plan(data))
    except (json.JSONDecodeError, ValueError) as exc:
        emit(error="invalid_input", message=str(exc))


if __name__ == "__main__":
    main()
