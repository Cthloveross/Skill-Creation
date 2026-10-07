#!/usr/bin/env python3
"""Produce a safe, ordered advisory plan for one debit-card CODE 05 case.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
program is deliberately side-effect free: its action names are recommendations
for an agent using authorized banking tools, not tool calls.
"""
import json
import sys

CARD_STATUSES = {"ACTIVE", "FROZEN", "CLOSED", "PENDING"}


def fail(message):
    return {"ok": False, "error": message}


def boolean(value, field):
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be a JSON boolean")


def main(data):
    if not isinstance(data, dict):
        return fail("input must be a JSON object")
    card = data.get("card")
    if not isinstance(card, dict):
        return fail("card must be an object")
    status = card.get("status")
    account_status = data.get("account_status")
    if status not in CARD_STATUSES:
        return fail("card.status must be ACTIVE, FROZEN, CLOSED, or PENDING")
    if not isinstance(account_status, str) or not account_status:
        return fail("account_status must be a nonempty string")

    try:
        verified = boolean(data.get("identity_verified", False), "identity_verified")
        legitimate = boolean(data.get("customer_confirms_transactions_legitimate", False), "customer_confirms_transactions_legitimate")
        wants_unfreeze = boolean(data.get("customer_wants_unfreeze", False), "customer_wants_unfreeze")
        wants_velocity_clear = boolean(data.get("customer_requests_early_velocity_clear", False), "customer_requests_early_velocity_clear")
        reasonable_explanation = boolean(data.get("reasonable_velocity_explanation", False), "reasonable_velocity_explanation")
    except ValueError as exc:
        return fail(str(exc))

    steps = [{"order": 1, "check": "card_status", "value": status}]
    if status == "FROZEN":
        if wants_unfreeze and verified and account_status == "OPEN":
            steps.append({"order": 1, "agent_action_required": "unfreeze_card", "tool": "unfreeze_debit_card_3893", "prerequisites": ["verified identity and ownership", "customer consent", "linked account OPEN"]})
            return {"ok": True, "outcome": "recommend_unfreeze", "steps": steps}
        steps.append({"order": 1, "customer_response": "Card is frozen; ask whether the customer wants it unfrozen. Do not unfreeze until identity/ownership is verified and the linked account is OPEN."})
        return {"ok": True, "outcome": "frozen_card_requires_unfreeze_branch", "steps": steps}
    if status == "CLOSED":
        steps.append({"order": 1, "customer_response": "Card is no longer active; check for another active card or applicable replacement option."})
        return {"ok": True, "outcome": "closed_card", "steps": steps}
    if status == "PENDING":
        steps.append({"order": 1, "customer_response": "Card is not yet activated; follow the issue-reason-specific activation protocol."})
        return {"ok": True, "outcome": "pending_card_requires_activation", "steps": steps}

    steps.append({"order": 2, "check": "linked_account_status", "value": account_status})
    if account_status != "OPEN":
        steps.append({"order": 2, "customer_response": "Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance."})
        return {"ok": True, "outcome": "linked_account_not_open", "steps": steps}

    fraud_active = card.get("fraud_alert_active")
    source = card.get("alert_source")
    if not isinstance(fraud_active, bool):
        steps.append({"order": 3, "check": "fraud_alert", "result": "unknown", "customer_response": "Obtain authoritative fraud-alert status; do not assume an omitted value is false."})
        return {"ok": True, "outcome": "fraud_status_unknown", "steps": steps}
    steps.append({"order": 3, "check": "fraud_alert", "active": fraud_active, "alert_source": source})
    if fraud_active:
        if source == "bank_initiated":
            steps.append({"order": 3, "agent_action_required": "transfer_to_security", "transfer_reason": "fraud_or_security_concern", "customer_response": "I see there's a security flag on your account that requires additional review. I'm transferring you to our security team."})
            return {"ok": True, "outcome": "bank_initiated_fraud_escalation", "steps": steps}
        if source != "customer_initiated":
            steps.append({"order": 3, "customer_response": "Fraud-alert source is unknown; do not clear it and obtain authoritative security guidance."})
            return {"ok": True, "outcome": "fraud_source_unknown", "steps": steps}
        if verified and legitimate:
            steps.append({"order": 3, "agent_action_required": "clear_customer_fraud_alert", "tool": "clear_debit_card_fraud_alert_4892", "arguments": {"card_id": card.get("card_id"), "reason": "customer_verified"}, "prerequisites": ["verified identity", "customer affirmatively confirmed transactions legitimate"]})
            return {"ok": True, "outcome": "recommend_clear_customer_initiated_alert", "steps": steps}
        steps.append({"order": 3, "customer_response": "Ask the customer to verify recent transactions. Do not clear a customer-initiated alert until identity is verified and transactions are affirmatively confirmed legitimate."})
        return {"ok": True, "outcome": "customer_alert_needs_confirmation", "steps": steps}

    velocity = card.get("velocity_blocked")
    if not isinstance(velocity, bool):
        steps.append({"order": 4, "check": "velocity_block", "result": "unknown", "customer_response": "Obtain authoritative velocity-block status; do not assume an omitted value is false."})
        return {"ok": True, "outcome": "velocity_status_unknown", "steps": steps}
    steps.append({"order": 4, "check": "velocity_block", "active": velocity})
    if velocity:
        if verified and wants_velocity_clear and reasonable_explanation:
            steps.append({"order": 4, "agent_action_required": "clear_velocity_block", "tool": "clear_debit_card_fraud_alert_4892", "arguments": {"card_id": card.get("card_id"), "reason": "velocity_clear"}, "prerequisites": ["verified identity", "customer requested early clearing", "reasonable explanation"]})
            return {"ok": True, "outcome": "recommend_clear_velocity_block", "steps": steps}
        steps.append({"order": 4, "customer_response": "The temporary unusual-activity block automatically lifts after 30 minutes. Offer an early lift only after identity verification and a reasonable explanation."})
        return {"ok": True, "outcome": "velocity_block_needs_prerequisites", "steps": steps}

    steps.append({"order": 4, "customer_response": "No listed card-status, account-status, fraud-alert, or velocity-block issue was found. Review relevant transaction records and report the completed investigation without guessing a cause."})
    return {"ok": True, "outcome": "no_code05_control_found", "steps": steps}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        result = main(raw)
    except json.JSONDecodeError as exc:
        result = fail(f"invalid JSON input: {exc.msg}")
    except Exception as exc:  # keep the script's public interface JSON-only
        result = fail(f"unexpected input error: {exc}")
    print(json.dumps(result, sort_keys=True))
