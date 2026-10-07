#!/usr/bin/env python3
"""Deterministic calculations for credit-limit-increase eligibility.

Read one JSON object from stdin and emit one JSON object. This utility is advisory:
callers must retrieve and interpret authoritative banking records themselves.
"""
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RULES = {
    "entry-tier": {"age_days": 120, "cooldown_days": 120, "utilization_lt": Decimal("70"), "payment_months": 6, "max_fraction": Decimal("0.25")},
    "mid-tier": {"age_days": 90, "cooldown_days": 90, "utilization_lt": Decimal("80"), "payment_months": 3, "max_fraction": Decimal("0.50")},
    "premium-tier": {"age_days": 60, "cooldown_days": 60, "utilization_lt": Decimal("90"), "payment_months": 3, "max_fraction": Decimal("0.50")},
}


def decimal_value(value, field, errors):
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError):
        errors.append("%s must be a finite number" % field)
        return None


def parse_date(value, field, errors):
    if value is None or value == "":
        return None
    text = str(value).strip()
    # Timezone labels such as EST are review labels; date arithmetic here is calendar-based.
    for suffix in (" EST", " EDT", " UTC"):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            break
    formats = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    errors.append("%s is not a supported date/time" % field)
    return None


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"errors": ["invalid JSON input: %s" % exc]}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"errors": ["input must be a JSON object"]}))
        return

    errors = []
    tier = str(payload.get("tier", "")).strip().lower()
    rule = RULES.get(tier)
    if rule is None:
        errors.append("tier must be entry-tier, mid-tier, or premium-tier")

    limit = decimal_value(payload.get("current_credit_limit"), "current_credit_limit", errors)
    requested = decimal_value(payload.get("requested_increase"), "requested_increase", errors)
    if limit is not None and limit <= 0:
        errors.append("current_credit_limit must be greater than zero")
    if requested is not None and requested <= 0:
        errors.append("requested_increase must be greater than zero")

    result = {
        "tier": tier or None,
        "errors": errors,
        "amount_within_limit": None,
        "maximum_increase": None,
        "new_credit_limit": None,
        "minimum_account_age_days": None,
        "cooldown_days": None,
        "utilization_must_be_below_percent": None,
        "required_on_time_payment_months": None,
        "account_age_eligible": None,
        "cooldown_eligible": None,
        "next_cooldown_eligibility_at": None,
        "utilization_percent": None,
        "utilization_eligible": None,
    }
    if rule is None:
        print(json.dumps(result, sort_keys=True))
        return

    result.update({
        "minimum_account_age_days": rule["age_days"],
        "cooldown_days": rule["cooldown_days"],
        "utilization_must_be_below_percent": str(rule["utilization_lt"]),
        "required_on_time_payment_months": rule["payment_months"],
    })
    if limit is not None and limit > 0:
        maximum = limit * rule["max_fraction"]
        result["maximum_increase"] = money(maximum)
        if requested is not None and requested > 0:
            result["amount_within_limit"] = requested <= maximum
            result["new_credit_limit"] = money(limit + requested)

    now = parse_date(payload.get("now"), "now", errors) if payload.get("now") is not None else None
    opened = parse_date(payload.get("account_open_date"), "account_open_date", errors) if payload.get("account_open_date") is not None else None
    if now is not None and opened is not None:
        result["account_age_eligible"] = now.date() >= (opened.date() + timedelta(days=rule["age_days"]))

    approved_at = parse_date(payload.get("last_approved_submission_at"), "last_approved_submission_at", errors) if payload.get("last_approved_submission_at") is not None else None
    if approved_at is None and payload.get("last_approved_submission_at") is None:
        # No approved request is a passing cooldown condition, not missing data.
        result["cooldown_eligible"] = True
    elif approved_at is not None:
        eligible_at = approved_at + timedelta(days=rule["cooldown_days"])
        result["next_cooldown_eligibility_at"] = eligible_at.strftime("%Y-%m-%d %H:%M:%S")
        if now is not None:
            result["cooldown_eligible"] = now >= eligible_at

    utilization = None
    if payload.get("utilization_percent") is not None:
        utilization = decimal_value(payload.get("utilization_percent"), "utilization_percent", errors)
    elif payload.get("current_balance") is not None and limit is not None and limit > 0:
        balance = decimal_value(payload.get("current_balance"), "current_balance", errors)
        if balance is not None:
            utilization = balance / limit * Decimal("100")
    if utilization is not None:
        result["utilization_percent"] = format(utilization.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")
        result["utilization_eligible"] = utilization < rule["utilization_lt"]

    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
