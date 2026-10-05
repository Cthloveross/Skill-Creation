#!/usr/bin/env python3
"""Assess published dispute provisional-credit and CLI rules without side effects.

Reads one JSON object from stdin and writes one JSON object to stdout.
This script never calls banking tools and cannot approve, deny, submit, or file a case.
"""
import json
import sys
from datetime import datetime, timedelta
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
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, TypeError, ValueError):
        errors.append(label + " must be a finite number")
        return None


def tier(account):
    direct = account.get("tier")
    if isinstance(direct, str):
        value = direct.strip().lower().replace("-tier", "")
        if value in PROVISIONAL_MAX:
            return value
    card_type = account.get("card_type")
    return CARD_TIERS.get(card_type.strip().lower()) if isinstance(card_type, str) else None


def result(status, detail, **fields):
    output = {"status": status, "detail": detail}
    output.update(fields)
    return output


def money(value):
    return format(value.quantize(Decimal("0.01")), ".2f")


def assess_cli(account, cli, today, errors):
    account_tier = tier(account)
    if account_tier not in CLI_RULES:
        return {"tier": account_tier, "precheck": "undetermined", "decision": "undetermined",
                "checks": {}, "message": "No published CLI rule for this card tier."}
    age_min, cooldown_days, util_max, payment_months, maximum_fraction = CLI_RULES[account_tier]
    checks = {}
    limit = number(account.get("credit_limit"), "account.credit_limit", errors)
    balance = number(account.get("current_balance"), "account.current_balance", errors)
    past_due = number(account.get("past_due_amount"), "account.past_due_amount", errors)
    requested = number(cli.get("requested_increase_amount"), "cli.requested_increase_amount", errors)
    if limit is None or limit <= 0 or requested is None:
        checks["requested_amount"] = result("unknown", "Positive limit and requested increase required")
    else:
        maximum = limit * maximum_fraction
        ok = requested > 0 and requested <= maximum
        checks["requested_amount"] = result(
            "pass" if ok else "fail", "Maximum increase evaluated",
            maximum_increase=money(maximum), resulting_limit=money(limit + requested))

    opened = parse_date(account.get("date_of_account_open"), "account.date_of_account_open", errors)
    if opened is None or opened > today:
        checks["account_age"] = result("unknown", "Valid nonfuture opening date required")
    else:
        days = (today - opened).days
        checks["account_age"] = result("pass" if days >= age_min else "fail", "Account age evaluated", days=days)

    prior = cli.get("last_approved_cli_submission_date", "missing")
    if prior == "missing":
        checks["cooldown"] = result("unknown", "Approved submission date or null required")
    elif prior is None:
        checks["cooldown"] = result("pass", "No prior approved request supplied")
    else:
        prior_date = parse_date(prior, "cli.last_approved_cli_submission_date", errors)
        if prior_date is None or prior_date > today:
            checks["cooldown"] = result("unknown", "Valid nonfuture approved date required")
        else:
            elapsed = (today - prior_date).days
            checks["cooldown"] = result("pass" if elapsed >= cooldown_days else "fail",
                                        "Cooldown evaluated", days_elapsed=elapsed)

    for key in ("pending_disputes", "pending_replacement_card"):
        value = cli.get(key)
        checks[key] = (result("pass" if not value else "fail", key + " evaluated")
                       if isinstance(value, bool) else result("unknown", "Boolean " + key + " required"))
    checks["good_standing"] = (result("unknown", "Past-due amount required") if past_due is None
                                else result("pass" if past_due <= 0 else "fail", "Past-due balance evaluated"))
    if limit is None or limit <= 0 or balance is None:
        checks["utilization"] = result("unknown", "Positive limit and balance required")
    else:
        utilization = balance / limit * Decimal("100")
        checks["utilization"] = result("pass" if utilization < util_max else "fail",
                                       "Strict utilization evaluated", utilization_percent=str(utilization))
    on_time = cli.get("consecutive_on_time_months")
    checks["payment_history"] = (
        result("pass" if on_time >= payment_months else "fail", "Payment history evaluated", months=on_time)
        if isinstance(on_time, int) and on_time >= 0 else
        result("unknown", "Nonnegative consecutive_on_time_months required"))

    review_order = [
        ("account_age", "insufficient_account_age"), ("cooldown", "cooldown_period_active"),
        ("pending_disputes", "pending_disputes"), ("pending_replacement_card", "pending_replacement_card"),
        ("good_standing", "past_due_balance"), ("utilization", "high_utilization"),
        ("payment_history", "insufficient_payment_history"),
    ]
    precheck = checks["requested_amount"]["status"]
    if precheck == "fail":
        decision, denial = "do_not_submit", "requested_amount_exceeds_limit"
    elif precheck == "unknown" or any(checks[key]["status"] == "unknown" for key, _ in review_order):
        decision, denial = "undetermined", None
    else:
        denial = next((reason for key, reason in review_order if checks[key]["status"] == "fail"), None)
        decision = "deny" if denial else "approve"
    return {"tier": account_tier, "precheck": precheck, "decision": decision,
            "denial_reason": denial, "checks": checks}


def assess_dispute(account, dispute, today, errors):
    checks = {}
    opened = parse_date(account.get("date_of_account_open"), "account.date_of_account_open", errors)
    if opened is None or opened > today:
        checks["account_age"] = result("unknown", "Valid nonfuture opening date required")
    else:
        checks["account_age"] = result("pass" if (today - opened).days >= 60 else "fail", "Account age evaluated")
    reason = dispute.get("reason")
    checks["reason"] = (result("pass" if reason in ELIGIBLE_REASONS else "fail", "Reason evaluated")
                        if reason in ALL_REASONS else result("unknown", "Supported dispute reason required"))
    amount = number(dispute.get("amount"), "dispute.amount", errors)
    maximum = PROVISIONAL_MAX.get(tier(account))
    checks["amount"] = (result("unknown", "Amount and recognized tier required") if amount is None or maximum is None else
                        result("pass" if Decimal("25") <= amount <= maximum else "fail", "Amount evaluated", maximum=money(maximum)))
    count = dispute.get("disputes_last_12_months")
    checks["prior_disputes"] = (result("pass" if count <= 2 else "fail", "Dispute count evaluated", count=count)
                                if isinstance(count, int) and count >= 0 else result("unknown", "Nonnegative 12-month dispute count required"))
    contacted = dispute.get("contacted_merchant")
    if reason == "unauthorized_fraudulent_charge":
        checks["merchant_contact"] = result("pass", "Not required for fraud")
    else:
        checks["merchant_contact"] = (result("pass" if contacted else "fail", "Merchant contact evaluated")
                                      if isinstance(contacted, bool) else result("unknown", "Boolean contacted_merchant required"))
    if reason == "goods_services_not_received":
        purchased = parse_date(dispute.get("purchase_date"), "dispute.purchase_date", errors)
        checks["delivery_wait"] = (result("unknown", "Valid nonfuture purchase date required") if purchased is None or purchased > today else
                                   result("pass" if (today - purchased).days > 30 else "fail", "Delivery wait evaluated"))
    else:
        checks["delivery_wait"] = result("pass", "Not applicable")
    statuses = [check["status"] for check in checks.values()]
    eligibility = "eligible" if all(value == "pass" for value in statuses) else ("ineligible" if "fail" in statuses else "undetermined")
    return {"tier": tier(account), "eligibility": eligibility,
            "eligible_for_provisional_credit": eligibility == "eligible", "checks": checks}


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
