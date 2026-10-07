#!/usr/bin/env python3
"""Evaluate collected credit-card closure facts without taking banking actions.

Input and output are JSON objects as described in SKILL.md.
"""
import datetime as dt
import json
import sys
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved"}
FINAL_ORDER_STATUSES = {"delivered", "cancelled", "canceled"}
VALID_REASONS = {
    "annual_fee", "not_using_card", "found_better_card", "unhappy_with_rewards",
    "simplifying_finances", "negative_experience", "other",
}
OFFERS = {
    "entry": {"points": 500, "statement_credit": "5.00"},
    "mid": {"points": 2000, "statement_credit": "20.00"},
    "premium": {"points": 5000, "statement_credit": "50.00"},
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    candidate = raw[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(candidate, fmt).date()
        except ValueError:
            pass
    try:
        return dt.datetime.strptime(raw.split()[0], "%m/%d/%Y").date()
    except ValueError:
        return None


def parse_balance(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def as_list(value):
    return value if isinstance(value, list) else None


def main(payload):
    blockers = []
    checks = {}
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}

    fields = payload.get("identity_matched_fields", [])
    allowed = {"date_of_birth", "email", "phone_number", "address"}
    matched = set(fields) & allowed if isinstance(fields, list) else set()
    checks["identity"] = {"matched_field_count": len(matched), "passed": len(matched) >= 2}
    if len(matched) < 2:
        blockers.append("Identity verification requires two matching permitted fields and a verification log.")

    today = parse_date(payload.get("now"))
    opened = parse_date(account.get("opened_on"))
    if today is None or opened is None or opened > today:
        checks["account_age"] = {"passed": False, "days": None}
        blockers.append("A valid current date and account opening date are required to verify the 60-day minimum age.")
    else:
        age_days = (today - opened).days
        checks["account_age"] = {"passed": age_days >= 60, "days": age_days}
        if age_days < 60:
            blockers.append("The account is less than 60 days old.")

    balance = parse_balance(account.get("current_balance"))
    checks["zero_balance"] = {"passed": balance == Decimal("0") if balance is not None else False}
    if balance is None:
        blockers.append("A readable current balance is required.")
    elif balance != Decimal("0"):
        blockers.append("The account balance must be $0.00 before closure.")

    disputes = as_list(payload.get("disputes"))
    if disputes is None:
        checks["disputes"] = {"passed": False, "state": "not_checked"}
        blockers.append("Dispute history has not been checked.")
    else:
        pending = False
        ambiguous = False
        for dispute in disputes:
            if not isinstance(dispute, dict):
                ambiguous = True
                continue
            target = dispute.get("target_account")
            status = str(dispute.get("status", "")).strip().lower()
            if target is None:
                ambiguous = True
            elif target is True and status not in FINAL_DISPUTE_STATUSES:
                pending = True
        checks["disputes"] = {
            "passed": not pending and not ambiguous,
            "has_pending_target_dispute": pending,
            "has_ambiguous_linkage": ambiguous,
        }
        if pending:
            blockers.append("A pending or active dispute on the target account blocks closure.")
        if ambiguous:
            blockers.append("Dispute-to-account linkage is ambiguous and must be resolved before closure.")

    orders = as_list(payload.get("replacement_orders"))
    if orders is None:
        checks["replacement_orders"] = {"passed": False, "state": "not_checked"}
        blockers.append("Pending replacement orders have not been checked.")
    else:
        nonfinal = False
        malformed = False
        for order in orders:
            if not isinstance(order, dict) or not order.get("status"):
                malformed = True
                continue
            if str(order["status"]).strip().lower() not in FINAL_ORDER_STATUSES:
                nonfinal = True
        checks["replacement_orders"] = {
            "passed": not nonfinal and not malformed,
            "has_nonfinal_order": nonfinal,
        }
        if nonfinal:
            blockers.append("A pending replacement-card order blocks closure.")
        if malformed:
            blockers.append("Replacement-order results are incomplete or ambiguous.")

    if blockers:
        return {"next_stage": "blocked", "blockers": blockers, "checks": checks}

    history = payload.get("prior_closure_history")
    if history is None or history not in (True, False):
        return {"next_stage": "check_prior_closure_history", "blockers": [], "checks": checks}
    if history is True:
        return {
            "next_stage": "ready_to_close",
            "blockers": [],
            "checks": checks,
            "retention_skipped": "prior closure-reason history within one year",
        }

    reason = payload.get("closure_reason")
    if reason not in VALID_REASONS:
        return {"next_stage": "obtain_and_log_closure_reason", "blockers": [], "checks": checks}
    if payload.get("reason_logged") is not True:
        return {
            "next_stage": "log_closure_reason",
            "blockers": [],
            "checks": checks,
            "closure_reason": reason,
        }

    if reason == "found_better_card":
        concern_explored = payload.get("concern_explored") is True
        comparable_available = payload.get("alternative_product_available") is True
        alternative_offered = payload.get("alternative_offered") is True
        checks["found_better_card_concern"] = {
            "asked_about_attracting_features": concern_explored,
            "comparable_product_available": comparable_available,
            "alternative_help_offered": alternative_offered,
        }
        if not concern_explored:
            return {
                "next_stage": "explore_competing_card_features",
                "blockers": [],
                "checks": checks,
                "closure_reason": reason,
                "customer_prompt": "Which rewards, features, or benefits of the other card are most attractive to you?",
            }
        if comparable_available and not alternative_offered:
            return {
                "next_stage": "offer_comparable_rho_bank_alternative",
                "blockers": [],
                "checks": checks,
                "closure_reason": reason,
            }

    state = payload.get("retention_state", "not_offered")
    tier = account.get("card_tier")
    offer = OFFERS.get(tier)
    if state == "accepted":
        return {
            "next_stage": "retain_account",
            "blockers": [],
            "checks": checks,
            "closure_reason": reason,
        }
    if state != "declined":
        result = {
            "next_stage": "make_one_retention_offer",
            "blockers": [],
            "checks": checks,
            "closure_reason": reason,
        }
        if offer:
            result["retention_offer"] = offer
        else:
            result["required_data"] = "Determine the card tier before making a tier-based offer."
        return result
    return {
        "next_stage": "ready_to_close",
        "blockers": [],
        "checks": checks,
        "closure_reason": reason,
        "retention_offer_declined": True,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"next_stage": "invalid_input", "blockers": [str(exc)], "checks": {}}))
