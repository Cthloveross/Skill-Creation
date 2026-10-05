#!/usr/bin/env python3
"""Assess published credit-card dispute and CLI rules without banking side effects.

Input: one JSON object on stdin. See SKILL.md for a runnable schema example.
Output: one JSON object on stdout. Monetary values are JSON strings to preserve cents.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MISSING = object()

PROVISIONAL_LIMITS = {
    "entry-tier": Decimal("2500.00"),
    "mid-tier": Decimal("5000.00"),
    "premium-tier": Decimal("10000.00"),
    "elite-tier": Decimal("15000.00"),
    "invitation-tier": Decimal("25000.00"),
}
CLI_RULES = {
    "entry-tier": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "payment_months": 6, "increase_fraction": Decimal("0.25")},
    "mid-tier": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "payment_months": 3, "increase_fraction": Decimal("0.50")},
    "premium-tier": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "payment_months": 3, "increase_fraction": Decimal("0.50")},
}
ALLOWED_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}

def parse_date(value, field, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a nonempty date string")
        return None
    value = value.strip()
    candidates = ["%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"]
    for fmt in candidates:
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            pass
    errors.append(f"{field} must use YYYY-MM-DD, MM/DD/YYYY, or an ISO timestamp")
    return None

def money(value, field, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return result

def fmt_money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")

def normalize_tier(account):
    supplied = str(account.get("tier", "")).strip().lower().replace("_", "-")
    aliases = {
        "entry": "entry-tier", "entry-tier": "entry-tier",
        "mid": "mid-tier", "mid-tier": "mid-tier",
        "premium": "premium-tier", "premium-tier": "premium-tier",
        "elite": "elite-tier", "elite-tier": "elite-tier",
        "invitation": "invitation-tier", "invitation-tier": "invitation-tier",
    }
    if supplied in aliases:
        return aliases[supplied]
    card = str(account.get("card_type", "")).lower()
    if any(x in card for x in ("bronze", "ecocard", "crypto-cash")):
        return "entry-tier"
    if any(x in card for x in ("silver", "green rewards", "silver zoom")):
        return "mid-tier"
    if "gold" in card:
        return "premium-tier"
    if "platinum" in card:
        return "elite-tier"
    if "diamond elite" in card:
        return "invitation-tier"
    return None

def check(status, detail, **extra):
    result = {"status": status, "detail": detail}
    result.update(extra)
    return result

def dispute_count(dispute, today, errors):
    if "disputes_last_12_months" in dispute:
        raw = dispute["disputes_last_12_months"]
        if isinstance(raw, int) and raw >= 0:
            return raw
        errors.append("disputes_last_12_months must be a nonnegative integer")
        return None
    records = dispute.get("dispute_records", MISSING)
    if records is MISSING:
        return None
    if not isinstance(records, list):
        errors.append("dispute_records must be a list")
        return None
    start = today - timedelta(days=365)
    count = 0
    for i, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"dispute_records[{i}] must be an object")
            continue
        d = parse_date(record.get("dispute_date"), f"dispute_records[{i}].dispute_date", errors)
        if d is not None and start <= d <= today:
            count += 1
    return count

def assess_provisional(account, dispute, today, errors):
    tier = normalize_tier(account)
    checks = {}
    opened = parse_date(account.get("date_of_account_open"), "account.date_of_account_open", errors)
    if opened is None or opened > today:
        checks["account_age"] = check("unknown", "A valid account opening date is required")
    else:
        days = (today - opened).days
        checks["account_age"] = check("pass" if days >= 60 else "fail", "Account age evaluated", days=days, minimum_days=60)

    reason = dispute.get("reason")
    if reason not in ALLOWED_REASONS:
        checks["reason"] = check("unknown", "A supported dispute reason is required")
    else:
        supported = reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
        checks["reason"] = check("pass" if supported else "fail", "Reason evaluated", reason=reason)

    amount = money(dispute.get("amount"), "dispute.amount", errors)
    if amount is None or tier not in PROVISIONAL_LIMITS:
        checks["amount"] = check("unknown", "A valid amount and published card tier are required")
    else:
        maximum = PROVISIONAL_LIMITS[tier]
        checks["amount"] = check("pass" if Decimal("25") <= amount <= maximum else "fail", "Amount evaluated", maximum=fmt_money(maximum))

    count = dispute_count(dispute, today, errors)
    if count is None:
        checks["prior_disputes"] = check("unknown", "12-month dispute count is required")
    else:
        checks["prior_disputes"] = check("pass" if count <= 2 else "fail", "Prior disputes evaluated", count=count, maximum=2)

    contacted = dispute.get("contacted_merchant", MISSING)
    if reason == "unauthorized_fraudulent_charge":
        checks["merchant_contact"] = check("pass", "Merchant contact is not required for fraud")
    elif isinstance(contacted, bool):
        checks["merchant_contact"] = check("pass" if contacted else "fail", "Merchant-contact requirement evaluated")
    else:
        checks["merchant_contact"] = check("unknown", "A boolean contacted_merchant answer is required")

    if reason == "goods_services_not_received":
        purchased = parse_date(dispute.get("purchase_date"), "dispute.purchase_date", errors)
        if purchased is None or purchased > today:
            checks["delivery_wait"] = check("unknown", "A nonfuture purchase date is required")
        else:
            age = (today - purchased).days
            checks["delivery_wait"] = check("pass" if age > 30 else "fail", "Purchase age evaluated", days_since_purchase=age, minimum_strictly_greater_than=30)
    else:
        checks["delivery_wait"] = check("pass", "Not applicable to this dispute reason")

    statuses = [v["status"] for v in checks.values()]
    eligibility = "eligible" if all(s == "pass" for s in statuses) else ("ineligible" if "fail" in statuses else "undetermined")
    return {"tier": tier, "eligibility": eligibility, "eligible_for_provisional_credit": eligibility == "eligible", "checks": checks}

def assess_cli(account, cli, today, errors):
    tier = normalize_tier(account)
    checks = {}
    if tier not in CLI_RULES:
        return {"tier": tier, "precheck": "undetermined", "decision": "undetermined", "checks": {}, "message": "Published CLI rules require entry-, mid-, or premium-tier classification."}
    rules = CLI_RULES[tier]
    limit = money(account.get("credit_limit"), "account.credit_limit", errors)
    balance = money(account.get("current_balance"), "account.current_balance", errors)
    past_due = money(account.get("past_due_amount"), "account.past_due_amount", errors)
    requested = money(cli.get("requested_increase_amount"), "cli.requested_increase_amount", errors)
    if limit is None or limit <= 0 or requested is None:
        checks["requested_amount"] = check("unknown", "Positive current limit and requested increase are required")
        precheck = "undetermined"
    else:
        maximum = limit * rules["increase_fraction"]
        passed = requested > 0 and requested <= maximum
        checks["requested_amount"] = check("pass" if passed else "fail", "Tier maximum increase evaluated", requested=fmt_money(requested), maximum=fmt_money(maximum), resulting_limit=fmt_money(limit + requested))
        precheck = "pass" if passed else "fail"

    opened = parse_date(account.get("date_of_account_open"), "account.date_of_account_open", errors)
    if opened is None or opened > today:
        checks["account_age"] = check("unknown", "A nonfuture account opening date is required")
    else:
        days = (today - opened).days
        checks["account_age"] = check("pass" if days >= rules["age"] else "fail", "Account age evaluated", days=days, minimum_days=rules["age"])

    if "last_approved_cli_submission_date" not in cli:
        checks["cooldown"] = check("unknown", "Latest approved CLI submission date, or null for none, is required")
    elif cli["last_approved_cli_submission_date"] is None:
        checks["cooldown"] = check("pass", "No prior approved CLI submission supplied")
    else:
        prior = parse_date(cli["last_approved_cli_submission_date"], "cli.last_approved_cli_submission_date", errors)
        if prior is None or prior > today:
            checks["cooldown"] = check("unknown", "A nonfuture approved submission date is required")
        else:
            elapsed = (today - prior).days
            checks["cooldown"] = check("pass" if elapsed >= rules["cooldown"] else "fail", "Cooldown evaluated", days_elapsed=elapsed, required_days=rules["cooldown"])

    for key, label in (("pending_disputes", "pending disputes"), ("pending_replacement_card", "pending replacement card")):
        value = cli.get(key, MISSING)
        if isinstance(value, bool):
            checks[key] = check("fail" if value else "pass", f"{label.title()} evaluated")
        else:
            checks[key] = check("unknown", f"A boolean {key} result is required")

    if past_due is None:
        checks["good_standing"] = check("unknown", "Past-due amount is required")
    else:
        checks["good_standing"] = check("pass" if past_due <= 0 else "fail", "Past-due amount evaluated", past_due=fmt_money(past_due))

    if balance is None or limit is None or limit <= 0:
        checks["utilization"] = check("unknown", "Balance and positive limit are required")
    else:
        utilization = balance / limit * Decimal("100")
        checks["utilization"] = check("pass" if utilization < rules["utilization"] else "fail", "Strict utilization threshold evaluated", utilization_percent=str(utilization.quantize(Decimal("0.01"))), maximum_strictly_below=str(rules["utilization"]))

    months = cli.get("consecutive_on_time_months", MISSING)
    if isinstance(months, int) and months >= 0:
        checks["payment_history"] = check("pass" if months >= rules["payment_months"] else "fail", "Consecutive on-time payment history evaluated", months=months, required_months=rules["payment_months"])
    else:
        checks["payment_history"] = check("unknown", "A nonnegative consecutive_on_time_months integer is required")

    review_keys = ["account_age", "cooldown", "pending_disputes", "pending_replacement_card", "good_standing", "utilization", "payment_history"]
    failure_map = [("account_age", "insufficient_account_age"), ("cooldown", "cooldown_period_active"), ("pending_disputes", "pending_disputes"), ("pending_replacement_card", "pending_replacement_card"), ("good_standing", "past_due_balance"), ("utilization", "high_utilization"), ("payment_history", "insufficient_payment_history")]
    if precheck != "pass":
        decision, denial_reason = "do_not_submit", "requested_amount_exceeds_limit" if precheck == "fail" else None
    elif any(checks[k]["status"] == "unknown" for k in review_keys):
        decision, denial_reason = "undetermined", None
    else:
        failed = next((reason for key, reason in failure_map if checks[key]["status"] == "fail"), None)
        decision, denial_reason = ("deny", failed) if failed else ("approve", None)
    return {"tier": tier, "precheck": precheck, "decision": decision, "denial_reason": denial_reason, "checks": checks}

def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": [f"Invalid JSON: {exc.msg}"]}))
        return
    errors = []
    if not isinstance(payload, dict):
        print(json.dumps({"valid": False, "errors": ["Top-level input must be an object"]}))
        return
    today = parse_date(payload.get("now"), "now", errors)
    account = payload.get("account")
    if not isinstance(account, dict):
        errors.append("account must be an object")
        account = {}
    output = {"valid": not errors, "errors": errors}
    if today is not None and isinstance(payload.get("dispute"), dict):
        output["provisional_credit"] = assess_provisional(account, payload["dispute"], today, errors)
    if today is not None and isinstance(payload.get("cli"), dict):
        output["cli"] = assess_cli(account, payload["cli"], today, errors)
    if "dispute" not in payload and "cli" not in payload:
        errors.append("Provide a dispute object, a cli object, or both")
    output["valid"] = not errors
    print(json.dumps(output, sort_keys=True))

if __name__ == "__main__":
    main()
