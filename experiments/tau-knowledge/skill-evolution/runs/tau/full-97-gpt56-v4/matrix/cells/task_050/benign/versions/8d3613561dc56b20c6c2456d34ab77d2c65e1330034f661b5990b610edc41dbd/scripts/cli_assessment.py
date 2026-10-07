#!/usr/bin/env python3
"""Conservative deterministic CLI calculation helper.
Reads one JSON object from stdin and writes one JSON report to stdout.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

RULES = {
    "entry": {"age": 120, "cooldown": 120, "util": Decimal("70"), "payments": 6, "cap": Decimal("0.25")},
    "mid": {"age": 90, "cooldown": 90, "util": Decimal("80"), "payments": 3, "cap": Decimal("0.50")},
    "premium": {"age": 60, "cooldown": 60, "util": Decimal("90"), "payments": 3, "cap": Decimal("0.50")},
}


def d(value):
    return Decimal(str(value))


def date_of(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def status_pass_or_unknown(data, key, predicate):
    if key not in data:
        return "unknown"
    return "pass" if predicate(data[key]) else "fail"


def main(data):
    tier = str(data.get("tier", "")).strip().lower().replace("-tier", "")
    if tier not in RULES:
        return {"error": "tier must be entry, mid, or premium; do not infer it from a card name"}
    rule = RULES[tier]
    try:
        limit, requested = d(data["current_limit"]), d(data["requested_increase"])
        opened, today = date_of(data["opened_on"]), date_of(data["now"])
    except (KeyError, ValueError, InvalidOperation) as exc:
        return {"error": "invalid required input: %s" % exc}
    if limit <= 0 or requested <= 0:
        return {"error": "current_limit and requested_increase must both be positive"}

    maximum = limit * rule["cap"]
    checks = {}
    checks["account_age"] = "pass" if today >= opened + timedelta(days=rule["age"]) else "fail"

    if "history" not in data:
        checks["cooldown"] = "unknown"
    else:
        approved_dates = []
        malformed = False
        for item in data["history"] or []:
            if str(item.get("outcome", item.get("status", ""))).lower() == "approved":
                try:
                    approved_dates.append(date_of(item.get("submitted_at", item.get("request_date"))))
                except (ValueError, TypeError):
                    malformed = True
        if malformed:
            checks["cooldown"] = "unknown"
        elif not approved_dates or today >= max(approved_dates) + timedelta(days=rule["cooldown"]):
            checks["cooldown"] = "pass"
        else:
            checks["cooldown"] = "fail"

    final_dispute = {"closed", "resolved", "cancelled", "denied"}
    if "disputes" not in data:
        checks["disputes"] = "unknown"
    else:
        statuses = [str(x.get("status", "")).lower() for x in (data["disputes"] or [])]
        checks["disputes"] = "pass" if all(s in final_dispute for s in statuses) else ("unknown" if "" in statuses else "fail")

    final_order = {"delivered", "cancelled"}
    if "replacement_orders" not in data:
        checks["replacement_orders"] = "unknown"
    else:
        statuses = [str(x.get("status", "")).lower() for x in (data["replacement_orders"] or [])]
        checks["replacement_orders"] = "pass" if all(s in final_order for s in statuses) else ("unknown" if "" in statuses else "fail")

    if "account_current" not in data or "past_due_amount" not in data:
        checks["good_standing"] = "unknown"
    else:
        try:
            checks["good_standing"] = "pass" if bool(data["account_current"]) and d(data["past_due_amount"]) <= 0 else "fail"
        except InvalidOperation:
            checks["good_standing"] = "unknown"

    if "balance" not in data:
        checks["utilization"] = "unknown"
        utilization = None
    else:
        try:
            utilization = d(data["balance"]) / limit * Decimal("100")
            checks["utilization"] = "pass" if utilization < rule["util"] else "fail"
        except InvalidOperation:
            utilization = None
            checks["utilization"] = "unknown"

    if "payment_months" not in data:
        checks["payment_history"] = "unknown"
    else:
        payments = data["payment_months"] or []
        on_time = len(payments) >= rule["payments"] and all(
            str(x.get("status", "")).lower() in {"on_time", "paid_on_time"}
            for x in payments[:rule["payments"]]
        )
        checks["payment_history"] = "pass" if on_time else "fail"

    return {
        "tier": tier,
        "maximum_increase": str(maximum),
        "requested_increase": str(requested),
        "amount_within_limit": requested <= maximum,
        "new_credit_limit_if_approved": str(limit + requested),
        "utilization_percent": None if utilization is None else str(utilization),
        "requirements": {"minimum_age_days": rule["age"], "cooldown_days": rule["cooldown"], "utilization_must_be_below_percent": str(rule["util"]), "on_time_months": rule["payments"]},
        "checks": checks,
        "decision_ready_for_approval": requested <= maximum and all(v == "pass" for v in checks.values()),
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
