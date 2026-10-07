#!/usr/bin/env python3
"""Normalize debit-card decline-code triage without accessing banking systems.

Input JSON object:
  decline_code: optional str/int such as "CODE 61" or 61
  transaction_kind: optional "purchase" or "atm"
  card_status, account_status: optional status strings
  limit, used, requested_amount: optional numeric values

Output JSON object:
  normalized_code, branch, lookup_requirements, guidance,
  escalation_required, and optional numeric limit assessment.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation

BRANCHES = {
    "05": ("generic_decline", ["card_status", "account_status", "fraud_alert_state_and_source", "velocity_block_state"], "Check card status, linked account status, fraud-alert state/source, and velocity-block state in that order.", False),
    "14": ("invalid_card_number", ["all_account_cards", "card_status", "date_issued"], "Confirm the correct current card is being used; an old replaced card or saved merchant card may need updating.", False),
    "19": ("temporary_processing_error", [], "Ask the merchant to retry immediately; if it repeats, wait 10–15 minutes.", False),
    "41": ("lost_card", ["card_status", "issue_reason", "replacement_cards"], "A reported-lost card cannot be reactivated; confirm the report and use the lost-card process.", False),
    "43": ("stolen_card", ["card_status", "issue_reason", "recent_transactions"], "Use enhanced identity verification. A stolen card cannot be reactivated; denial of the report requires security escalation.", True),
    "51": ("insufficient_funds", ["checking_balance", "pending_transactions", "authorization_holds", "pos_overdraft_setting"], "Review available funds, pending debits, and authorization holds before concluding the balance is insufficient.", False),
    "52": ("checking_account_issue", ["account_status"], "Check linked checking-account status; an open account may need a 10–15 minute retry for synchronization.", False),
    "54": ("expired_card", ["expiration_date", "replacement_cards"], "Verify expiration and check whether an expired-card replacement is pending or active.", False),
    "55": ("pin_problem", ["pin_locked", "pin_attempts_remaining"], "A locked PIN requires the separate fraud-risk protocol before any unlock action.", False),
    "56": ("no_card_record", ["all_account_cards"], "Confirm the customer is using the bank's card and compare only non-sensitive last-four details with cards on file.", False),
    "57": ("card_restriction", ["restricted_mccs", "international_enabled", "online_enabled", "account_class"], "Identify the applicable restriction; protected merchant-category and parental-control changes require their specific rules.", False),
    "58": ("terminal_restriction", [], "Suggest another terminal or merchant. Repeated unrelated-terminal failures need generic decline diagnosis.", False),
    "61": ("daily_limit", ["daily_limit", "daily_used", "account_status", "card_status"], "Compare the requested amount with the remaining applicable daily limit.", False),
    "62": ("geographic_or_new_card_restriction", ["allowed_regions", "blocked_regions", "date_issued"], "Review geographic restrictions and whether a newly issued card is within its initial security window.", False),
    "65": ("activity_count_limit", ["daily_transaction_count", "daily_transaction_limit"], "Explain the daily count and reset timing if returned; count limits are generally not increaseable.", False),
    "75": ("pin_problem", ["pin_locked", "pin_attempts_remaining"], "A locked PIN requires the separate fraud-risk protocol before any unlock action.", False),
    "82": ("chip_or_cvv_mismatch", ["card_status", "recent_transactions"], "Ask about card damage. An undamaged card with this issue should be treated as a possible security concern.", False),
    "83": ("pin_network_error", [], "Explain this is a temporary PIN-verification issue, then retry or try another terminal.", False),
    "87": ("cashback_not_permitted", [], "Retry the purchase without cashback.", False),
    "91": ("issuer_unavailable", [], "Retry in a few minutes; if persistent, wait 10–15 minutes or use another payment method.", False),
    "92": ("routing_issue", [], "Retry the transaction; if it persists, try another merchant.", False),
    "96": ("system_malfunction", [], "Retry in a few minutes; if persistent, wait 10–15 minutes or use another payment method.", False),
    "04": ("internal_security_code", [], "Do not disclose this code or its rationale. Use the approved neutral response and escalation route.", True),
    "07": ("internal_security_code", [], "Do not disclose this code or its rationale. Use the approved neutral response and escalation route.", True),
    "34": ("internal_security_code", [], "Do not disclose this code or its rationale. Use the approved neutral response and escalation route.", True),
    "59": ("internal_security_code", [], "Do not disclose this code or its rationale. Use the approved neutral response and escalation route.", True),
}


def normalize_code(value):
    if value is None:
        return None
    match = re.search(r"\b(\d{1,2})\b", str(value))
    return match.group(1).zfill(2) if match else None


def decimal_value(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if number < 0:
        raise ValueError(f"{field} must be nonnegative")
    return number


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    code = normalize_code(data.get("decline_code"))
    if code in BRANCHES:
        branch, required, guidance, escalate = BRANCHES[code]
    else:
        branch = "generic_decline"
        required = ["card_status", "account_status", "fraud_alert_state_and_source", "velocity_block_state"]
        guidance = "No reliable supported decline code is available; use the generic diagnosis order and do not guess the cause."
        escalate = False

    result = {
        "normalized_code": code,
        "branch": branch,
        "lookup_requirements": required,
        "guidance": guidance,
        "escalation_required": escalate,
    }
    supplied = [key for key in ("limit", "used", "requested_amount") if key in data]
    if supplied:
        values = {key: decimal_value(data[key], key) for key in supplied}
        if "limit" in values and "used" in values:
            remaining = max(Decimal("0"), values["limit"] - values["used"])
            result["remaining_limit"] = float(remaining)
            if "requested_amount" in values:
                result["amount_exceeds_remaining"] = values["requested_amount"] > remaining
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
