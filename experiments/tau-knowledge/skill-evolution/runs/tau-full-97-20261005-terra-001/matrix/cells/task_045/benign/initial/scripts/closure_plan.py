#!/usr/bin/env python3
"""Assess documented credit-card closure prerequisites from JSON stdin.

This script is intentionally side-effect free. It accepts the schema documented in
SKILL.md and writes one JSON object to stdout.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}
DATE_FORMATS = (
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S %Z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
)


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty date string")
    text = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError(f"{field} has an unsupported date format: {value!r}") from exc


def money(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"current_balance is not a valid amount: {value!r}") from exc
    raise ValueError("current_balance must be a number or money string")


def check(status, detail):
    return {"status": status, "detail": detail}


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    current_day = parse_date(payload.get("current_time"), "current_time")
    account = payload.get("account")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")
    for key in ("account_id", "user_id", "card_type", "date_of_account_open", "current_balance"):
        if not account.get(key) and account.get(key) != 0:
            raise ValueError(f"account.{key} is required")

    checks = {}
    blockers = []
    steps = []

    if payload.get("identity_verified") is True:
        checks["identity"] = check("pass", "Identity is marked verified.")
    else:
        checks["identity"] = check("fail", "Verify two identity fields and log verification before account actions.")
        blockers.append("Identity verification has not been completed.")
        steps.append("Obtain two customer-confirmed identity fields and create the verification log.")

    opened = parse_date(account["date_of_account_open"], "account.date_of_account_open")
    age_days = (current_day - opened).days
    if age_days < 0:
        checks["account_age"] = check("unknown", "Account-open date is after the supplied current date.")
        blockers.append("Account age cannot be confirmed from the supplied dates.")
    elif age_days >= 60:
        checks["account_age"] = check("pass", f"Account age is {age_days} days (minimum is 60).")
    else:
        checks["account_age"] = check("fail", f"Account age is {age_days} days; it must be at least 60 days.")
        blockers.append("The account has not been open for at least 60 days.")

    balance = money(account["current_balance"])
    if balance == Decimal("0"):
        checks["balance"] = check("pass", "Outstanding balance is $0.00.")
    elif balance > 0:
        checks["balance"] = check("fail", f"Outstanding balance is ${balance:.2f}; it must be paid to $0.00.")
        blockers.append("The outstanding balance must be paid in full and confirmed as posted.")
        steps.append("If requested and authorized, arrange an eligible checking-to-card payment, then re-check the card balance.")
    else:
        checks["balance"] = check("unknown", "A negative balance requires review; zero-balance eligibility is not confirmed.")
        blockers.append("The balance is not exactly $0.00 and requires review.")

    dispute = payload.get("dispute_check")
    if not isinstance(dispute, dict) or dispute.get("performed") is not True:
        checks["disputes"] = check("unknown", "Target-account dispute check has not been completed.")
        blockers.append("Active or pending disputes for the target account have not been ruled out.")
        steps.append("Review dispute history and reliably associate any active disputes with the target account.")
    elif dispute.get("active_for_target") is True:
        checks["disputes"] = check("fail", "The target account has an active or pending dispute.")
        blockers.append("All active or pending target-account disputes must be resolved before closure.")
    elif dispute.get("active_for_target") is False:
        checks["disputes"] = check("pass", "No active or pending disputes are reported for the target account.")
    else:
        checks["disputes"] = check("unknown", "Dispute result is ambiguous for the target account.")
        blockers.append("Target-account dispute status is ambiguous.")

    replacement = payload.get("replacement_check")
    if not isinstance(replacement, dict) or replacement.get("performed") is not True:
        checks["replacement_orders"] = check("unknown", "Replacement-order check has not been completed immediately before closure.")
        blockers.append("Pending replacement-card orders have not been ruled out.")
        steps.append("Immediately before closure, check replacement orders for the target account.")
    elif not isinstance(replacement.get("orders"), list):
        checks["replacement_orders"] = check("unknown", "Replacement-order response does not contain an orders list.")
        blockers.append("Replacement-card order result is ambiguous.")
    else:
        nonfinal = []
        for order in replacement["orders"]:
            status = order.get("status") if isinstance(order, dict) else None
            normalized = str(status).strip().lower() if status is not None else "unknown"
            if normalized not in FINAL_REPLACEMENT_STATUSES:
                nonfinal.append(normalized)
        if nonfinal:
            checks["replacement_orders"] = check("fail", "Non-final replacement order status(es): " + ", ".join(nonfinal) + ".")
            blockers.append("A replacement card must be delivered or cancelled before closure.")
        else:
            checks["replacement_orders"] = check("pass", "No pending or shipped replacement-card orders are reported.")

    required = ("identity", "account_age", "balance", "disputes", "replacement_orders")
    closure_ready = all(checks[name]["status"] == "pass" for name in required)

    history = payload.get("history_check")
    retention = {"status": "not_applicable", "detail": "Complete eligibility checks before retention handling."}
    if closure_ready:
        if not isinstance(history, dict) or history.get("performed") is not True:
            retention = {"status": "required", "detail": "Check prior closure-reason records within the past year before making an offer."}
            steps.append("Check closure-reason history for this account before retention handling.")
        elif history.get("records_within_past_year") is True:
            retention = {"status": "skip_offers", "detail": "Prior closure-reason record exists within the past year; skip retention offers."}
            steps.append("Proceed to closure if the customer still confirms the request.")
        elif history.get("records_within_past_year") is False:
            retention = {"status": "offer_flow", "detail": "Log the reason, address it, and make one appropriate retention offer if the customer still wants closure."}
            steps.append("Log the approved closure reason and follow the one-offer retention flow.")
        else:
            retention = {"status": "unknown", "detail": "Prior-attempt history result is ambiguous."}
            steps.append("Resolve the prior closure-reason history result before retention handling.")

    rewards = {"status": "unknown", "detail": "Reward balance was not supplied."}
    points = account.get("reward_points")
    if points is not None:
        try:
            point_value = Decimal(str(points))
            if point_value < 0:
                raise InvalidOperation
            rewards = {
                "status": "info",
                "points": str(point_value),
                "estimated_redemption_value_dollars": f"{(point_value * Decimal('0.01')):.2f}",
                "detail": "Remaining rewards may be redeemed for 45 days after the closure request; they are forfeited afterward.",
            }
        except (InvalidOperation, ValueError):
            rewards = {"status": "unknown", "detail": "Reward-points value is invalid; verify it before quoting a value."}

    fee = {"status": "unknown", "detail": "Annual-fee posting date was not supplied; do not promise a refund."}
    if account.get("annual_fee_posted_date"):
        posted = parse_date(account["annual_fee_posted_date"], "account.annual_fee_posted_date")
        elapsed = (current_day - posted).days
        if 0 <= elapsed <= 37:
            fee = {"status": "potentially_eligible", "days_since_posting": elapsed, "detail": "Closure is within 37 days of the supplied fee posting; a full refund may apply."}
        else:
            fee = {"status": "not_eligible_by_date", "days_since_posting": elapsed, "detail": "The supplied fee-posting date is outside the 37-day full-refund window."}

    return {
        "ok": True,
        "account_id": account["account_id"],
        "user_id": account["user_id"],
        "closure_ready": closure_ready,
        "checks": checks,
        "blockers": blockers,
        "recommended_next_steps": steps,
        "retention": retention,
        "rewards": rewards,
        "annual_fee_refund": fee,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
