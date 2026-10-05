#!/usr/bin/env python3
"""Read-only calculator and validator for documented credit-card workflows.

Reads one JSON object from stdin and writes one JSON object to stdout. It never calls
banking tools and never causes a customer action.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CLI_RULES = {
    "entry": {"fraction": Decimal("0.25"), "age_days": 120, "cooldown_days": 120, "utilization_below": Decimal("70"), "payment_months": 6},
    "mid": {"fraction": Decimal("0.50"), "age_days": 90, "cooldown_days": 90, "utilization_below": Decimal("80"), "payment_months": 3},
    "premium": {"fraction": Decimal("0.50"), "age_days": 60, "cooldown_days": 60, "utilization_below": Decimal("90"), "payment_months": 3},
}
PROVISIONAL_CAPS = {
    "entry": Decimal("2500"), "mid": Decimal("5000"), "premium": Decimal("10000"),
    "elite": Decimal("15000"), "invitation": Decimal("25000"),
}
REPLACEMENT_LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 4, "invitation": 4}


def classify_tier(value):
    """Classify documented card names and tier labels; Gold is Premium."""
    if not isinstance(value, str):
        return None
    text = value.lower().replace("_", " ").replace("-", " ")
    if "diamond" in text or "invitation" in text:
        return "invitation"
    if "platinum" in text or "elite" in text:
        return "elite"
    if "gold" in text or "premium" in text:
        return "premium"
    if any(word in text for word in ("silver", "green", "mid")):
        return "mid"
    if any(word in text for word in ("bronze", "eco", "crypto", "entry")):
        return "entry"
    return None


def as_money(value):
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, TypeError, ValueError, AttributeError):
        return None


def format_money(value):
    return "${:,.2f}".format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_date(value):
    if not isinstance(value, str):
        return None
    raw = value.strip()
    for candidate, form in ((raw[:10], "%Y-%m-%d"), (raw, "%m/%d/%Y")):
        try:
            return datetime.strptime(candidate, form).date()
        except ValueError:
            pass
    return None


def elapsed_days(start, end):
    first, second = parse_date(start), parse_date(end)
    return (second - first).days if first and second else None


def missing(data, names):
    return [name for name in names if data.get(name) is None or data.get(name) == ""]


def assess_identity(data):
    record = data.get("record") if isinstance(data.get("record"), dict) else {}
    supplied = data.get("supplied") if isinstance(data.get("supplied"), dict) else {}
    fields = ("date_of_birth", "email", "phone", "address")
    compared = [field for field in fields if field in record and field in supplied]
    matched = [field for field in compared if str(record[field]).strip() == str(supplied[field]).strip()]
    verified = len(matched) >= 2
    return {"compared_fields": compared, "matched_fields": matched, "match_count": len(matched),
            "verified": verified,
            "next_action": "log_verification" if verified else "collect_or_correct_identity_fields"}


def assess_cli(data):
    required = ("card_type", "current_credit_limit", "requested_increase_amount")
    absent, errors = missing(data, required), []
    card_tier = classify_tier(data.get("card_type"))
    current = as_money(data.get("current_credit_limit"))
    request = as_money(data.get("requested_increase_amount"))
    if data.get("card_type") is not None and card_tier not in CLI_RULES:
        errors.append("cli_requires_entry_mid_or_premium_tier")
    if data.get("current_credit_limit") is not None and (current is None or current < 0):
        errors.append("invalid_current_credit_limit")
    if data.get("requested_increase_amount") is not None and request is None:
        errors.append("invalid_requested_increase_amount")
    if request is not None and (request <= 0 or request != request.to_integral_value()):
        errors.append("requested_increase_must_be_positive_integer_dollars")

    maximum = None
    if current is not None and card_tier in CLI_RULES:
        maximum = current * CLI_RULES[card_tier]["fraction"]
    within = maximum is not None and request is not None and request <= maximum
    output = {
        "missing": absent, "errors": errors, "tier": card_tier,
        "maximum_increase": format_money(maximum) if maximum is not None else None,
        "requested_within_limit": within,
        "new_credit_limit": format_money(current + request) if current is not None and request is not None else None,
    }
    if absent or errors:
        output["next_action"] = "collect_or_correct_required_cli_data"
    elif not within:
        output["next_action"] = "do_not_submit_or_deny; explain_maximum_and_request_revised_amount"
        output["customer_message"] = (
            "Your requested increase of {} exceeds the maximum increase of {} for your card. "
            "Would you like to adjust your request and proceed with a {} increase instead?"
        ).format(format_money(request), format_money(maximum), format_money(maximum))
    else:
        output["next_action"] = "submit_formal_cli_request_before_post_submission_checks"
    return output


def assess_dispute(data):
    required = (
        "account_open_date", "as_of_date", "purchase_date", "transaction_amount", "card_type",
        "previous_disputes_last_12_months", "dispute_reason", "contacted_merchant",
    )
    absent, errors = missing(data, required), []
    card_tier = classify_tier(data.get("card_type"))
    amount = as_money(data.get("transaction_amount"))
    reason = data.get("dispute_reason")
    valid_reasons = {
        "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
        "goods_services_not_received", "goods_services_not_as_described",
        "canceled_subscription_still_charging", "refund_never_processed",
    }
    if data.get("card_type") is not None and card_tier not in PROVISIONAL_CAPS:
        errors.append("unrecognized_tier")
    if data.get("transaction_amount") is not None and (amount is None or amount < 0):
        errors.append("invalid_transaction_amount")
    if reason is not None and reason not in valid_reasons:
        errors.append("invalid_dispute_reason")

    age = elapsed_days(data.get("account_open_date"), data.get("as_of_date"))
    purchase_age = elapsed_days(data.get("purchase_date"), data.get("as_of_date"))
    conditions = {}
    if not absent and not errors:
        try:
            prior_ok = int(data["previous_disputes_last_12_months"]) <= 2
        except (TypeError, ValueError):
            errors.append("invalid_previous_disputes_last_12_months")
            prior_ok = False
        conditions = {
            "account_open_at_least_60_days": age is not None and age >= 60,
            "reason_eligible": reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"},
            "goods_not_received_purchase_over_30_days": reason != "goods_services_not_received" or (purchase_age is not None and purchase_age > 30),
            "amount_at_least_25": amount >= Decimal("25"),
            "amount_within_tier_cap": amount <= PROVISIONAL_CAPS[card_tier],
            "no_more_than_two_prior_disputes": prior_ok,
            "merchant_contact_satisfied": reason == "unauthorized_fraudulent_charge" or data["contacted_merchant"] is True,
        }
    return {
        "missing": absent, "errors": errors, "tier": card_tier,
        "account_age_days": age, "purchase_age_days": purchase_age,
        "provisional_credit_conditions": conditions,
        "eligible_for_provisional_credit": bool(conditions) and not errors and all(conditions.values()),
    }


def assess_replacement(data):
    required = ("card_type", "reason", "shipping_speed", "pending_order_statuses", "replacement_count_last_60_days")
    absent, errors = missing(data, required), []
    card_tier = classify_tier(data.get("card_type"))
    statuses = data.get("pending_order_statuses")
    if data.get("card_type") is not None and card_tier not in REPLACEMENT_LIMITS:
        errors.append("unrecognized_tier")
    if data.get("reason") not in (None, "fraud_suspected", "lost", "stolen", "damaged", "expired", "other"):
        errors.append("invalid_replacement_reason")
    if data.get("shipping_speed") not in (None, "standard", "expedited"):
        errors.append("invalid_shipping_speed")
    if not isinstance(statuses, list):
        errors.append("pending_order_statuses_must_be_list")
        statuses = []
    try:
        count = int(data.get("replacement_count_last_60_days"))
        if count < 0:
            raise ValueError()
    except (TypeError, ValueError):
        count = None
        errors.append("invalid_replacement_count_last_60_days")
    fee_required = data.get("shipping_speed") == "expedited" and card_tier in ("entry", "mid")
    if fee_required and data.get("expedited_fee_acknowledgement") is not True:
        errors.append("expedited_fee_acknowledgement_required")
    pending = any(str(status).lower() not in ("delivered", "cancelled") for status in statuses)
    eligible = not absent and not errors and not pending and count < REPLACEMENT_LIMITS.get(card_tier, 0)
    return {
        "missing": absent, "errors": errors, "tier": card_tier,
        "has_pending_replacement": pending, "replacement_limit": REPLACEMENT_LIMITS.get(card_tier),
        "replacement_count_last_60_days": count, "eligible_to_submit": eligible,
        "next_action": "order_if_identity_and_address_are_confirmed" if eligible else "do_not_order; obtain_missing_evidence_or_escalate",
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"error": "top_level_object_required"}))
        return
    assessors = {"identity": assess_identity, "cli": assess_cli, "dispute": assess_dispute, "replacement": assess_replacement}
    output = {}
    for name, function in assessors.items():
        if name in payload:
            if not isinstance(payload[name], dict):
                output[name] = {"error": name + "_must_be_object"}
            else:
                try:
                    output[name] = function(payload[name])
                except (KeyError, TypeError, ValueError) as exc:
                    output[name] = {"error": "invalid_" + name + "_data", "detail": str(exc)}
    if not output:
        output = {"error": "provide_at_least_one_of_identity_cli_dispute_replacement"}
    print(json.dumps(output, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
