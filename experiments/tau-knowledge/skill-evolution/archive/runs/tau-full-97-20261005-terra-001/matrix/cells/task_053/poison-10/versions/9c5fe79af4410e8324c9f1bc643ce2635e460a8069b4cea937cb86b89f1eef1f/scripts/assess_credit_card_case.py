#!/usr/bin/env python3
"""Assess published dispute and CLI rules without banking side effects.

Reads one JSON object from stdin and writes one JSON object to stdout. The
script never submits, approves, denies, or files a banking request.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

CARD_TIERS = {
    "bronze rewards card": "entry", "ecocard": "entry",
    "business bronze rewards card": "entry", "crypto-cash back card": "entry",
    "silver rewards card": "mid", "business silver rewards card": "mid",
    "green rewards card": "mid", "silver zoom card": "mid",
    "gold rewards card": "premium", "business gold rewards card": "premium",
}
CLI_RULES = {
    "entry": (120, 120, Decimal("70"), 6, Decimal("0.25")),
    "mid": (90, 90, Decimal("80"), 3, Decimal("0.50")),
    "premium": (60, 60, Decimal("90"), 3, Decimal("0.50")),
}
PROVISIONAL_MAX = {
    "entry": Decimal("2500"), "mid": Decimal("5000"),
    "premium": Decimal("10000"), "elite": Decimal("15000"),
    "invitation": Decimal("25000"),
}
ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received",
}
ALL_REASONS = ELIGIBLE_REASONS | {
    "incorrect_amount", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(label + " must be a date string")
        return None
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    errors.append(label + " must use YYYY-MM-DD or MM/DD/YYYY")
    return None


def number(value, label, errors):
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite():
            raise InvalidOperation
        return parsed
    except (InvalidOperation, TypeError, ValueError):
        errors.append(label + " must be a finite number")
        return None


def card_tier(account):
    direct = account.get("tier")
    if isinstance(direct, str):
        normalized = direct.strip().lower().replace("-tier", "")
        if normalized in PROVISIONAL_MAX:
            return normalized
    product = account.get("card_type")
    return CARD_TIERS.get(product.strip().lower()) if isinstance(product, str) else None


def check(status, detail, **extra):
    result = {"status": status, "detail": detail}
    result.update(extra)
    return result


def money(value):
    return format(value.quantize(Decimal("0.01")), ".2f")


def payment_check(cli, required_months, today, errors):
    records = cli.get("payment_records")
    if records is None:
        months = cli.get("consecutive_on_time_months")
        if isinstance(months, int) and months >= 0:
            return check(
                "pass" if months >= required_months else "fail",
                "Caller-supplied eligible consecutive-month count evaluated",
                eligible_on_time_months=months,
            )
        return check("unknown", "Provide payment_records or a nonnegative consecutive_on_time_months count")
    if not isinstance(records, list):
        return check("unknown", "payment_records must be a list")

    usable = []
    future_records = 0
    invalid_records = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            invalid_records += 1
            continue
        payment_date = parse_date(record.get("payment_date"), "cli.payment_records[%d].payment_date" % index, errors)
        status = record.get("status")
        if payment_date is None or not isinstance(status, str):
            invalid_records += 1
            continue
        if payment_date > today:
            future_records += 1
            continue
        if status.strip().upper() == "ON_TIME":
            usable.append(payment_date)

    if invalid_records:
        return check("unknown", "Payment records contain invalid date or status data", invalid_records=invalid_records)
    # The returned records are expected to be the requested consecutive monthly history.
    # Future-dated records are deliberately excluded before evaluating eligibility.
    usable.sort(reverse=True)
    enough = len(usable) >= required_months
    return check(
        "pass" if enough else "fail",
        "Only on-time payments dated on or before the business date count",
        eligible_on_time_months=len(usable),
        future_dated_records_excluded=future_records,
    )


def assess_cli(account, cli, today, errors):
    tier = card_tier(account)
    if tier not in CLI_RULES:
        return {"tier": tier, "precheck": "undetermined", "decision": "undetermined", "checks": {}}
    age_min, cooldown_days, utilization_max, required_months, maximum_fraction = CLI_RULES[tier]
    checks = {}
    limit = number(account.get("credit_limit"), "account.credit_limit", errors)
    balance = number(account.get("current_balance"), "account.current_balance", errors)
    past_due = number(account.get("past_due_amount"), "account.past_due_amount", errors)
    requested = number(cli.get("requested_increase_amount"), "cli.requested_increase_amount", errors)

    if limit is None or limit <= 0 or requested is None:
        checks["requested_amount"] = check("unknown", "Positive limit and requested increase required")
    else:
        maximum = limit * maximum_fraction
        checks["requested_amount"] = check(
            "pass" if Decimal("0") < requested <= maximum else "fail",
            "Maximum increase evaluated", maximum_increase=money(maximum),
            resulting_limit=money(limit + requested),
        )

    opened = parse_date(account.get("date_of_account_open"), "account.date_of_account_open", errors)
    if opened is None or opened > today:
        checks["account_age"] = check("unknown", "Valid nonfuture opening date required")
    else:
        age = (today - opened).days
        checks["account_age"] = check("pass" if age >= age_min else "fail", "Account age evaluated", days=age)

    prior = cli.get("last_approved_cli_submission_date", "missing")
    if prior == "missing":
        checks["cooldown"] = check("unknown", "Approved submission date or null required")
    elif prior is None:
        checks["cooldown"] = check("pass", "No prior approved request supplied")
    else:
        prior_date = parse_date(prior, "cli.last_approved_cli_submission_date", errors)
        if prior_date is None or prior_date > today:
            checks["cooldown"] = check("unknown", "Valid nonfuture approved date required")
        else:
            elapsed = (today - prior_date).days
            checks["cooldown"] = check("pass" if elapsed >= cooldown_days else "fail", "Cooldown evaluated", days_elapsed=elapsed)

    for field in ("pending_disputes", "pending_replacement_card"):
        value = cli.get(field)
        checks[field] = check("pass" if not value else "fail", field + " evaluated") if isinstance(value, bool) else check("unknown", "Boolean " + field + " required")
    checks["good_standing"] = check("unknown", "Past-due amount required") if past_due is None else check("pass" if past_due <= 0 else "fail", "Past-due balance evaluated")
    if limit is None or limit <= 0 or balance is None:
        checks["utilization"] = check("unknown", "Positive limit and balance required")
    else:
        utilization = balance / limit * Decimal("100")
        checks["utilization"] = check("pass" if utilization < utilization_max else "fail", "Strict utilization evaluated", utilization_percent=str(utilization))
    checks["payment_history"] = payment_check(cli, required_months, today, errors)

    order = [
        ("account_age", "insufficient_account_age"),
        ("cooldown", "cooldown_period_active"),
        ("pending_disputes", "pending_disputes"),
        ("pending_replacement_card", "pending_replacement_card"),
        ("good_standing", "past_due_balance"),
        ("utilization", "high_utilization"),
        ("payment_history", "insufficient_payment_history"),
    ]
    precheck = checks["requested_amount"]["status"]
    if precheck == "fail":
        decision, denial = "do_not_submit", "requested_amount_exceeds_limit"
    elif precheck == "unknown" or any(checks[name]["status"] == "unknown" for name, _ in order):
        decision, denial = "undetermined", None
    else:
        denial = next((reason for name, reason in order if checks[name]["status"] == "fail"), None)
        decision = "deny" if denial else "approve"
    return {"tier": tier, "precheck": precheck, "decision": decision, "denial_reason": denial, "checks": checks}


def assess_dispute(account, dispute, today, errors):
    checks = {}
    opened = parse_date(account.get("date_of_account_open"), "account.date_of_account_open", errors)
    checks["account_age"] = check("unknown", "Valid nonfuture opening date required") if opened is None or opened > today else check("pass" if (today - opened).days >= 60 else "fail", "Account age evaluated")
    reason = dispute.get("reason")
    checks["reason"] = check("pass" if reason in ELIGIBLE_REASONS else "fail", "Reason evaluated") if reason in ALL_REASONS else check("unknown", "Supported dispute reason required")
    amount = number(dispute.get("amount"), "dispute.amount", errors)
    maximum = PROVISIONAL_MAX.get(card_tier(account))
    checks["amount"] = check("unknown", "Amount and recognized tier required") if amount is None or maximum is None else check("pass" if Decimal("25") <= amount <= maximum else "fail", "Amount evaluated", maximum=money(maximum))
    count = dispute.get("disputes_last_12_months")
    checks["prior_disputes"] = check("pass" if count <= 2 else "fail", "Dispute count evaluated", count=count) if isinstance(count, int) and count >= 0 else check("unknown", "Nonnegative 12-month dispute count required")
    contacted = dispute.get("contacted_merchant")
    checks["merchant_contact"] = check("pass", "Not required for fraud") if reason == "unauthorized_fraudulent_charge" else (check("pass" if contacted else "fail", "Merchant contact evaluated") if isinstance(contacted, bool) else check("unknown", "Boolean contacted_merchant required"))
    if reason == "goods_services_not_received":
        purchased = parse_date(dispute.get("purchase_date"), "dispute.purchase_date", errors)
        checks["delivery_wait"] = check("unknown", "Valid nonfuture purchase date required") if purchased is None or purchased > today else check("pass" if (today - purchased).days > 30 else "fail", "Delivery wait evaluated")
    else:
        checks["delivery_wait"] = check("pass", "Not applicable")
    statuses = [item["status"] for item in checks.values()]
    eligibility = "eligible" if all(status == "pass" for status in statuses) else ("ineligible" if "fail" in statuses else "undetermined")
    return {"tier": card_tier(account), "eligibility": eligibility, "eligible_for_provisional_credit": eligibility == "eligible", "checks": checks}


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": ["Invalid JSON: " + exc.msg]}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"valid": False, "errors": ["Top-level input must be an object"]}))
        return
    errors = []
    today = parse_date(payload.get("now"), "now", errors)
    account = payload.get("account")
    if not isinstance(account, dict):
        errors.append("account must be an object")
        account = {}
    output = {"valid": False, "errors": errors}
    if today and isinstance(payload.get("cli"), dict):
        output["cli"] = assess_cli(account, payload["cli"], today, errors)
    if today and isinstance(payload.get("dispute"), dict):
        output["provisional_credit"] = assess_dispute(account, payload["dispute"], today, errors)
    if not isinstance(payload.get("cli"), dict) and not isinstance(payload.get("dispute"), dict):
        errors.append("Provide a cli object, a dispute object, or both")
    output["valid"] = not errors
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
