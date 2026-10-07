#!/usr/bin/env python3
"""Produce a conservative debit-card decline investigation checklist.

Input JSON schema:
{
  "decline_code": "optional string or number",
  "amount": optional number,
  "channel": "purchase" | "atm" | "other",
  "account": {"status": "OPEN", "balance": number},
  "card": {"status": "ACTIVE", "fraud_alert_active": bool,
           "alert_source": "customer_initiated" | "bank_initiated",
           "velocity_blocked": bool, "daily_purchase_limit": number,
           "daily_purchase_used": number, "daily_atm_limit": number,
           "daily_atm_used": number, "pin_locked": bool}
}
Output JSON contains findings, next_steps, requires_verification, and transfer_reason.
It never recommends executing a banking tool automatically.
"""
import json
import sys


def num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def main(data):
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    code = str(data.get("decline_code", "")).strip().upper().replace("CODE ", "")
    amount = num(data.get("amount"))
    channel = data.get("channel", "other")
    findings, steps = [], []
    verification = False
    transfer = None

    status = card.get("status")
    if status and status != "ACTIVE":
        findings.append("Card status is %s." % status)
        if status == "FROZEN":
            steps.append("Ask whether the customer wants an unfreeze; verify identity, ownership, and OPEN linked account before any action.")
            verification = True
        elif status == "PENDING":
            steps.append("Confirm physical-card and activation prerequisites; select activation tool from issue reason.")
            verification = True
        elif status == "CLOSED":
            steps.append("Explain that the card is inactive; inspect card history for an active or pending replacement.")
        return result(findings, steps, verification, transfer)

    account_status = account.get("status")
    if account_status and account_status != "OPEN":
        findings.append("Linked account is not OPEN.")
        steps.append("Give the approved account-restriction message without disclosing restriction details.")
        return result(findings, steps, verification, transfer)

    if card.get("fraud_alert_active") is True:
        source = card.get("alert_source")
        if source == "bank_initiated":
            findings.append("A bank-initiated security alert is active.")
            steps.append("Do not clear the alert; transfer to the security team.")
            transfer = "fraud_or_security_concern"
            return result(findings, steps, verification, transfer)
        if source == "customer_initiated":
            findings.append("A customer-initiated fraud alert is active.")
            steps.append("Clear only after identity verification and confirmation that recent transactions are legitimate.")
            verification = True

    if card.get("velocity_blocked") is True:
        findings.append("A temporary velocity block is active.")
        steps.append("Explain it lifts after 30 minutes; early clearing requires verified identity.")
        verification = True

    if code in {"55", "75"} and card.get("pin_locked") is True:
        findings.append("PIN lock is active.")
        steps.append("Follow the separate PIN fraud-risk investigation before any unlock; do not disclose its scoring.")
        return result(findings, steps, verification, transfer)

    if code == "61" and channel in {"purchase", "atm"}:
        prefix = "daily_purchase" if channel == "purchase" else "daily_atm"
        limit, used = num(card.get(prefix + "_limit")), num(card.get(prefix + "_used"))
        if limit is not None and used is not None:
            remaining = limit - used
            findings.append("Remaining %s capacity is %.2f." % (channel, remaining))
            if amount is not None and amount > remaining:
                steps.append("The requested amount exceeds remaining capacity; assess temporary-increase eligibility if requested.")
            else:
                steps.append("The supplied amount does not exceed calculated remaining capacity; continue generic/security diagnostics.")
        else:
            steps.append("Retrieve the applicable daily limit and same-day usage before diagnosing a limit decline.")
        return result(findings, steps, verification, transfer)

    if code == "51":
        findings.append("Insufficient-funds code reported.")
        steps.append("Review balance, pending debits, authorization holds, and POS overdraft setting before concluding funds are unavailable.")
    elif code in {"04", "07", "34", "59"}:
        findings.append("Security-sensitive decline code reported.")
        steps.append("Do not disclose the code or rationale; use approved branch/in-person wording.")
        transfer = "fraud_or_security_concern"
    elif code in {"91", "96"}:
        findings.append("Temporary issuer/system code reported.")
        steps.append("Suggest retry in a few minutes, then 10–15 minutes if persistent.")
    elif code == "19":
        findings.append("Temporary re-entry code reported.")
        steps.append("Ask merchant to retry immediately; use a 10–15 minute wait only after another failure.")
    else:
        steps.append("Continue generic order: ACTIVE card, OPEN account, fraud alert, velocity block, then live transaction and limit review.")

    return result(findings, steps, verification, transfer)


def result(findings, steps, verification, transfer):
    return {
        "findings": findings,
        "next_steps": steps,
        "requires_verification": verification,
        "transfer_reason": transfer,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
