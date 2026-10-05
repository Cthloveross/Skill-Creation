#!/usr/bin/env python3
"""Assess normalized CLI facts from stdin; emit an auditable JSON plan to stdout."""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

POLICY = {
    "entry-tier": {"age": 120, "cooldown": 120, "util": Decimal("70"), "payments": 6, "max_fraction": Decimal("0.25")},
    "mid-tier": {"age": 90, "cooldown": 90, "util": Decimal("80"), "payments": 3, "max_fraction": Decimal("0.50")},
    "premium-tier": {"age": 60, "cooldown": 60, "util": Decimal("90"), "payments": 3, "max_fraction": Decimal("0.50")},
}
FINAL_ORDER = [
    ("account_age", "insufficient_account_age"),
    ("cooldown", "cooldown_period_active"),
    ("disputes", "pending_disputes"),
    ("replacement_orders", "pending_replacement_card"),
    ("good_standing", "past_due_balance"),
    ("utilization", "high_utilization"),
    ("payment_history", "insufficient_payment_history"),
]
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}
FINAL_DISPUTE_STATUSES = {"closed", "resolved", "cancelled", "canceled", "denied", "withdrawn"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    for candidate in (value[:10], value):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def result(status, detail, **extra):
    output = {"status": status, "detail": detail}
    output.update(extra)
    return output


def main(data):
    tier = str(data.get("card_tier", "")).strip().lower()
    if tier not in POLICY:
        return {"error": "unsupported_or_missing_card_tier", "supported_tiers": sorted(POLICY)}
    p = POLICY[tier]
    now = parse_date(data.get("current_date"))
    limit = decimal(data.get("current_credit_limit"))
    requested_raw = data.get("requested_increase_amount")
    requested = decimal(requested_raw)
    requested_is_integer = (isinstance(requested_raw, int) and not isinstance(requested_raw, bool))
    maximum = limit * p["max_fraction"] if limit is not None and limit >= 0 else None

    if not requested_is_integer or requested is None or requested <= 0:
        return {
            "error": "requested_increase_must_be_a_positive_integer_dollar_amount",
            "pre_submission_action": "obtain_valid_amount",
        }
    if maximum is None:
        return {"error": "missing_or_invalid_current_credit_limit", "pre_submission_action": "obtain_current_limit"}
    if requested > maximum:
        return {
            "card_tier": tier,
            "maximum_increase": float(maximum),
            "requested_increase_amount": int(requested),
            "pre_submission_action": "request_adjustment",
            "final_decision": "not_submitted",
            "denial_reason_if_submitted": "requested_amount_exceeds_limit",
        }

    checks = {}
    opened = parse_date(data.get("account_open_date"))
    if now is None or opened is None:
        checks["account_age"] = result("unknown", "current_date or account_open_date is missing or invalid")
    else:
        eligible_on = opened + timedelta(days=p["age"])
        checks["account_age"] = result("pass" if now >= eligible_on else "fail", "minimum account age evaluated", eligible_on=eligible_on.isoformat())

    history = data.get("history")
    if not isinstance(history, list) or now is None:
        checks["cooldown"] = result("unknown", "approved-request history or current_date is unavailable")
    else:
        approved_dates = [parse_date(x.get("submitted_at")) for x in history if isinstance(x, dict) and str(x.get("status", "")).lower() == "approved"]
        approved_dates = [d for d in approved_dates if d]
        if not approved_dates:
            checks["cooldown"] = result("pass", "no prior approved request with a parseable submission date")
        else:
            latest = max(approved_dates)
            eligible_on = latest + timedelta(days=p["cooldown"])
            checks["cooldown"] = result("pass" if now >= eligible_on else "fail", "cooldown evaluated from latest approved submission", latest_approved_submission=latest.isoformat(), eligible_on=eligible_on.isoformat())

    disputes = data.get("disputes")
    if not isinstance(disputes, list):
        checks["disputes"] = result("unknown", "dispute results unavailable")
    else:
        active = [str(x.get("status", "")).lower() for x in disputes if not isinstance(x, dict) or str(x.get("status", "")).lower() not in FINAL_DISPUTE_STATUSES]
        checks["disputes"] = result("fail" if active else "pass", "active or ambiguous disputes block processing" if active else "all disputes are final", blocking_statuses=active)

    orders = data.get("replacement_orders")
    if not isinstance(orders, list):
        checks["replacement_orders"] = result("unknown", "replacement-order results unavailable")
    else:
        blocking = [str(x.get("status", "")).lower() for x in orders if not isinstance(x, dict) or str(x.get("status", "")).lower() not in FINAL_REPLACEMENT_STATUSES]
        checks["replacement_orders"] = result("fail" if blocking else "pass", "non-final replacement orders block processing" if blocking else "no non-final replacement orders", blocking_statuses=blocking)

    past_due = data.get("is_past_due")
    if not isinstance(past_due, bool):
        checks["good_standing"] = result("unknown", "explicit past-due/current-standing evidence unavailable")
    else:
        checks["good_standing"] = result("fail" if past_due else "pass", "account has past-due balance" if past_due else "account is current")

    balance = decimal(data.get("current_balance"))
    if balance is None or limit <= 0:
        checks["utilization"] = result("unknown", "current balance or positive credit limit unavailable")
    else:
        utilization = balance / limit * Decimal("100")
        checks["utilization"] = result("pass" if utilization < p["util"] else "fail", "utilization is strictly below threshold" if utilization < p["util"] else "utilization is at or above threshold", utilization_percent=float(utilization), threshold_percent=float(p["util"]))

    months = data.get("consecutive_on_time_months")
    if not isinstance(months, int) or isinstance(months, bool) or months < 0:
        checks["payment_history"] = result("unknown", "consecutive on-time payment count unavailable")
    else:
        checks["payment_history"] = result("pass" if months >= p["payments"] else "fail", "required consecutive on-time payment months evaluated", required_months=p["payments"], observed_months=months)

    failed = [key for key, _ in FINAL_ORDER if checks[key]["status"] == "fail"]
    unknown = [key for key, _ in FINAL_ORDER if checks[key]["status"] == "unknown"]
    if failed:
        reason = next(reason for key, reason in FINAL_ORDER if key == failed[0])
        decision = "deny"
    elif unknown:
        reason = "other"
        decision = "deny"
    else:
        reason = None
        decision = "approve"
    out = {
        "card_tier": tier,
        "maximum_increase": float(maximum),
        "requested_increase_amount": int(requested),
        "pre_submission_action": "submit_then_assess",
        "checks": checks,
        "final_decision": decision,
        "denial_reason": reason,
        "failed_checks": failed,
        "unknown_checks": unknown,
    }
    if decision == "approve":
        out["new_credit_limit"] = float(limit + requested)
    return out


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        sys.exit(1)
