#!/usr/bin/env python3
"""Assess documented evidence for a credit-card closure workflow.

Reads one JSON object from stdin and writes one JSON object to stdout. It makes no
network or banking-tool calls.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}
FINAL_DISPUTE_STATUSES = {"closed", "resolved", "withdrawn", "cancelled"}
VALID_REASONS = {
    "annual_fee",
    "not_using_card",
    "found_better_card",
    "unhappy_with_rewards",
    "simplifying_finances",
    "negative_experience",
    "other",
}
OFFERS = {
    "entry": "500 bonus points or a $5 statement credit",
    "mid": "2,000 bonus points or a $20 statement credit",
    "premium": "5,000 bonus points or a $50 statement credit",
}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be a date string.")
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    errors.append(f"{field} must use MM/DD/YYYY or YYYY-MM-DD.")
    return None


def parse_money(value, errors):
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        errors.append("account.current_balance must be a numeric or currency string.")
        return None
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        errors.append("account.current_balance is not a valid monetary amount.")
        return None


def as_object(value, field, errors):
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object.")
        return {}
    return value


def main(payload):
    errors = []
    blockers = []
    missing = []
    actions = []

    as_of = parse_date(payload.get("as_of"), "as_of", errors)
    account = as_object(payload.get("account"), "account", errors)
    authenticated_user_id = payload.get("authenticated_user_id")

    if payload.get("identity_verified") is not True:
        missing.append("Successful two-factor identity verification is not evidenced.")
    if payload.get("verification_logged") is not True:
        missing.append("The required verification audit record has not been logged.")

    account_id = account.get("account_id")
    account_user_id = account.get("user_id")
    if not isinstance(account_id, str) or not account_id:
        missing.append("A selected credit_card_account_id is required.")
    if not isinstance(authenticated_user_id, str) or not authenticated_user_id:
        missing.append("The authenticated user_id is required.")
    elif not isinstance(account_user_id, str) or not account_user_id:
        missing.append("Selected account ownership evidence is required.")
    elif authenticated_user_id != account_user_id:
        missing.append("The selected account does not match the authenticated user.")

    balance = parse_money(account.get("current_balance"), errors)
    if balance is not None and balance != Decimal("0"):
        blockers.append("Outstanding balance must be exactly $0.00 before closure.")

    opened = parse_date(account.get("opened_on"), "account.opened_on", errors)
    age_days = None
    if opened is not None and as_of is not None:
        age_days = (as_of - opened).days
        if age_days < 0:
            errors.append("account.opened_on cannot be later than as_of.")
        elif age_days < 60:
            blockers.append("Account must be open for at least 60 days before closure.")

    disputes = as_object(payload.get("dispute_check"), "dispute_check", errors)
    if disputes.get("performed") is not True:
        missing.append("A current dispute-history check is required.")
    elif disputes.get("account_association_complete") is not True:
        missing.append("Dispute results are not completely associated to the selected account.")
    else:
        records = disputes.get("records", [])
        if not isinstance(records, list):
            errors.append("dispute_check.records must be an array.")
        else:
            for record in records:
                if not isinstance(record, dict):
                    errors.append("Each dispute record must be an object.")
                    continue
                belongs = record.get("belongs_to_selected_account")
                if belongs not in (True, False):
                    missing.append("Each dispute record needs explicit account association.")
                    continue
                if belongs is True:
                    status = record.get("status")
                    if not isinstance(status, str) or not status.strip():
                        missing.append("A selected-account dispute has no usable status.")
                    elif status.strip().lower() not in FINAL_DISPUTE_STATUSES:
                        blockers.append("Selected account has an active or pending dispute.")

    replacements = as_object(payload.get("replacement_check"), "replacement_check", errors)
    if replacements.get("performed") is not True:
        missing.append("A current pending-replacement-order check is required.")
    else:
        orders = replacements.get("orders", [])
        if not isinstance(orders, list):
            errors.append("replacement_check.orders must be an array.")
        else:
            for order in orders:
                if not isinstance(order, dict):
                    errors.append("Each replacement order must be an object.")
                    continue
                status = order.get("status")
                if not isinstance(status, str) or not status.strip():
                    missing.append("A replacement order has no usable status.")
                elif status.strip().lower() not in FINAL_REPLACEMENT_STATUSES:
                    blockers.append("Selected account has a pending replacement-card order.")

    retention = as_object(payload.get("retention", {}), "retention", errors)
    retention_guidance = {"next_step": "Complete eligibility evidence before retention processing."}
    workflow_missing = []
    closure_permitted = False

    eligibility_status = "eligible"
    if blockers:
        eligibility_status = "ineligible"
    elif missing or errors:
        eligibility_status = "needs_review"

    if eligibility_status == "eligible":
        if retention.get("history_checked") is not True:
            workflow_missing.append("Check closure-reason history for the selected account within the past year.")
            retention_guidance = {"next_step": "Call get_closure_reason_history_8293 before logging a reason or making an offer."}
        elif retention.get("prior_attempt_within_year") is True:
            retention_guidance = {
                "next_step": "Skip reason logging and retention offers; proceed if the customer still wants closure.",
                "retention_skipped": True,
            }
            closure_permitted = retention.get("customer_wants_close") is True
            if not closure_permitted:
                workflow_missing.append("Obtain the customer's current confirmation that they want closure.")
        elif retention.get("prior_attempt_within_year") is False:
            reason = retention.get("reason")
            tier = retention.get("card_tier")
            offer = OFFERS.get(tier)
            retention_guidance = {"retention_skipped": False, "offer": offer}
            if reason not in VALID_REASONS:
                workflow_missing.append("Obtain and map the closure reason to an allowed reason value.")
            if retention.get("reason_logged") is not True:
                workflow_missing.append("Log the valid closure reason before making a retention offer.")
            if offer is None:
                workflow_missing.append("Determine whether the card tier is entry, mid, or premium.")
            if retention.get("offer_presented") is not True:
                workflow_missing.append("Present exactly one applicable retention offer.")
            decision = retention.get("customer_decision")
            if decision == "accepted":
                retention_guidance["next_step"] = "Do not close while the customer accepts the retention outcome."
            elif decision == "declined" and retention.get("customer_wants_close") is True:
                closure_permitted = not workflow_missing
                retention_guidance["next_step"] = "Customer declined the offer; closure may proceed without pressure."
            else:
                workflow_missing.append("Obtain the customer's decision on the retention offer and closure request.")
        else:
            workflow_missing.append("The prior-attempt history result must explicitly state true or false.")

    if eligibility_status != "eligible":
        actions.append("Do not make a retention offer or call the closure tool.")
    elif not closure_permitted:
        actions.append("Complete the remaining retention workflow before calling the closure tool.")
    else:
        actions.append("The executor may call close_credit_card_account_7834 with the selected account ID and authenticated user ID.")

    return {
        "eligibility_status": eligibility_status,
        "eligibility_blockers": sorted(set(blockers)),
        "missing_evidence": sorted(set(missing)),
        "input_errors": errors,
        "account_age_days": age_days,
        "retention": retention_guidance,
        "workflow_missing": sorted(set(workflow_missing)),
        "closure_permitted": closure_permitted and eligibility_status == "eligible",
        "next_actions": actions,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON input must be an object.")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({
            "eligibility_status": "needs_review",
            "eligibility_blockers": [],
            "missing_evidence": [],
            "input_errors": [str(exc)],
            "closure_permitted": False,
            "next_actions": ["Provide a valid JSON evidence object and reassess before any closure action."],
        }, sort_keys=True))
