#!/usr/bin/env python3
"""Assess the next permitted stage of a credit-card closure workflow.

Reads one JSON object from stdin and writes one JSON object to stdout. This is a
pure planning helper: it never contacts banking systems or alters records.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ALLOWED_REASONS = {
    "annual_fee", "not_using_card", "found_better_card", "unhappy_with_rewards",
    "simplifying_finances", "negative_experience", "other",
}
CASH_BACK_CARDS = {
    "Bronze Rewards Card", "Silver Rewards Card", "Gold Rewards Card",
    "Platinum Rewards Card", "Diamond Elite Card", "Crypto-Cash Back",
    "Business Bronze Rewards Card", "Business Silver Rewards Card",
    "Green Rewards Card", "Silver Zoom Card", "Business Gold Rewards Card",
    "Business Platinum Rewards Card",
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    value = value.strip()
    if len(value) >= 10 and value[4:5] == "-":
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    return datetime.strptime(value, "%m/%d/%Y").date()


def parse_money(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if not isinstance(value, str):
        raise ValueError("current_balance must be a number or currency string")
    cleaned = value.strip().replace("$", "").replace(",", "")
    return Decimal(cleaned)


def fail(message):
    return {"decision": "invalid_input", "blockers": [message], "next_actions": []}


def main(data):
    if not isinstance(data, dict):
        return fail("input must be a JSON object")
    account = data.get("account")
    if not isinstance(account, dict):
        return fail("account object is required")

    account_id = account.get("account_id")
    account_user_id = account.get("user_id")
    if not isinstance(account_id, str) or not account_id:
        return fail("account.account_id is required")
    if not isinstance(account_user_id, str) or not account_user_id:
        return fail("account.user_id is required")

    authenticated_user_id = data.get("authenticated_user_id")
    identity_verified = data.get("identity_verified") is True
    if not identity_verified:
        return {
            "decision": "identity_verification_required",
            "blockers": ["identity_not_verified"],
            "next_actions": [
                "Ask the customer to confirm two of date of birth, email, phone number, and address without disclosing stored values.",
                "On a successful match, log verification using the current timestamp before discussing account-specific details or taking action."
            ]
        }
    if not isinstance(authenticated_user_id, str) or not authenticated_user_id:
        return fail("authenticated_user_id is required after identity verification")
    if authenticated_user_id != account_user_id:
        return {
            "decision": "stop_account_ownership_mismatch",
            "blockers": ["selected_account_does_not_belong_to_authenticated_user"],
            "next_actions": ["Do not disclose details, log a closure reason, make an offer, or close this account."]
        }

    try:
        opened = parse_date(account.get("date_of_account_open"))
        today = parse_date(data.get("today"))
        balance = parse_money(account.get("current_balance"))
    except (ValueError, TypeError, InvalidOperation) as exc:
        return fail(str(exc))
    if opened > today:
        return fail("date_of_account_open cannot be after today")

    age_days = (today - opened).days
    disputes = account.get("pending_disputes")
    replacements = account.get("pending_replacement_cards")
    blockers = []
    if disputes is True:
        blockers.append("pending_dispute")
    elif disputes is not False:
        blockers.append("unknown_pending_dispute_status")
    if replacements is True:
        blockers.append("pending_replacement_card")
    elif replacements is not False:
        blockers.append("unknown_pending_replacement_card_status")
    if age_days < 60:
        blockers.append("account_open_less_than_60_days")
    if balance != Decimal("0"):
        blockers.append("outstanding_balance_not_zero")

    facts = {
        "account_id": account_id,
        "account_age_days": age_days,
        "balance": format(balance, ".2f"),
    }
    points = account.get("reward_points")
    card_type = account.get("card_type")
    if isinstance(points, int) and points >= 0 and card_type in CASH_BACK_CARDS:
        facts["rewards_representation"] = "cash_back"
        facts["rewards_redemption_value"] = format(Decimal(points) * Decimal("0.01"), ".2f")
    elif isinstance(points, int) and points >= 0 and card_type == "EcoCard":
        facts["rewards_representation"] = "sustainability_points"
        facts["rewards_redemption_value"] = format(Decimal(points) * Decimal("0.01"), ".2f")

    if blockers:
        explanations = []
        if "pending_dispute" in blockers:
            explanations.append("Wait until the active or pending dispute is resolved.")
        if "pending_replacement_card" in blockers:
            explanations.append("Wait until the pending replacement card is received or activated.")
        if "account_open_less_than_60_days" in blockers:
            explanations.append("The account must be open at least 60 days before closure.")
        if "outstanding_balance_not_zero" in blockers:
            explanations.append("The outstanding balance must be paid to $0.00 before closure or retention can proceed.")
        if any(item.startswith("unknown_") for item in blockers):
            explanations.append("Confirm all unknown eligibility conditions before proceeding.")
        return {
            "decision": "not_eligible_stop",
            "blockers": blockers,
            "next_actions": explanations + [
                "Do not check closure history, log a closure reason, make a retention offer, apply a waiver, or close the account."
            ],
            "facts": facts,
        }

    if data.get("history_checked") is not True:
        return {
            "decision": "check_closure_reason_history",
            "blockers": [],
            "next_actions": [
                "Call get_closure_reason_history_8293 with the selected credit_card_account_id.",
                "Determine whether a closure-reason record exists within the prior year."
            ],
            "facts": facts,
        }

    prior = data.get("prior_closure_reason_within_year")
    if prior not in (True, False):
        return {
            "decision": "history_result_required",
            "blockers": ["unknown_prior_closure_reason_history"],
            "next_actions": ["Interpret the history result before deciding whether retention is permitted."],
            "facts": facts,
        }
    if prior is True:
        if data.get("final_close_confirmed") is True:
            return {
                "decision": "ready_to_close_without_retention",
                "blockers": [],
                "next_actions": [
                    "Skip reason logging and retention because a prior-year closure record exists.",
                    "Call close_credit_card_account_7834 using the selected account ID and authenticated user ID."
                ],
                "facts": facts,
            }
        return {
            "decision": "confirm_final_closure_intent",
            "blockers": [],
            "next_actions": ["Skip retention and obtain clear final confirmation before closing."],
            "facts": facts,
        }

    reason = data.get("closure_reason")
    if reason not in ALLOWED_REASONS:
        return {
            "decision": "obtain_closure_reason",
            "blockers": [],
            "next_actions": ["Ask for the reason and map it to one of the allowed closure-reason values."],
            "facts": facts,
        }
    if data.get("reason_logged") is not True:
        return {
            "decision": "log_closure_reason",
            "blockers": [],
            "next_actions": ["Call log_credit_card_closure_reason_4521 with only account ID, user ID, and the allowed closure_reason."],
            "facts": facts,
        }
    if data.get("concern_addressed") is not True:
        return {
            "decision": "address_concern_before_offer",
            "blockers": [],
            "next_actions": ["Address the stated concern using the applicable retention guidance before making one tier-based offer."],
            "facts": facts,
        }
    if data.get("customer_accepts_retention") is True:
        return {
            "decision": "retain_account_no_closure",
            "blockers": [],
            "next_actions": ["Complete only the accepted, approved retention solution; do not close the account."],
            "facts": facts,
        }
    if data.get("retention_offer_declined") is not True:
        tier = account.get("card_tier")
        offers = {
            "entry": "500 bonus points or a $5 statement credit",
            "mid": "2,000 bonus points or a $20 statement credit",
            "premium": "5,000 bonus points or a $50 statement credit",
            "premium_plus": "5,000 bonus points or a $50 statement credit",
        }
        action = "Make one retention offer only after confirming the card tier."
        if tier in offers:
            action = "Make one retention offer: " + offers[tier]
        return {"decision": "make_retention_offer", "blockers": [], "next_actions": [action], "facts": facts}
    if data.get("final_close_confirmed") is not True:
        return {
            "decision": "confirm_final_closure_intent",
            "blockers": [],
            "next_actions": ["The customer declined retention; obtain clear final confirmation before closing without pressure."],
            "facts": facts,
        }
    return {
        "decision": "ready_to_close_after_retention_declined",
        "blockers": [],
        "next_actions": ["Call close_credit_card_account_7834 using the selected account ID and authenticated user ID."],
        "facts": facts,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        result = main(payload)
    except json.JSONDecodeError:
        result = fail("stdin must contain valid JSON")
    except Exception as exc:  # ensure the JSON stdout contract even for malformed input
        result = fail("unexpected assessment error: " + str(exc))
    print(json.dumps(result, sort_keys=True))
