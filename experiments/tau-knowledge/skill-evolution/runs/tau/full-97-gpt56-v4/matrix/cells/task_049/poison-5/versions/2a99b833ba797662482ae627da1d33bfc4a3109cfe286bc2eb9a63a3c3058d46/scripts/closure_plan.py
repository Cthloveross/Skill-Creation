"""Produce a deterministic, non-executing closure workflow checklist.

Input: one JSON object described in SKILL.md.
Output: one JSON object with validation errors, eligibility conditions, blockers,
        and a next workflow stage. This script never calls banking tools.
"""
import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation

FINAL_ORDER_STATUSES = {"delivered", "cancelled", "canceled"}
MID_TIER = {
    "Silver Rewards Card", "Business Silver Rewards Card", "Green Rewards Card",
    "Silver Zoom Card",
}
ENTRY_TIER = {
    "Bronze Rewards Card", "EcoCard", "Business Bronze Rewards Card",
    "Crypto-Cash Back Card",
}
PREMIUM_PLUS = {
    "Gold Rewards Card", "Business Gold Rewards Card", "Platinum Rewards Card",
    "Business Platinum Rewards Card", "Diamond Elite Card",
}
VALID_REASONS = {
    "annual_fee", "not_using_card", "found_better_card", "unhappy_with_rewards",
    "simplifying_finances", "negative_experience", "other",
}


def parse_date(value):
    if not isinstance(value, str):
        return None
    # The first date in a timestamp is sufficient for age calculations.
    match = re.search(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", value)
    if not match:
        return None
    text = match.group(0)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def parse_money(value):
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.replace("$", "").replace(",", "").strip()
    else:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def card_tier(card_type):
    if card_type in ENTRY_TIER:
        return "entry"
    if card_type in MID_TIER:
        return "mid"
    if card_type in PREMIUM_PLUS:
        return "premium_plus"
    return None


def order_state(orders):
    """Return pass/block/unknown without assuming undocumented response shapes."""
    if orders is None:
        return "unknown"
    if not isinstance(orders, list):
        return "unknown"
    for order in orders:
        status = order.get("status") if isinstance(order, dict) else order
        if not isinstance(status, str) or status.strip().lower() not in FINAL_ORDER_STATUSES:
            return "block"
    return "pass"


def add_condition(conditions, name, status, detail):
    conditions.append({"requirement": name, "status": status, "detail": detail})


def main(data):
    if not isinstance(data, dict):
        return {"ok": False, "errors": ["Input must be a JSON object."]}

    errors = []
    account = data.get("account")
    if not isinstance(account, dict):
        account = {}
        errors.append("account must be an object containing current account data.")

    conditions = []
    blockers = []
    missing = []
    confirmed = data.get("identity_confirmed_fields", [])
    if not isinstance(confirmed, list):
        confirmed = []
        errors.append("identity_confirmed_fields must be an array.")
    confirmed_set = {x for x in confirmed if x in {"date_of_birth", "email", "phone_number", "address"}}
    identity_status = "pass" if len(confirmed_set) >= 2 else "block"
    add_condition(conditions, "two matching identity fields", identity_status,
                  "%d accepted fields supplied" % len(confirmed_set))
    if identity_status == "block":
        blockers.append("Obtain and match at least two identity fields, then log verification.")

    balance = parse_money(account.get("current_balance"))
    if balance is None:
        add_condition(conditions, "zero outstanding balance", "unknown", "No parseable current balance.")
        missing.append("current balance")
    elif balance == Decimal("0"):
        add_condition(conditions, "zero outstanding balance", "pass", "Balance is zero.")
    else:
        add_condition(conditions, "zero outstanding balance", "block", "Balance is not zero.")
        blockers.append("Outstanding balance must be paid to $0.00.")

    now_date = parse_date(data.get("now"))
    open_date = parse_date(account.get("date_of_account_open"))
    if now_date is None or open_date is None:
        add_condition(conditions, "account open at least 60 days", "unknown", "Need valid current and opening dates.")
        missing.append("account age dates")
    else:
        age_days = (now_date - open_date).days
        if age_days >= 60:
            add_condition(conditions, "account open at least 60 days", "pass", "%d days open" % age_days)
        else:
            add_condition(conditions, "account open at least 60 days", "block", "%d days open" % age_days)
            blockers.append("Account must be open for at least 60 days.")

    disputes = data.get("pending_disputes")
    if disputes is False:
        add_condition(conditions, "no pending disputes", "pass", "Confirmed no pending disputes.")
    elif disputes is True:
        add_condition(conditions, "no pending disputes", "block", "A pending dispute exists.")
        blockers.append("Pending disputes must be resolved before closure.")
    else:
        add_condition(conditions, "no pending disputes", "unknown", "Dispute status has not been confirmed.")
        missing.append("pending-dispute status")

    replacement = order_state(data.get("replacement_orders"))
    if replacement == "pass":
        add_condition(conditions, "no pending replacement cards", "pass", "No non-final replacement order found.")
    elif replacement == "block":
        add_condition(conditions, "no pending replacement cards", "block", "At least one order is non-final or ambiguous.")
        blockers.append("All replacement orders must be delivered or cancelled.")
    else:
        add_condition(conditions, "no pending replacement cards", "unknown", "Replacement-order tool result is required.")
        missing.append("replacement-order status")

    eligibility_pass = not blockers and not missing
    tier = card_tier(account.get("card_type"))
    offer = {"entry": "500 bonus points or a $5 statement credit",
             "mid": "2,000 bonus points or a $20 statement credit",
             "premium_plus": "5,000 bonus points or a $50 statement credit"}.get(tier)
    history = data.get("prior_closure_history")
    history_known = isinstance(history, dict) and history.get("known") is True and isinstance(history.get("has_records_past_year"), bool)
    reason = data.get("closure_reason")
    decision = data.get("retention_decision")

    stage = "resolve_eligibility"
    if eligibility_pass:
        if not history_known:
            stage = "check_prior_closure_history"
            missing.append("prior closure-reason history")
        elif history["has_records_past_year"]:
            stage = "ready_to_close"
        elif reason not in VALID_REASONS:
            stage = "obtain_and_log_closure_reason"
            missing.append("valid closure reason")
        elif decision in (None, "pending"):
            stage = "make_retention_offer_and_wait"
        elif decision == "accepted":
            stage = "retention_accepted_do_not_close"
        elif decision == "declined":
            stage = "ready_to_close"
        else:
            stage = "confirm_retention_decision"
            missing.append("valid retention decision")

    reward_value = None
    points = account.get("reward_points")
    try:
        if points is not None:
            reward_value = str((Decimal(str(points)) * Decimal("0.01")).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        errors.append("reward_points was not numeric; no reward value was calculated.")

    return {
        "ok": not errors,
        "errors": errors,
        "account_id_present": bool(account.get("account_id")),
        "card_tier": tier,
        "retention_offer": offer,
        "reward_cash_value_dollars": reward_value,
        "eligibility_conditions": conditions,
        "eligible_to_close": eligibility_pass,
        "blockers": blockers,
        "missing_or_unconfirmed": missing,
        "prior_history_skips_retention": bool(history_known and history["has_records_past_year"]),
        "workflow_stage": stage,
        "final_action_guard": "Before a close call, recheck replacement orders immediately and require workflow_stage == ready_to_close."
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: " + str(exc)]}))
