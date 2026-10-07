#!/usr/bin/env python3
"""Deterministically assess published dispute provisional-credit and CLI rules.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
has no banking side effects; callers must obtain and validate live tool data first.
"""
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

CLI = {
    "entry": (120, 120, Decimal("70"), 6, Decimal("0.25")),
    "mid": (90, 90, Decimal("80"), 3, Decimal("0.50")),
    "premium": (60, 60, Decimal("90"), 3, Decimal("0.50")),
}
PROVISIONAL_MAX = {
    "entry": Decimal("2500"), "mid": Decimal("5000"),
    "premium": Decimal("10000"), "elite": Decimal("15000"),
    "invitation": Decimal("25000"),
}
REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}


def date_value(value, name, errors):
    if not isinstance(value, str):
        errors.append(name + " must be a date string")
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    errors.append(name + " must be YYYY-MM-DD or MM/DD/YYYY")
    return None


def decimal_value(value, name, errors):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise InvalidOperation
        return amount
    except (InvalidOperation, ValueError, TypeError):
        errors.append(name + " must be a finite number")
        return None


def status(passed, detail, **extra):
    result = {"status": "pass" if passed else "fail", "detail": detail}
    result.update(extra)
    return result


def unknown(detail):
    return {"status": "unknown", "detail": detail}


def tier_value(account):
    value = str(account.get("tier", "")).strip().lower().replace("-tier", "")
    aliases = {"entry": "entry", "mid": "mid", "premium": "premium",
               "elite": "elite", "invitation": "invitation"}
    return aliases.get(value)


def format_money(value):
    return format(value.quantize(Decimal("0.01")), ".2f")


def prior_dispute_count(dispute, today, errors):
    if "disputes_last_12_months" in dispute:
        value = dispute["disputes_last_12_months"]
        if isinstance(value, int) and value >= 0:
            return value
        errors.append("disputes_last_12_months must be a nonnegative integer")
        return None
    records = dispute.get("dispute_records")
    if not isinstance(records, list):
        return None
    count = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append("dispute_records[%d] must be an object" % index)
            continue
        filed = date_value(record.get("dispute_date"),
                           "dispute_records[%d].dispute_date" % index, errors)
        if filed and today - timedelta(days=365) <= filed <= today:
            count += 1
    return count


def assess_dispute(account, dispute, today, errors):
    checks = {}
    tier = tier_value(account)
    opened = date_value(account.get("date_of_account_open"),
                        "account.date_of_account_open", errors)
    if opened is None or opened > today:
        checks["account_age"] = unknown("Valid nonfuture opening date required")
    else:
        age = (today - opened).days
        checks["account_age"] = status(age >= 60, "At least 60 days required", days=age)

    reason = dispute.get("reason")
    if reason not in REASONS:
        checks["reason"] = unknown("Supported dispute reason required")
    else:
        checks["reason"] = status(reason in {
            "unauthorized_fraudulent_charge", "duplicate_charge",
            "goods_services_not_received"}, "Eligible reason category evaluated")

    amount = decimal_value(dispute.get("amount"), "dispute.amount", errors)
    if amount is None or tier not in PROVISIONAL_MAX:
        checks["amount"] = unknown("Amount and recognized card tier required")
    else:
        maximum = PROVISIONAL_MAX[tier]
        checks["amount"] = status(Decimal("25") <= amount <= maximum,
                                   "Tier amount range evaluated",
                                   maximum=format_money(maximum))

    count = prior_dispute_count(dispute, today, errors)
    checks["prior_disputes"] = (unknown("12-month dispute count required") if count is None
                                 else status(count <= 2, "Prior disputes evaluated", count=count))

    contacted = dispute.get("contacted_merchant")
    if reason == "unauthorized_fraudulent_charge":
        checks["merchant_contact"] = status(True, "Not required for fraud")
    elif isinstance(contacted, bool):
        checks["merchant_contact"] = status(contacted, "Merchant contact evaluated")
    else:
        checks["merchant_contact"] = unknown("Boolean contacted_merchant required")

    if reason == "goods_services_not_received":
        purchased = date_value(dispute.get("purchase_date"), "dispute.purchase_date", errors)
        if purchased is None or purchased > today:
            checks["delivery_wait"] = unknown("Valid nonfuture purchase date required")
        else:
            days = (today - purchased).days
            checks["delivery_wait"] = status(days > 30, "Purchase must be over 30 days ago", days=days)
    else:
        checks["delivery_wait"] = status(True, "Not applicable")

    values = [item["status"] for item in checks.values()]
    eligibility = "eligible" if all(x == "pass" for x in values) else (
        "ineligible" if "fail" in values else "undetermined")
    return {"tier": tier, "eligibility": eligibility,
            "eligible_for_provisional_credit": eligibility == "eligible", "checks": checks}


def assess_cli(account, cli, today, errors):
    tier = tier_value(account)
    if tier not in CLI:
        return {"tier": tier, "precheck": "undetermined", "decision": "undetermined",
                "checks": {}, "message": "Published CLI rules cover entry, mid, and premium tiers."}
    min_age, cooldown, utilization_max, payment_months, fraction = CLI[tier]
    checks = {}
    limit = decimal_value(account.get("credit_limit"), "account.credit_limit", errors)
    balance = decimal_value(account.get("current_balance"), "account.current_balance", errors)
    past_due = decimal_value(account.get("past_due_amount"), "account.past_due_amount", errors)
    requested = decimal_value(cli.get("requested_increase_amount"),
                              "cli.requested_increase_amount", errors)
    if limit is None or limit <= 0 or requested is None:
        checks["requested_amount"] = unknown("Positive limit and requested increase required")
        precheck = "undetermined"
    else:
        maximum = limit * fraction
        checks["requested_amount"] = status(requested > 0 and requested <= maximum,
                                              "Maximum increase evaluated",
                                              maximum=format_money(maximum),
                                              resulting_limit=format_money(limit + requested))
        precheck = checks["requested_amount"]["status"]

    opened = date_value(account.get("date_of_account_open"), "account.date_of_account_open", errors)
    if opened is None or opened > today:
        checks["account_age"] = unknown("Valid nonfuture opening date required")
    else:
        days = (today - opened).days
        checks["account_age"] = status(days >= min_age, "Account age evaluated", days=days)

    prior_value = cli.get("last_approved_cli_submission_date", "missing")
    if prior_value == "missing":
        checks["cooldown"] = unknown("Latest approved submission date or null required")
    elif prior_value is None:
        checks["cooldown"] = status(True, "No prior approved request supplied")
    else:
        prior = date_value(prior_value, "cli.last_approved_cli_submission_date", errors)
        if prior is None or prior > today:
            checks["cooldown"] = unknown("Valid nonfuture approved submission date required")
        else:
            elapsed = (today - prior).days
            checks["cooldown"] = status(elapsed >= cooldown, "Cooldown evaluated", days_elapsed=elapsed)

    for field in ("pending_disputes", "pending_replacement_card"):
        value = cli.get(field)
        checks[field] = (status(not value, field + " evaluated") if isinstance(value, bool)
                         else unknown("Boolean " + field + " required"))
    checks["good_standing"] = (unknown("Past-due amount required") if past_due is None
                                else status(past_due <= 0, "Past-due amount evaluated"))
    if balance is None or limit is None or limit <= 0:
        checks["utilization"] = unknown("Balance and positive limit required")
    else:
        actual = balance / limit * Decimal("100")
        checks["utilization"] = status(actual < utilization_max, "Strict utilization evaluated",
                                        utilization_percent=str(actual))
    months = cli.get("consecutive_on_time_months")
    checks["payment_history"] = (status(months >= payment_months, "Payment history evaluated", months=months)
                                  if isinstance(months, int) and months >= 0 else
                                  unknown("Nonnegative consecutive_on_time_months required"))

    order = [("account_age", "insufficient_account_age"), ("cooldown", "cooldown_period_active"),
             ("pending_disputes", "pending_disputes"), ("pending_replacement_card", "pending_replacement_card"),
             ("good_standing", "past_due_balance"), ("utilization", "high_utilization"),
             ("payment_history", "insufficient_payment_history")]
    review = [key for key, _ in order]
    if precheck != "pass":
        decision = "do_not_submit" if precheck == "fail" else "undetermined"
        denial = "requested_amount_exceeds_limit" if precheck == "fail" else None
    elif any(checks[key]["status"] == "unknown" for key in review):
        decision, denial = "undetermined", None
    else:
        denial = next((reason for key, reason in order if checks[key]["status"] == "fail"), None)
        decision = "deny" if denial else "approve"
    return {"tier": tier, "precheck": precheck, "decision": decision,
            "denial_reason": denial, "checks": checks}


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
    today = date_value(payload.get("now"), "now", errors)
    account = payload.get("account")
    if not isinstance(account, dict):
        errors.append("account must be an object")
        account = {}
    output = {"valid": False, "errors": errors}
    if today and isinstance(payload.get("dispute"), dict):
        output["provisional_credit"] = assess_dispute(account, payload["dispute"], today, errors)
    if today and isinstance(payload.get("cli"), dict):
        output["cli"] = assess_cli(account, payload["cli"], today, errors)
    if not isinstance(payload.get("dispute"), dict) and not isinstance(payload.get("cli"), dict):
        errors.append("Provide a dispute object, a cli object, or both")
    output["valid"] = not errors
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
