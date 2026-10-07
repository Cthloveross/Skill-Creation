#!/usr/bin/env python3
"""Read decline evidence as JSON from stdin and emit conservative triage JSON.

This helper does not call banking tools and cannot authorize an action. Input schema:
{
  "accounts": [object], "cards": [object], "transactions": [object],
  "decline": {"account_id": str?, "card_id": str?, "channel": str?,
              "amount": number|string?, "code": string|number|null},
  "identity_verified": bool
}
Fields beyond this schema are preserved only through derived findings. Card fields used when
present: status, fraud_alert_active, alert_source, velocity_blocked, pin_locked,
daily_purchase_limit, daily_purchase_used, daily_atm_limit, daily_atm_used. Account fields
used when present: status, available_balance, balance. Transactions may use status and amount.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def money(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def text(value):
    return str(value).upper() if value is not None else ""


def find_by_id(rows, key, value):
    if value is None:
        return None
    for row in rows:
        if str(row.get(key)) == str(value):
            return row
    return None


def add_unique(items, value):
    if value not in items:
        items.append(value)


def main(payload):
    if not isinstance(payload, dict):
        return {"error": "input must be a JSON object"}
    accounts = payload.get("accounts") or []
    cards = payload.get("cards") or []
    txns = payload.get("transactions") or []
    decline = payload.get("decline") or {}
    if not all(isinstance(x, list) for x in (accounts, cards, txns)) or not isinstance(decline, dict):
        return {"error": "accounts, cards, transactions must be arrays and decline must be an object"}

    findings, missing, next_steps, gates = [], [], [], []
    card = find_by_id(cards, "card_id", decline.get("card_id"))
    account = find_by_id(accounts, "account_id", decline.get("account_id"))
    if card is None and len(cards) == 1:
        card = cards[0]
    if account is None and card is not None:
        account = find_by_id(accounts, "account_id", card.get("account_id"))
    if account is None and len(accounts) == 1:
        account = accounts[0]

    if card is None:
        add_unique(missing, "A specific declined card (or card last four digits) is needed when more than one card may apply.")
    else:
        status = text(card.get("status"))
        if not status:
            add_unique(missing, "card status")
        elif status != "ACTIVE":
            findings.append({"kind": "card_status", "value": status, "evidence": "card.status"})
            if status == "FROZEN":
                next_steps.append("Ask whether the customer wants the card unfrozen; require verification and an OPEN linked account before an unfreeze.")
            elif status == "PENDING":
                next_steps.append("Use the card activation procedure after verifying physical-card details, issue reason, account status, and identity.")
            elif status == "CLOSED":
                next_steps.append("Explain the card is no longer active and check for another active or pending replacement card.")

    if account is None:
        add_unique(missing, "linked checking-account status")
    else:
        account_status = text(account.get("status"))
        if not account_status:
            add_unique(missing, "linked checking-account status")
        elif account_status != "OPEN":
            findings.append({"kind": "account_not_open", "value": account_status, "evidence": "account.status"})
            next_steps.append("Use the approved account-restriction response; do not disclose suspended or restricted account details.")

    verified = payload.get("identity_verified") is True
    if card is not None:
        fraud = card.get("fraud_alert_active") is True
        source = str(card.get("alert_source") or "").lower()
        if fraud:
            findings.append({"kind": "fraud_alert", "value": source or "source_unknown", "evidence": "card.fraud_alert_active/card.alert_source"})
            if source == "bank_initiated":
                gates.append({"action": "clear_fraud_alert", "allowed": False, "reason": "Bank-initiated fraud alerts cannot be cleared; transfer to security."})
                next_steps.append("Transfer to the security team; do not clear or explain the bank-initiated security flag.")
            elif source == "customer_initiated":
                allowed = verified
                gates.append({"action": "clear_customer_fraud_alert", "allowed": allowed, "reason": "Requires identity verification and customer confirmation that recent transactions are legitimate."})
                next_steps.append("After verification and legitimacy confirmation, a customer-initiated alert may be cleared with reason customer_verified.")
            else:
                gates.append({"action": "clear_fraud_alert", "allowed": False, "reason": "Alert source must be established before any clearing decision."})
        if card.get("velocity_blocked") is True:
            findings.append({"kind": "velocity_block", "value": True, "evidence": "card.velocity_blocked"})
            gates.append({"action": "clear_velocity_block", "allowed": verified, "reason": "Early clearing requires identity verification; otherwise it normally expires after 30 minutes."})
            next_steps.append("Explain the temporary block normally lifts after 30 minutes; offer an early clear only after verification.")
        if card.get("pin_locked") is True:
            findings.append({"kind": "pin_locked", "value": True, "evidence": "card.pin_locked"})
            gates.append({"action": "unlock_pin", "allowed": False, "reason": "A full PIN Lock Investigation Protocol and its outcome are required before an unlock."})
            next_steps.append("Complete the PIN Lock Investigation Protocol; do not unlock based on this helper.")

    code = str(decline.get("code") or "").strip().lstrip("0")
    if code in {"4", "7", "34", "59"}:
        findings.append({"kind": "non_disclosable_security_code", "value": code, "evidence": "decline.code"})
        next_steps.append("Do not disclose the decline code or fraud rationale; give only the approved in-person/branch response.")
    elif code in {"55", "75"} and not any(f.get("kind") == "pin_locked" for f in findings):
        next_steps.append("Check PIN lock state and apply the full PIN Lock Investigation Protocol before considering any unlock.")
    elif code == "83":
        next_steps.append("Describe this as a temporary PIN-verification network issue; retry, use signature if allowed, another terminal, or wait 10–15 minutes.")

    channel = str(decline.get("channel") or "").lower()
    amount = money(decline.get("amount"))
    if amount is None:
        add_unique(missing, "approximate declined amount")
    if channel in {"purchase", "in_person", "online", "card_not_present", "atm"} and card is not None:
        is_atm = channel == "atm"
        limit_key = "daily_atm_limit" if is_atm else "daily_purchase_limit"
        used_key = "daily_atm_used" if is_atm else "daily_purchase_used"
        limit, used = money(card.get(limit_key)), money(card.get(used_key))
        if limit is None or used is None:
            add_unique(missing, f"{limit_key} and {used_key}")
        else:
            remaining = max(Decimal("0"), limit - used)
            findings.append({"kind": "daily_limit_capacity", "limit_type": "atm" if is_atm else "purchase", "limit": str(limit), "used": str(used), "remaining": str(remaining), "evidence": f"card.{limit_key}/card.{used_key}"})
            if amount is not None and amount > remaining:
                next_steps.append("The requested amount exceeds remaining daily capacity; discuss a smaller transaction or a separately requested eligible temporary increase.")

    if account is not None and amount is not None:
        available = money(account.get("available_balance"))
        if available is None:
            add_unique(missing, "available balance (posted balance alone is not sufficient)")
        else:
            pending_total = sum((money(t.get("amount")) or Decimal("0")) for t in txns if text(t.get("status")) in {"PENDING", "PROCESSING"} and (money(t.get("amount")) or Decimal("0")) > 0)
            findings.append({"kind": "available_funds", "available_balance": str(available), "pending_debits_observed": str(pending_total), "evidence": "account.available_balance and pending transaction records"})
            if amount > available:
                next_steps.append("Available funds appear insufficient for the requested amount; offer adding/transferring funds or a smaller purchase.")
            elif pending_total > 0:
                next_steps.append("Available funds may be affected by pending activity; review holds and pending debits before ruling out a balance-related decline.")

    if not txns:
        add_unique(missing, "recent transaction history, including pending activity and declined attempts")
    if not code:
        add_unique(missing, "decline code or notification reason, if obtainable")
    if not findings and not missing:
        next_steps.append("No supported cause was found in supplied fields; inspect merchant amount, holds, restrictions, location controls, and PIN/decline history.")
    return {"findings": findings, "missing_data": missing, "customer_safe_next_steps": next_steps, "action_gates": gates}


if __name__ == "__main__":
    try:
        main_input = json.load(sys.stdin)
        print(json.dumps(main(main_input), sort_keys=True))
    except json.JSONDecodeError:
        print(json.dumps({"error": "stdin must contain valid JSON"}))
    except Exception as exc:
        print(json.dumps({"error": "unable to analyze supplied evidence", "detail": str(exc)}))
