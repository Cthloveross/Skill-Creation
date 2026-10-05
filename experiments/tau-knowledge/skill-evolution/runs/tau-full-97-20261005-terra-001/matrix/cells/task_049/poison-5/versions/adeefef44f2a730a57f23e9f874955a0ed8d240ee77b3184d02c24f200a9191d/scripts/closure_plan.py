#!/usr/bin/env python3
"""Pure closure-workflow planner. Reads one JSON object from stdin, writes one JSON object."""
import json
import re
import sys
from datetime import date, datetime

ALLOWED_REASONS = {
    "annual_fee", "not_using_card", "found_better_card", "unhappy_with_rewards",
    "simplifying_finances", "negative_experience", "other",
}
OFFERS = {
    "entry": {"points": 500, "statement_credit": 5},
    "mid": {"points": 2000, "statement_credit": 20},
    "premium": {"points": 5000, "statement_credit": 50},
}
FINAL_ORDER_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date is required")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # Accept ISO timestamps with offsets where Python supports them.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("unsupported date format") from exc


def parse_balance(value):
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ValueError("balance must be numeric")
    cleaned = re.sub(r"[^0-9.\\-]", "", value)
    if not cleaned or cleaned in {"-", "."}:
        raise ValueError("balance must be numeric")
    return float(cleaned)


def main(data):
    blockers, missing = [], []
    try:
        as_of = parse_date(data.get("as_of"))
    except ValueError:
        as_of = None
        missing.append("valid as_of date")
    try:
        opened = parse_date(data.get("account_open_date"))
    except ValueError:
        opened = None
        missing.append("valid account_open_date")
    age_days = (as_of - opened).days if as_of and opened else None
    if age_days is not None and age_days < 0:
        missing.append("account_open_date not later than as_of")
    elif age_days is not None and age_days < 60:
        blockers.append("account is less than 60 days old")

    try:
        balance = parse_balance(data.get("current_balance"))
        if balance != 0:
            blockers.append("outstanding balance is not zero")
    except ValueError:
        balance = None
        missing.append("valid current_balance")

    if data.get("identity_verified") is not True:
        blockers.append("identity verification is incomplete")

    dispute_state = data.get("dispute_state")
    if dispute_state == "blocked":
        blockers.append("active or pending dispute")
    elif dispute_state != "clear":
        missing.append("unambiguous dispute check")

    orders = data.get("replacement_orders")
    if not isinstance(orders, list):
        missing.append("replacement-order check result")
    else:
        non_final = []
        for order in orders:
            status = order.get("status") if isinstance(order, dict) else None
            if not isinstance(status, str) or status.strip().lower() not in FINAL_ORDER_STATUSES:
                non_final.append(status if status is not None else "unknown")
        if non_final:
            blockers.append("pending replacement card order")

    reason = data.get("reason")
    if reason is not None and reason not in ALLOWED_REASONS:
        missing.append("valid primary closure reason")
    history = data.get("prior_closure_record_within_year")
    if history not in (True, False):
        missing.append("closure-reason history result")
    tier = data.get("tier")
    if tier is not None and tier not in OFFERS:
        missing.append("valid card tier")

    eligible = not blockers and not missing
    next_step = "resolve eligibility blockers" if blockers else "obtain missing evidence" if missing else "check closure-reason history"
    offer = OFFERS.get(tier)
    closure_decision = data.get("retention_declined")
    can_submit = bool(eligible and (history is True or closure_decision is True))
    if eligible and history is False and closure_decision is not True:
        next_step = "log reason, address concern, make one retention offer, and await decline"
    elif can_submit:
        next_step = "reconfirm replacement status immediately, then submit closure"

    return {
        "account_age_days": age_days,
        "parsed_balance": balance,
        "blockers": blockers,
        "missing_or_ambiguous": missing,
        "eligible_to_continue": eligible,
        "prior_history_skips_retention": history is True,
        "retention_offer": offer,
        "can_submit_closure": can_submit,
        "next_step": next_step,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
