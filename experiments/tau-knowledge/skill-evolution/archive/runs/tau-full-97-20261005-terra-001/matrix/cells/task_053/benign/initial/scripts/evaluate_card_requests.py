#!/usr/bin/env python3
"""Deterministic assessment helper for normalized credit-card case data.

Reads one JSON object from stdin and writes one JSON object to stdout. It does
not access banking systems or perform any customer action.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CLI_RULES = {
    "entry": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "payments": 6, "max_fraction": Decimal("0.25")},
    "mid": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "payments": 3, "max_fraction": Decimal("0.50")},
    "premium": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "payments": 3, "max_fraction": Decimal("0.50")},
}
PROVISIONAL_CAPS = {
    "entry": Decimal("2500"), "mid": Decimal("5000"), "premium": Decimal("10000"),
    "elite": Decimal("15000"), "invitation": Decimal("25000"),
}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}
ALLOWED_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def money(value):
    try:
        if isinstance(value, bool) or value is None:
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def bool_is(value):
    return value if isinstance(value, bool) else None


def as_int(value):
    if isinstance(value, bool):
        return None
    try:
        integer = int(value)
        return integer if str(integer) == str(value) or isinstance(value, int) else integer
    except (TypeError, ValueError):
        return None


def add_years_safely(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # February 29
        return d.replace(month=2, day=28, year=d.year + years)


def decimal_out(value):
    return float(value) if isinstance(value, Decimal) else value


def cli_assessment(now, card, cli):
    result = {"requested_amount_valid": False, "submission_action": "do_not_submit", "unknown_checks": [], "failures": []}
    tier = cli.get("tier")
    rule = CLI_RULES.get(tier)
    limit = money(card.get("current_credit_limit"))
    if rule is None:
        result["pre_submission_error"] = "unsupported_or_missing_cli_tier"
        return result
    if limit is None or limit <= 0:
        result["pre_submission_error"] = "missing_or_invalid_current_credit_limit"
        return result

    increase = money(cli.get("requested_increase_amount")) if "requested_increase_amount" in cli else None
    new_limit = money(cli.get("requested_new_limit")) if "requested_new_limit" in cli else None
    if increase is None and new_limit is None:
        result["pre_submission_error"] = "missing_requested_increase_or_new_limit"
        return result
    if new_limit is not None:
        derived = new_limit - limit
        if increase is not None and increase != derived:
            result["pre_submission_error"] = "requested_increase_and_new_limit_do_not_agree"
            return result
        increase = derived
    if increase is None or increase <= 0:
        result["pre_submission_error"] = "requested_increase_must_be_positive"
        return result
    if increase != increase.to_integral_value():
        result["pre_submission_error"] = "requested_increase_must_be_whole_dollars"
        return result

    maximum = limit * rule["max_fraction"]
    result.update({
        "requested_increase_amount": decimal_out(increase),
        "maximum_increase_amount": decimal_out(maximum),
        "proposed_new_credit_limit": decimal_out(limit + increase),
    })
    if increase > maximum:
        result["pre_submission_error"] = "requested_amount_exceeds_limit"
        return result

    result["requested_amount_valid"] = True
    result["submission_action"] = "submit_then_complete_all_checks"

    opened = parse_date(card.get("account_open_date"))
    if now is None or opened is None:
        result["unknown_checks"].append("account_age")
    elif (now - opened).days < rule["age"]:
        result["failures"].append("insufficient_account_age")

    if bool_is(cli.get("history_checked")) is not True:
        result["unknown_checks"].append("cooldown_period")
    else:
        approved = cli.get("last_approved_submission_date")
        if approved is not None:
            approved_date = parse_date(approved)
            if now is None or approved_date is None:
                result["unknown_checks"].append("cooldown_period")
            elif (now - approved_date).days < rule["cooldown"]:
                result["failures"].append("cooldown_period_active")
                result["next_eligible_date"] = (approved_date.fromordinal(approved_date.toordinal() + rule["cooldown"])).isoformat()

    if bool_is(cli.get("active_disputes_checked")) is not True:
        result["unknown_checks"].append("active_disputes")
    else:
        count = as_int(cli.get("active_dispute_count"))
        if count is None or count < 0:
            result["unknown_checks"].append("active_disputes")
        elif count > 0:
            result["failures"].append("pending_disputes")

    if bool_is(cli.get("replacement_checked")) is not True:
        result["unknown_checks"].append("pending_replacement_cards")
    else:
        orders = cli.get("replacement_orders")
        if not isinstance(orders, list):
            result["unknown_checks"].append("pending_replacement_cards")
        elif any(not isinstance(x, dict) or str(x.get("status", "")).lower() not in FINAL_REPLACEMENT_STATUSES for x in orders):
            result["failures"].append("pending_replacement_card")

    past_due = money(card.get("past_due_amount"))
    if past_due is None:
        result["unknown_checks"].append("good_standing")
    elif past_due > 0:
        result["failures"].append("past_due_balance")

    balance = money(card.get("current_balance"))
    if balance is None:
        result["unknown_checks"].append("credit_utilization")
    else:
        utilization = balance / limit * Decimal("100")
        result["utilization_percent"] = decimal_out(utilization)
        if utilization >= rule["utilization"]:
            result["failures"].append("high_utilization")

    if bool_is(cli.get("payment_history_checked")) is not True:
        result["unknown_checks"].append("payment_history")
    else:
        months = as_int(cli.get("consecutive_on_time_months"))
        if months is None or months < 0:
            result["unknown_checks"].append("payment_history")
        elif months < rule["payments"]:
            result["failures"].append("insufficient_payment_history")

    if result["unknown_checks"]:
        result["decision"] = "needs_completed_checks"
        result["decision_action"] = "do_not_approve_or_deny_yet"
    elif result["failures"]:
        result["decision"] = "deny"
        result["denial_reason"] = result["failures"][0]
        result["decision_action"] = "call_deny_credit_limit_increase"
    else:
        result["decision"] = "approve"
        result["decision_action"] = "call_approve_credit_limit_increase"
    return result


def provisional_assessment(now, card, dispute):
    result = {"eligible": None, "unknown_checks": [], "failures": []}
    tier = dispute.get("card_tier")
    cap = PROVISIONAL_CAPS.get(tier)
    if cap is None:
        result["unknown_checks"].append("provisional_card_tier")

    opened = parse_date(card.get("account_open_date"))
    if now is None or opened is None:
        result["unknown_checks"].append("account_age")
    elif (now - opened).days < 60:
        result["failures"].append("account_under_60_days")

    reason = dispute.get("reason")
    if reason not in ALLOWED_REASONS:
        result["unknown_checks"].append("dispute_reason")
    elif reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        result["failures"].append("reason_not_provisionally_eligible")
    elif reason == "goods_services_not_received":
        purchase = parse_date(dispute.get("purchase_date"))
        if now is None or purchase is None:
            result["unknown_checks"].append("purchase_age")
        elif (now - purchase).days <= 30:
            result["failures"].append("goods_not_received_purchase_not_over_30_days")

    amount = money(dispute.get("transaction_amount"))
    if amount is None:
        result["unknown_checks"].append("transaction_amount")
    else:
        if amount < Decimal("25"):
            result["failures"].append("transaction_amount_below_25")
        if cap is not None and amount > cap:
            result["failures"].append("transaction_amount_exceeds_tier_cap")

    if bool_is(dispute.get("history_checked")) is not True:
        result["unknown_checks"].append("prior_dispute_history")
    else:
        dates = dispute.get("prior_dispute_dates")
        if not isinstance(dates, list) or now is None:
            result["unknown_checks"].append("prior_dispute_history")
        else:
            parsed = [parse_date(x) for x in dates]
            if any(x is None for x in parsed):
                result["unknown_checks"].append("prior_dispute_history")
            else:
                cutoff = add_years_safely(now, -1)
                count = sum(1 for x in parsed if cutoff <= x <= now)
                result["prior_disputes_past_12_months"] = count
                if count > 2:
                    result["failures"].append("more_than_two_prior_disputes")

    if reason and reason != "unauthorized_fraudulent_charge":
        contacted = bool_is(dispute.get("contacted_merchant"))
        if contacted is None:
            result["unknown_checks"].append("merchant_contact")
        elif not contacted:
            result["failures"].append("merchant_not_contacted")

    if result["unknown_checks"]:
        result["eligible"] = None
    else:
        result["eligible"] = not bool(result["failures"])
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        now = parse_date(payload.get("now"))
        card = payload.get("card") if isinstance(payload.get("card"), dict) else {}
        cli = payload.get("cli") if isinstance(payload.get("cli"), dict) else {}
        dispute = payload.get("dispute") if isinstance(payload.get("dispute"), dict) else {}
        output = {
            "now_parsed": now.isoformat() if now else None,
            "cli": cli_assessment(now, card, cli) if cli else {"not_requested": True},
            "provisional_credit": provisional_assessment(now, card, dispute) if dispute else {"not_requested": True},
        }
        print(json.dumps(output, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
