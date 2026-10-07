#!/usr/bin/env python3
"""Check supplied banking-action prerequisites without invoking any banking tool."""
import json
import sys

COMMON = [
    "identity_verified", "authority_verified", "account_ownership_verified",
    "product_eligibility_verified", "fees_disclosed", "limits_checked",
    "cutoffs_checked", "confirmation_received"
]
OPEN_SAVINGS = [
    "active_checking_verified", "checking_tenure_verified",
    "savings_account_count_verified", "under_savings_account_limit",
    "no_collections_or_negative_balances", "official_account_class_confirmed",
    "opening_deposit_requirement_confirmed"
]
TRANSFER = ["source_account_confirmed", "destination_account_confirmed", "available_balance_verified", "amount_confirmed"]
CARD_APPLICATION = ["card_eligibility_verified", "credit_review_consent_received", "card_terms_disclosed"]


def main(data):
    action = data.get("action")
    if action not in {"open_savings", "internal_funding_transfer", "credit_card_application", "statement_delivery_change"}:
        return {"status": "error", "error": "action must be open_savings, internal_funding_transfer, credit_card_application, or statement_delivery_change"}
    required = list(COMMON)
    if action == "open_savings":
        required += OPEN_SAVINGS
    elif action == "internal_funding_transfer":
        required += TRANSFER
    elif action == "credit_card_application":
        required += CARD_APPLICATION
    elif action == "statement_delivery_change":
        required += ["statement_delivery_option_verified"]
    missing = [key for key in required if data.get(key) is not True]
    return {
        "status": "ready" if not missing else "not_ready",
        "action": action,
        "missing_or_unverified": missing,
        "next_step": "Obtain and verify every listed prerequisite and explicit confirmation before using a normal banking tool." if missing else "Prerequisites are marked complete; use only the declared normal banking tool and record its actual result."
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
