#!/usr/bin/env python3
"""Produce a non-executing ordered CODE 05 debit-card triage plan.

Input: one JSON object on stdin. Output: one JSON object on stdout.
This program has no network access, performs no tool calls, and performs no banking action.
"""
import json
import sys


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def is_true(value):
    return value is True


def verification_ready(data):
    return all(is_true(data.get(key)) for key in (
        "identity_verified", "authority_confirmed", "ownership_verified"
    ))


def plan_for(card, account, verified, unauthorized, transfer_requested):
    card_id = card["card_id"]
    status = str(card.get("status", "")).upper()
    account_status = str((account or {}).get("status", "")).upper()
    plan = {"card_id": card_id, "card_status": status, "steps": []}

    if status == "FROZEN":
        plan["outcome"] = "card_frozen"
        plan["steps"].append({"kind": "ask_customer", "message": "Ask whether the customer wants this specific card unfrozen."})
        if account_status == "OPEN":
            plan["steps"].append({
                "kind": "conditional_action",
                "tool": "unfreeze_debit_card_3893",
                "arguments": {"card_id": card_id},
                "condition": "Identity, ownership, OPEN linked account, and explicit customer consent are confirmed."
            })
        else:
            plan["steps"].append({"kind": "blocker", "reason": "The linked checking account must be OPEN before unfreezing."})
        return plan

    if status == "CLOSED":
        plan["outcome"] = "card_closed"
        plan["steps"].append({"kind": "customer_guidance", "message": "Card is not active; check for another active or pending card and offer the applicable replacement workflow."})
        return plan

    if status == "PENDING":
        issue_reason = str(card.get("issue_reason", "")).lower()
        activation_tools = {
            "new_account": "activate_debit_card_8291", "first_card": "activate_debit_card_8291",
            "lost": "activate_debit_card_8292", "stolen": "activate_debit_card_8292", "fraud": "activate_debit_card_8292",
            "expired": "activate_debit_card_8293", "damaged": "activate_debit_card_8293",
            "upgrade": "activate_debit_card_8293", "bank_reissue": "activate_debit_card_8293"
        }
        plan["outcome"] = "card_pending_activation"
        plan["steps"].append({"kind": "prerequisites", "requirements": [
            "Verified identity and card ownership", "OPEN linked checking account", "Physical card present and not expired",
            "Matching last four digits, expiration date, and CVV", "Compliant new four-digit PIN"
        ]})
        if account_status != "OPEN":
            plan["steps"].append({"kind": "blocker", "reason": "Linked account is not OPEN."})
        elif issue_reason in activation_tools:
            plan["steps"].append({"kind": "conditional_action", "tool": activation_tools[issue_reason], "condition": "All activation prerequisites are satisfied."})
        else:
            plan["steps"].append({"kind": "blocker", "reason": "Unknown issue_reason; refresh card data before selecting an activation tool."})
        return plan

    if status != "ACTIVE":
        plan["outcome"] = "unknown_card_status"
        plan["steps"].append({"kind": "blocker", "reason": "Refresh card lookup; do not infer a remedy from an unknown status."})
        return plan

    if not account:
        plan["outcome"] = "linked_account_not_found"
        plan["steps"].append({"kind": "blocker", "reason": "Retrieve the linked account before further diagnosis."})
        return plan
    if account_status != "OPEN":
        plan["outcome"] = "linked_account_restriction"
        plan["steps"].append({"kind": "customer_guidance", "message": "Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance."})
        return plan

    alert = card.get("fraud_alert_active")
    source = card.get("alert_source")
    if alert is None:
        plan["outcome"] = "fraud_alert_state_unknown"
        plan["steps"].append({"kind": "blocker", "reason": "Refresh lookup with fraud-alert fields before velocity checks."})
        return plan
    if is_true(alert):
        if source == "bank_initiated":
            plan["outcome"] = "bank_initiated_fraud_alert"
            plan["steps"].append({"kind": "transfer", "tool": "transfer_to_human_agents", "reason": "fraud_or_security_concern", "condition": "Transfer immediately; do not clear a bank-initiated alert."})
            return plan
        if source == "customer_initiated":
            plan["outcome"] = "customer_initiated_fraud_alert"
            if unauthorized:
                plan["steps"].append({"kind": "preserve_alert", "reason": "Customer reported an unauthorized or inconsistent transaction; do not clear the customer-initiated alert."})
                plan["steps"].append({"kind": "investigate", "message": "Review linked-account transactions and capture suspicious transaction details."})
                plan["steps"].append({"kind": "offer_transfer", "message": "Offer a fraud/dispute specialist connection."})
                if transfer_requested:
                    plan["steps"].append({"kind": "transfer", "tool": "transfer_to_human_agents", "reason": "fraud_or_security_concern", "condition": "Customer accepted or requested transfer; invoke immediately with a factual summary."})
                return plan
            legitimate = is_true(card.get("customer_confirmed_transactions_legitimate"))
            plan["steps"].append({"kind": "ask_customer", "message": "Ask the customer to verify that recent transactions are legitimate."})
            plan["may_clear_now"] = verified and legitimate
            if verified and legitimate:
                plan["steps"].append({"kind": "conditional_action", "tool": "clear_debit_card_fraud_alert_4892", "arguments": {"card_id": card_id, "reason": "customer_verified"}, "condition": "Document legitimate-transaction confirmation and clearing reason."})
            return plan
        plan["outcome"] = "fraud_alert_source_unknown"
        plan["steps"].append({"kind": "blocker", "reason": "Do not clear an alert with an unknown or unsupported source."})
        return plan

    velocity = card.get("velocity_blocked")
    if velocity is None:
        plan["outcome"] = "velocity_state_unknown"
        plan["steps"].append({"kind": "blocker", "reason": "Refresh lookup with velocity-block status."})
    elif is_true(velocity):
        consent = is_true(card.get("customer_consents_velocity_clear"))
        plan["outcome"] = "velocity_blocked"
        plan["steps"].append({"kind": "customer_guidance", "message": "The temporary block automatically lifts after 30 minutes; ask whether the customer wants it lifted now."})
        plan["may_clear_now"] = verified and consent
        if verified and consent:
            plan["steps"].append({"kind": "conditional_action", "tool": "clear_debit_card_fraud_alert_4892", "arguments": {"card_id": card_id, "reason": "velocity_clear"}, "condition": "Document verified identity and explicit consent."})
    else:
        plan["outcome"] = "no_code_05_block_found"
        plan["steps"].append({"kind": "investigate", "message": "Collect exact decline details, timestamps, screenshots, device/app/browser version, and workflow; escalate with logs if repeated."})
    return plan


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        emit({"ok": False, "errors": ["Input must be one valid JSON object: %s" % exc]})
        return
    if not isinstance(data, dict):
        emit({"ok": False, "errors": ["Input must be a JSON object."]})
        return
    accounts, cards = data.get("accounts", []), data.get("cards", [])
    errors = []
    if not isinstance(accounts, list): errors.append("accounts must be an array")
    if not isinstance(cards, list): errors.append("cards must be an array")
    if errors:
        emit({"ok": False, "errors": errors})
        return
    for i, account in enumerate(accounts):
        if not isinstance(account, dict) or not account.get("account_id"):
            errors.append("accounts[%d] must contain account_id" % i)
    for i, card in enumerate(cards):
        if not isinstance(card, dict):
            errors.append("cards[%d] must be an object" % i)
        else:
            for field in ("card_id", "account_id", "status"):
                if not card.get(field): errors.append("cards[%d] missing %s" % (i, field))
    if errors:
        emit({"ok": False, "errors": errors})
        return
    reported = data.get("reported_card_ids")
    candidates = [{"card_id": c["card_id"], "card_number_last_4": c.get("card_number_last_4")} for c in cards]
    if not isinstance(reported, list) or not reported:
        emit({"ok": True, "identification_required": True, "candidate_cards": candidates, "message": "Ask the customer to identify each declined card before remediation."})
        return
    selected = set(reported)
    available = {c["card_id"] for c in cards}
    unknown = sorted(selected - available)
    if unknown:
        emit({"ok": False, "errors": ["reported_card_ids not found in cards: " + ", ".join(unknown)]})
        return
    accounts_by_id = {a["account_id"]: a for a in accounts}
    verified = verification_ready(data)
    plans = [plan_for(c, accounts_by_id.get(c["account_id"]), verified,
                      is_true(data.get("customer_reports_unauthorized")),
                      is_true(data.get("customer_requests_transfer")))
             for c in cards if c["card_id"] in selected]
    emit({"ok": True, "verification_prerequisites_complete": verified, "plans": plans,
          "note": "Advisory only. Obtain live tool access, required consent, and successful tool results before reporting completion."})


if __name__ == "__main__":
    main()
