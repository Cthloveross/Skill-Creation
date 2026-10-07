#!/usr/bin/env python3
"""Validate deterministic facts for dispute, replacement, and CLI workflows.

Input: a JSON object with optional identity, dispute, replacement, and cli objects.
Output: a JSON object with one assessment per supplied object. This program is
read-only: it does not call tools or write account records.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CLI_RULES = {
    "entry": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "payment_months": 6, "max_fraction": Decimal("0.25")},
    "mid": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "payment_months": 3, "max_fraction": Decimal("0.50")},
    "premium": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "payment_months": 3, "max_fraction": Decimal("0.50")},
}
PROVISIONAL_LIMITS = {
    "entry": Decimal("2500"), "mid": Decimal("5000"), "premium": Decimal("10000"),
    "elite": Decimal("15000"), "invitation": Decimal("25000"),
}
REPLACEMENT_LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 4, "invitation": 4}


def canon_tier(value):
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("_", " ").replace("-", " ")
    if "invitation" in text or "diamond" in text:
        return "invitation"
    if "elite" in text or "platinum" in text:
        return "elite"
    if "premium" in text or "gold" in text:
        return "premium"
    if "mid" in text or "silver" in text or "green" in text:
        return "mid"
    if "entry" in text or "bronze" in text or "eco" in text or "crypto" in text:
        return "entry"
    return None


def as_decimal(value):
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    return None


def days_between(older, newer):
    left, right = as_date(older), as_date(newer)
    if not left or not right:
        return None
    return (right - left).days


def require(data, fields):
    return [field for field in fields if data.get(field) is None or data.get(field) == ""]


def assess_identity(data):
    fields = ("date_of_birth", "email", "phone", "address")
    record = data.get("record") if isinstance(data.get("record"), dict) else {}
    supplied = data.get("supplied") if isinstance(data.get("supplied"), dict) else {}
    available = [field for field in fields if field in supplied and field in record]
    matches = [field for field in available if str(supplied[field]).strip() == str(record[field]).strip()]
    return {
        "available_comparisons": available,
        "matched_fields": matches,
        "match_count": len(matches),
        "verified": len(matches) >= 2,
        "next_action": "log_verification" if len(matches) >= 2 else "collect_or_correct_identity_fields",
    }


def assess_dispute(data):
    required = [
        "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id", "phone", "email", "address",
        "contacted_merchant", "purchase_date", "issue_noticed_date", "dispute_reason", "resolution_requested",
        "account_open_date", "as_of_date", "transaction_amount", "tier", "previous_disputes_last_12_months",
    ]
    missing = require(data, required)
    errors = []
    reason = data.get("dispute_reason")
    allowed_reasons = {
        "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount", "goods_services_not_received",
        "goods_services_not_as_described", "canceled_subscription_still_charging", "refund_never_processed",
    }
    allowed_actions = {"keep_active", "cancel_and_reissue"}
    allowed_resolutions = {"full_refund", "partial_refund", "reversal_of_charge"}
    if reason is not None and reason not in allowed_reasons:
        errors.append("invalid_dispute_reason")
    if data.get("card_action") is not None and data.get("card_action") not in allowed_actions:
        errors.append("invalid_card_action")
    resolution = data.get("resolution_requested")
    if resolution is not None and resolution not in allowed_resolutions:
        errors.append("invalid_resolution_requested")
    if resolution == "partial_refund" and as_decimal(data.get("partial_refund_amount")) is None:
        errors.append("partial_refund_amount_required")
    if resolution != "partial_refund" and data.get("partial_refund_amount") not in (None, ""):
        errors.append("partial_refund_amount_not_applicable")
    for field in ("purchase_date", "issue_noticed_date"):
        if data.get(field) is not None:
            try:
                datetime.strptime(str(data[field]), "%m/%d/%Y")
            except ValueError:
                errors.append(field + "_must_be_MM_DD_YYYY")
    tier = canon_tier(data.get("tier"))
    amount = as_decimal(data.get("transaction_amount"))
    account_age = days_between(data.get("account_open_date"), data.get("as_of_date"))
    purchase_age = days_between(data.get("purchase_date"), data.get("as_of_date"))
    if data.get("tier") is not None and tier is None:
        errors.append("unrecognized_tier")
    if data.get("transaction_amount") is not None and amount is None:
        errors.append("invalid_transaction_amount")
    if data.get("account_open_date") is not None and account_age is None:
        errors.append("invalid_account_open_date_or_as_of_date")
    conditions = {}
    if not missing and not errors:
        conditions = {
            "account_age_at_least_60_days": account_age >= 60,
            "eligible_reason": reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"},
            "goods_not_received_purchase_more_than_30_days": reason != "goods_services_not_received" or purchase_age > 30,
            "amount_at_least_25": amount >= Decimal("25"),
            "amount_within_tier_limit": amount <= PROVISIONAL_LIMITS[tier],
            "no_more_than_two_prior_disputes": int(data["previous_disputes_last_12_months"]) <= 2,
            "merchant_contact_requirement": reason == "unauthorized_fraudulent_charge" or bool(data["contacted_merchant"]),
        }
    eligible = bool(conditions) and all(conditions.values())
    return {
        "missing": missing, "errors": errors, "tier": tier, "account_age_days": account_age,
        "purchase_age_days": purchase_age, "provisional_credit_conditions": conditions,
        "eligible_for_provisional_credit": eligible,
        "dispute_payload_ready": not missing and not errors,
    }


def assess_replacement(data):
    missing = require(data, ["tier", "reason", "shipping_address", "shipping_speed", "pending_order_statuses", "replacement_count_last_60_days"])
    errors = []
    tier = canon_tier(data.get("tier"))
    if data.get("tier") is not None and tier is None:
        errors.append("unrecognized_tier")
    if data.get("reason") is not None and data["reason"] not in {"fraud_suspected", "lost", "stolen", "damaged", "expired", "other"}:
        errors.append("invalid_replacement_reason")
    if data.get("shipping_speed") is not None and data["shipping_speed"] not in {"standard", "expedited"}:
        errors.append("invalid_shipping_speed")
    statuses = data.get("pending_order_statuses", [])
    if not isinstance(statuses, list):
        errors.append("pending_order_statuses_must_be_list")
        statuses = []
    has_pending = any(str(status).lower() not in {"delivered", "cancelled"} for status in statuses)
    count = data.get("replacement_count_last_60_days")
    if count is not None:
        try:
            count = int(count)
        except (TypeError, ValueError):
            errors.append("invalid_replacement_count_last_60_days")
    fee_required = tier in {"entry", "mid"} and data.get("shipping_speed") == "expedited"
    if fee_required and data.get("expedited_fee_acknowledgement") is not True:
        errors.append("expedited_fee_acknowledgement_required")
    eligible = not missing and not errors and not has_pending and count < REPLACEMENT_LIMITS[tier]
    return {
        "missing": missing, "errors": errors, "tier": tier, "has_pending_replacement": has_pending,
        "replacement_limit": REPLACEMENT_LIMITS.get(tier), "replacement_count_last_60_days": count,
        "eligible_to_submit": eligible,
    }


def assess_cli(data):
    base_required = ["tier", "current_credit_limit", "requested_increase_amount"]
    missing = require(data, base_required)
    errors = []
    tier = canon_tier(data.get("tier"))
    current = as_decimal(data.get("current_credit_limit"))
    requested = as_decimal(data.get("requested_increase_amount"))
    if tier not in CLI_RULES and data.get("tier") is not None:
        errors.append("cli_requires_entry_mid_or_premium_tier")
    if current is None and data.get("current_credit_limit") is not None:
        errors.append("invalid_current_credit_limit")
    if requested is None and data.get("requested_increase_amount") is not None:
        errors.append("invalid_requested_increase_amount")
    if requested is not None and (requested <= 0 or requested != requested.to_integral_value()):
        errors.append("requested_increase_must_be_positive_integer_dollars")
    maximum = current * CLI_RULES[tier]["max_fraction"] if current is not None and tier in CLI_RULES else None
    within_limit = maximum is not None and requested is not None and requested <= maximum
    result = {
        "missing": missing, "errors": errors, "tier": tier, "maximum_increase": str(maximum) if maximum is not None else None,
        "requested_within_limit": within_limit, "new_credit_limit": str(current + requested) if current is not None and requested is not None else None,
    }
    if missing or errors:
        result["pre_submission_action"] = "collect_or_correct_required_data"
        return result
    if not within_limit:
        result["pre_submission_action"] = "do_not_submit; request_customer_confirmation_of_in_limit_amount"
        return result
    post_fields = ["account_open_date", "as_of_date", "last_approved_cli_date", "active_disputes", "pending_replacement", "past_due_amount", "utilization_percent", "consecutive_on_time_months"]
    post_missing = require(data, post_fields)
    result["pre_submission_action"] = "submit_formal_cli_request_before_post_submission_checks"
    result["post_submission_missing"] = post_missing
    if post_missing:
        result["post_submission_decision"] = "unknown_do_not_approve_or_deny_until_checks_complete"
        return result
    age = days_between(data["account_open_date"], data["as_of_date"])
    cooldown_elapsed = days_between(data["last_approved_cli_date"], data["as_of_date"])
    utilization = as_decimal(data["utilization_percent"])
    past_due = as_decimal(data["past_due_amount"])
    if age is None or cooldown_elapsed is None or utilization is None or past_due is None:
        result["post_submission_decision"] = "unknown_invalid_date_or_numeric_eligibility_fact"
        return result
    rules = CLI_RULES[tier]
    checks = {
        "insufficient_account_age": age >= rules["age"],
        "cooldown_period_active": cooldown_elapsed >= rules["cooldown"],
        "pending_disputes": not bool(data["active_disputes"]),
        "pending_replacement_card": not bool(data["pending_replacement"]),
        "past_due_balance": past_due <= Decimal("0"),
        "high_utilization": utilization < rules["utilization"],
        "insufficient_payment_history": int(data["consecutive_on_time_months"]) >= rules["payment_months"],
    }
    failures = [reason for reason, passed in checks.items() if not passed]
    result.update({"account_age_days": age, "cooldown_days_elapsed": cooldown_elapsed, "post_submission_checks": checks, "failed_reasons": failures})
    if failures:
        result["post_submission_decision"] = "deny"
        result["denial_reason"] = failures[0]
    else:
        result["post_submission_decision"] = "approve"
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"error": "top_level_object_required"}))
        return
    output = {}
    for key, function in (("identity", assess_identity), ("dispute", assess_dispute), ("replacement", assess_replacement), ("cli", assess_cli)):
        if key in payload:
            if not isinstance(payload[key], dict):
                output[key] = {"error": key + "_must_be_object"}
            else:
                try:
                    output[key] = function(payload[key])
                except (TypeError, ValueError, KeyError) as exc:
                    output[key] = {"error": "invalid_" + key + "_data", "detail": str(exc)}
    if not output:
        output = {"error": "provide_at_least_one_of_identity_dispute_replacement_cli"}
    print(json.dumps(output, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
