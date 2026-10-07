#!/usr/bin/env python3
"""Produce a non-executing, ordered CODE 05 debit-card triage plan.

Reads one JSON object from stdin and writes one JSON object to stdout.
No network, tool calls, files, or banking actions are performed.
"""
import json
import sys


def as_bool(value):
    return value is True


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def need_card_fields(card, index):
    missing = [key for key in ("card_id", "account_id", "status") if not card.get(key)]
    return ["cards[%d] missing %s" % (index, key) for key in missing]


def verification_ready(data):
    return all(as_bool(data.get(key)) for key in (
        "identity_verified", "authority_confirmed", "ownership_verified"
    ))


def plan_for(card, account, verified):
    card_id = card["card_id"]
    status = str(card.get("status", "")).upper()
    account_status = str((account or {}).get("status", "")).upper()
    base = {"card_id": card_id, "card_status": status, "steps": []}

    if status == "FROZEN":
        base["outcome"] = "card_frozen"
        base["steps"].append({
            "kind": "ask_customer",
            "message": "Ask whether the customer wants to unfreeze this card."
        })
        if account_status == "OPEN":
            base["steps"].append({
                "kind": "conditional_action",
                "condition": "Identity, ownership, and customer confirmation are recorded.",
                "tool": "unfreeze_debit_card_3893",
                "arguments": {"card_id": card_id}
            })
        else:
            base["steps"].append({
                "kind": "blocker",
                "reason": "The linked checking account must be OPEN before unfreezing."
            })
        return base

    if status == "CLOSED":
        base["outcome"] = "card_closed"
        base["steps"].append({
            "kind": "customer_guidance",
            "message": "The card is no longer active; check for another active or pending card and offer the applicable replacement workflow."
        })
        return base

    if status == "PENDING":
        issue_reason = str(card.get("issue_reason", "")).lower()
        tools = {
            "new_account": "activate_debit_card_8291",
            "first_card": "activate_debit_card_8291",
            "lost": "activate_debit_card_8292",
            "stolen": "activate_debit_card_8292",
            "fraud": "activate_debit_card_8292",
            "expired": "activate_debit_card_8293",
            "damaged": "activate_debit_card_8293",
            "upgrade": "activate_debit_card_8293",
            "bank_reissue": "activate_debit_card_8293",
        }
        base["outcome"] = "card_pending_activation"
        base["steps"].append({
            "kind": "prerequisites",
            "requirements": [
                "Verified customer and card ownership",
                "Linked checking account is OPEN",
                "Physical card is present and not expired",
                "Last four digits, expiration date, and CVV match",
                "New PIN is exactly four digits and is not sequential, repeating, or derived from birth date"
            ]
        })
        if account_status != "OPEN":
            base["steps"].append({"kind": "blocker", "reason": "Linked account is not OPEN."})
        elif issue_reason in tools:
            base["steps"].append({
                "kind": "conditional_action", "tool": tools[issue_reason],
                "condition": "All activation prerequisites and customer confirmation are satisfied."
            })
        else:
            base["steps"].append({"kind": "blocker", "reason": "Unknown issue_reason; refresh card data before selecting an activation tool."})
        return base

    if status != "ACTIVE":
        base["outcome"] = "unknown_card_status"
        base["steps"].append({"kind": "blocker", "reason": "Refresh card lookup; do not infer a remedy from an unknown status."})
        return base

    # Required order for an ACTIVE card: account, fraud alert, velocity block.
    if not account:
        base["outcome"] = "linked_account_not_found"
        base["steps"].append({"kind": "blocker", "reason": "Retrieve the linked account before further diagnosis."})
        return base
    if account_status != "OPEN":
        base["outcome"] = "linked_account_restriction"
        base["steps"].append({
            "kind": "customer_guidance",
            "message": "Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance."
        })
        return base

    active = card.get("fraud_alert_active")
    source = card.get("alert_source")
    if active is None:
        base["outcome"] = "fraud_alert_state_unknown"
        base["steps"].append({"kind": "blocker", "reason": "Refresh lookup with fraud-alert fields before proceeding to velocity checks."})
        return base
    if as_bool(active):
        if source == "bank_initiated":
            base["outcome"] = "bank_initiated_fraud_alert"
            base["steps"].append({
                "kind": "transfer",
                "reason": "fraud_or_security_concern",
                "message": "I see there’s a security flag on your account that requires additional review. I’m transferring you to our security team."
            })
            return base
        if source == "customer_initiated":
            legitimate = as_bool(card.get("customer_confirmed_transactions_legitimate"))
            base["outcome"] = "customer_initiated_fraud_alert"
            base["steps"].append({"kind": "ask_customer", "message": "Ask the customer to verify that recent transactions are legitimate."})
            base["may_clear_now"] = verified and legitimate
            if verified and legitimate:
                base["steps"].append({
                    "kind": "conditional_action", "tool": "clear_debit_card_fraud_alert_4892",
                    "arguments": {"card_id": card_id, "reason": "customer_verified"},
                    "condition": "Document the legitimate-transaction confirmation and clearing reason."
                })
            return base
        base["outcome"] = "fraud_alert_source_unknown"
        base["steps"].append({"kind": "blocker", "reason": "Do not clear an alert with an unknown or unsupported source."})
        return base

    velocity = card.get("velocity_blocked")
    if velocity is None:
        base["outcome"] = "velocity_state_unknown"
        base["steps"].append({"kind": "blocker", "reason": "Refresh lookup with velocity-block status."})
        return base
    if as_bool(velocity):
        agrees = as_bool(card.get("customer_consents_velocity_clear"))
        base["outcome"] = "velocity_blocked"
        base["steps"].append({
            "kind": "customer_guidance",
            "message": "Your card was temporarily blocked because our security system detected unusual activity patterns. This block automatically lifts after 30 minutes. Would you like me to verify your identity and lift it now?"
        })
        base["may_clear_now"] = verified and agrees
        if verified and agrees:
            base["steps"].append({
                "kind": "conditional_action", "tool": "clear_debit_card_fraud_alert_4892",
                "arguments": {"card_id": card_id, "reason": "velocity_clear"},
                "condition": "Document identity verification and the customer’s consent."
            })
        return base

    base["outcome"] = "no_code_05_block_found"
    base["steps"].append({
        "kind": "investigate",
        "message": "No status, linked-account, fraud-alert, or velocity-block cause was found. Corroborate the attempts and collect timestamps, screenshots, app/browser/device version, and workflow; escalate with logs if repeated."
    })
    return base


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        emit({"ok": False, "errors": ["Input must be one valid JSON object: %s" % exc]})
        return
    if not isinstance(data, dict):
        emit({"ok": False, "errors": ["Input must be a JSON object."]})
        return

    accounts = data.get("accounts", [])
    cards = data.get("cards", [])
    errors = []
    if not isinstance(accounts, list):
        errors.append("accounts must be an array")
    if not isinstance(cards, list):
        errors.append("cards must be an array")
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
            errors.extend(need_card_fields(card, i))
    if errors:
        emit({"ok": False, "errors": errors})
        return

    reported = data.get("reported_card_ids")
    candidate_cards = [{"card_id": c["card_id"], "card_number_last_4": c.get("card_number_last_4")} for c in cards]
    if not isinstance(reported, list) or not reported:
        emit({
            "ok": True,
            "identification_required": True,
            "candidate_cards": candidate_cards,
            "message": "Ask the customer to identify each declined card by last four digits, then map it to a unique card_id before remediation."
        })
        return
    selected = set(reported)
    available = {c["card_id"] for c in cards}
    unknown = sorted(selected - available)
    if unknown:
        emit({"ok": False, "errors": ["reported_card_ids not found in cards: " + ", ".join(unknown)]})
        return

    account_by_id = {a["account_id"]: a for a in accounts}
    verified = verification_ready(data)
    plans = []
    for card in cards:
        if card["card_id"] in selected:
            plans.append(plan_for(card, account_by_id.get(card["account_id"]), verified))
    emit({
        "ok": True,
        "verification_prerequisites_complete": verified,
        "plans": plans,
        "note": "This is an advisory plan only. Obtain customer confirmation where stated and verify live tool results before claiming completion."
    })


if __name__ == "__main__":
    main()
