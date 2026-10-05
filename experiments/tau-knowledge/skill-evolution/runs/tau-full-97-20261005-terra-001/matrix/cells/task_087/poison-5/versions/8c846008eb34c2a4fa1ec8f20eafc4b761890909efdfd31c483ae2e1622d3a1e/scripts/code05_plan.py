#!/usr/bin/env python3
"""Produce a non-executing, ordered CODE 05 triage plan from normalized facts.

Reads one JSON object from stdin and writes one JSON object to stdout. It makes no
network, filesystem, or banking-tool calls.
"""

import json
import sys

VELOCITY_NOTICE = (
    "Your card was temporarily blocked because our security system detected unusual "
    "activity patterns. This block automatically lifts after 30 minutes. Would you "
    "like me to verify your identity and lift it now?"
)


def bool_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def text(value):
    return value.strip().upper() if isinstance(value, str) else None


def require_boolean(card, field, errors):
    value = bool_value(card.get(field))
    if value is None:
        errors.append("missing or invalid %s" % field)
    return value


def observed_velocity_notice(card):
    """Return the mandatory notice when a lookup has already exposed a true block."""
    return VELOCITY_NOTICE if bool_value(card.get("velocity_blocked")) is True else None


def plan_card(card, identity_verified, index):
    errors = []
    checked = ["card_status"]
    label = card.get("label") if isinstance(card.get("label"), str) else "card_%d" % (index + 1)
    status = text(card.get("status"))
    base = {"label": label, "card_id": card.get("card_id"), "checked_in_order": checked}

    if status not in ("ACTIVE", "FROZEN", "CLOSED", "PENDING"):
        base.update({
            "outcome": "unresolved",
            "banking_action_eligible": False,
            "next_step": "obtain a reliable card status",
            "validation_errors": ["missing or unsupported status"],
        })
        return base

    if status == "FROZEN":
        base.update({
            "outcome": "frozen_card",
            "banking_action_eligible": False,
            "next_step": (
                "ask whether the customer wants to unfreeze; verify open linked account, "
                "ownership, and consent before unfreezing; then complete account, fraud, "
                "and velocity checks before promising usability"
            ),
            "validation_errors": errors,
        })
        notice = observed_velocity_notice(card)
        if notice:
            base["required_customer_notice"] = notice
        return base

    if status == "CLOSED":
        base.update({
            "outcome": "closed_card",
            "banking_action_eligible": False,
            "next_step": "check for another active card or discuss replacement after eligibility and fee checks",
            "validation_errors": errors,
        })
        return base

    if status == "PENDING":
        base.update({
            "outcome": "pending_activation",
            "banking_action_eligible": False,
            "next_step": "follow issue-reason-specific activation requirements",
            "validation_errors": errors,
        })
        return base

    checked.append("linked_account_status")
    account_status = text(card.get("account_status"))
    if not account_status:
        errors.append("missing account_status")
        base.update({
            "outcome": "unresolved",
            "banking_action_eligible": False,
            "next_step": "obtain the linked checking-account status",
            "validation_errors": errors,
        })
        return base
    if account_status != "OPEN":
        base.update({
            "outcome": "account_restriction",
            "banking_action_eligible": False,
            "next_step": "give the generic account-restriction message without disclosing details",
            "validation_errors": errors,
        })
        return base

    checked.append("fraud_alert")
    alert = require_boolean(card, "fraud_alert_active", errors)
    if alert is None:
        base.update({
            "outcome": "unresolved",
            "banking_action_eligible": False,
            "next_step": "obtain fraud-alert status and source",
            "validation_errors": errors,
        })
        return base

    if alert:
        source = card.get("alert_source") if isinstance(card.get("alert_source"), str) else None
        source = source.strip().lower() if source else None
        if source == "bank_initiated":
            base.update({
                "outcome": "bank_initiated_fraud_alert",
                "banking_action_eligible": False,
                "next_step": "transfer to security; do not clear the alert",
                "transfer_reason": "fraud_or_security_concern",
                "validation_errors": errors,
            })
            return base
        if source == "customer_initiated":
            legitimate = require_boolean(card, "transactions_confirmed_legitimate", errors)
            consent = require_boolean(card, "customer_consents_to_clear", errors)
            eligible = bool(identity_verified and legitimate is True and consent is True and not errors)
            base.update({
                "outcome": "customer_initiated_fraud_alert",
                "banking_action_eligible": eligible,
                "next_step": (
                    "clear with reason customer_verified only if identity, legitimacy confirmation, "
                    "ownership, and consent are all satisfied"
                    if not eligible else "eligible to clear with reason customer_verified"
                ),
                "validation_errors": errors,
            })
            return base
        errors.append("missing or unsupported alert_source for active fraud alert")
        base.update({
            "outcome": "unresolved_fraud_alert",
            "banking_action_eligible": False,
            "next_step": "do not clear; obtain alert source or use security escalation as appropriate",
            "validation_errors": errors,
        })
        return base

    checked.append("velocity_block")
    velocity = require_boolean(card, "velocity_blocked", errors)
    if velocity is None:
        base.update({
            "outcome": "unresolved",
            "banking_action_eligible": False,
            "next_step": "obtain velocity-block status",
            "validation_errors": errors,
        })
        return base
    if velocity:
        requested = require_boolean(card, "customer_requested_early_velocity_lift", errors)
        explanation = require_boolean(card, "reasonable_velocity_explanation", errors)
        consent = require_boolean(card, "customer_consents_to_clear", errors)
        eligible = bool(identity_verified and requested is True and explanation is True and consent is True and not errors)
        base.update({
            "outcome": "velocity_block",
            "banking_action_eligible": eligible,
            "required_customer_notice": VELOCITY_NOTICE,
            "next_step": (
                "clear with reason velocity_clear only after identity, ownership, reasonable explanation, and consent"
                if not eligible else "eligible to clear with reason velocity_clear"
            ),
            "validation_errors": errors,
        })
        return base

    base.update({
        "outcome": "no_status_or_security_cause_found",
        "banking_action_eligible": False,
        "next_step": "collect exact decline context and investigate recurring errors without inventing a cause",
        "validation_errors": errors,
    })
    return base


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"ok": False, "validation_errors": ["invalid input JSON: %s" % exc], "cases": []}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "validation_errors": ["input must be a JSON object"], "cases": []}))
        return

    cards = payload.get("cards")
    if not isinstance(cards, list) or not cards:
        print(json.dumps({"ok": False, "validation_errors": ["cards must be a non-empty array"], "cases": []}))
        return

    identity = bool_value(payload.get("identity_verified"))
    top_errors = []
    if identity is None:
        top_errors.append("identity_verified must be a boolean")
        identity = False

    results = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            results.append({
                "label": "card_%d" % (index + 1),
                "outcome": "unresolved",
                "banking_action_eligible": False,
                "checked_in_order": [],
                "next_step": "supply a card object",
                "validation_errors": ["card entry must be an object"],
            })
        else:
            results.append(plan_card(card, identity, index))

    print(json.dumps({"ok": not top_errors, "validation_errors": top_errors, "cases": results}, sort_keys=True))


if __name__ == "__main__":
    main()
