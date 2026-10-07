#!/usr/bin/env python3
"""Read-only validation for credit-card dispute, replacement, and CLI workflows.

Input: JSON object with optional identity, dispute, replacement, and cli objects.
Output: JSON object containing deterministic calculations and validation results.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

CLI = {
    "entry": {"age": 120, "cooldown": 120, "util": Decimal("70"), "months": 6, "fraction": Decimal(".25")},
    "mid": {"age": 90, "cooldown": 90, "util": Decimal("80"), "months": 3, "fraction": Decimal(".50")},
    "premium": {"age": 60, "cooldown": 60, "util": Decimal("90"), "months": 3, "fraction": Decimal(".50")},
}
PROVISIONAL_CAP = {"entry": Decimal("2500"), "mid": Decimal("5000"), "premium": Decimal("10000"), "elite": Decimal("15000"), "invitation": Decimal("25000")}
REPLACEMENT_CAP = {"entry": 2, "mid": 3, "premium": 4, "elite": 4, "invitation": 4}


def tier(value):
    """Map documented card names and tier labels; Gold is always Premium."""
    if not isinstance(value, str):
        return None
    value = value.lower().replace("_", " ").replace("-", " ")
    if "diamond" in value or "invitation" in value:
        return "invitation"
    if "platinum" in value or "elite" in value:
        return "elite"
    if "gold" in value or "premium" in value:
        return "premium"
    if any(x in value for x in ("silver", "green", "mid")):
        return "mid"
    if any(x in value for x in ("bronze", "eco", "crypto", "entry")):
        return "entry"
    return None


def money(value):
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def day(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip()[:10], fmt).date()
        except ValueError:
            pass
    return None


def elapsed(start, end):
    start, end = day(start), day(end)
    return (end - start).days if start and end else None


def required(data, names):
    return [name for name in names if data.get(name) is None or data.get(name) == ""]


def identity(data):
    record = data.get("record") if isinstance(data.get("record"), dict) else {}
    supplied = data.get("supplied") if isinstance(data.get("supplied"), dict) else {}
    fields = ("date_of_birth", "email", "phone", "address")
    compared = [x for x in fields if x in record and x in supplied]
    matched = [x for x in compared if str(record[x]).strip() == str(supplied[x]).strip()]
    return {"available_comparisons": compared, "matched_fields": matched,
            "match_count": len(matched), "verified": len(matched) >= 2,
            "next_action": "log_verification" if len(matched) >= 2 else "collect_or_correct_identity_fields"}


def dispute(data):
    fields = ("transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id", "phone", "email", "address", "contacted_merchant", "purchase_date", "issue_noticed_date", "dispute_reason", "resolution_requested", "account_open_date", "as_of_date", "transaction_amount", "tier", "previous_disputes_last_12_months")
    missing, errors = required(data, fields), []
    reason, resolution, card_tier = data.get("dispute_reason"), data.get("resolution_requested"), tier(data.get("tier"))
    if data.get("card_action") not in (None, "keep_active", "cancel_and_reissue"): errors.append("invalid_card_action")
    if reason not in (None, "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount", "goods_services_not_received", "goods_services_not_as_described", "canceled_subscription_still_charging", "refund_never_processed"): errors.append("invalid_dispute_reason")
    if resolution not in (None, "full_refund", "partial_refund", "reversal_of_charge"): errors.append("invalid_resolution_requested")
    if resolution == "partial_refund" and money(data.get("partial_refund_amount")) is None: errors.append("partial_refund_amount_required")
    if resolution != "partial_refund" and data.get("partial_refund_amount") not in (None, ""): errors.append("partial_refund_amount_not_applicable")
    for field in ("purchase_date", "issue_noticed_date"):
        if data.get(field) is not None:
            try: datetime.strptime(str(data[field]), "%m/%d/%Y")
            except ValueError: errors.append(field + "_must_be_MM_DD_YYYY")
    amount, age, purchase_age = money(data.get("transaction_amount")), elapsed(data.get("account_open_date"), data.get("as_of_date")), elapsed(data.get("purchase_date"), data.get("as_of_date"))
    if data.get("tier") is not None and card_tier is None: errors.append("unrecognized_tier")
    if data.get("transaction_amount") is not None and amount is None: errors.append("invalid_transaction_amount")
    conditions = {}
    if not missing and not errors:
        try: prior_ok = int(data["previous_disputes_last_12_months"]) <= 2
        except (TypeError, ValueError): errors.append("invalid_previous_disputes_last_12_months"); prior_ok = False
        conditions = {"account_age_at_least_60_days": age is not None and age >= 60,
                      "eligible_reason": reason in ("unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"),
                      "goods_not_received_purchase_more_than_30_days": reason != "goods_services_not_received" or (purchase_age is not None and purchase_age > 30),
                      "amount_at_least_25": amount >= 25,
                      "amount_within_tier_limit": amount <= PROVISIONAL_CAP[card_tier],
                      "no_more_than_two_prior_disputes": prior_ok,
                      "merchant_contact_requirement": reason == "unauthorized_fraudulent_charge" or bool(data["contacted_merchant"])}
    return {"missing": missing, "errors": errors, "tier": card_tier, "account_age_days": age,
            "purchase_age_days": purchase_age, "provisional_credit_conditions": conditions,
            "eligible_for_provisional_credit": bool(conditions) and not errors and all(conditions.values()),
            "dispute_payload_ready": not missing and not errors}


def replacement(data):
    missing, errors = required(data, ("tier", "reason", "shipping_address", "shipping_speed", "pending_order_statuses", "replacement_count_last_60_days")), []
    card_tier, statuses = tier(data.get("tier")), data.get("pending_order_statuses", [])
    if card_tier is None and data.get("tier") is not None: errors.append("unrecognized_tier")
    if data.get("reason") not in (None, "fraud_suspected", "lost", "stolen", "damaged", "expired", "other"): errors.append("invalid_replacement_reason")
    if data.get("shipping_speed") not in (None, "standard", "expedited"): errors.append("invalid_shipping_speed")
    if not isinstance(statuses, list): errors.append("pending_order_statuses_must_be_list"); statuses = []
    try: count = int(data.get("replacement_count_last_60_days"))
    except (TypeError, ValueError): count = None; errors.append("invalid_replacement_count_last_60_days")
    fee = card_tier in ("entry", "mid") and data.get("shipping_speed") == "expedited"
    if fee and data.get("expedited_fee_acknowledgement") is not True: errors.append("expedited_fee_acknowledgement_required")
    pending = any(str(x).lower() not in ("delivered", "cancelled") for x in statuses)
    eligible = not missing and not errors and not pending and count < REPLACEMENT_CAP[card_tier]
    return {"missing": missing, "errors": errors, "tier": card_tier, "has_pending_replacement": pending,
            "replacement_limit": REPLACEMENT_CAP.get(card_tier), "replacement_count_last_60_days": count,
            "eligible_to_submit": eligible}


def cli(data):
    missing, errors = required(data, ("tier", "current_credit_limit", "requested_increase_amount")), []
    card_tier, current, request = tier(data.get("tier")), money(data.get("current_credit_limit")), money(data.get("requested_increase_amount"))
    if card_tier not in CLI and data.get("tier") is not None: errors.append("cli_requires_entry_mid_or_premium_tier")
    if current is None and data.get("current_credit_limit") is not None: errors.append("invalid_current_credit_limit")
    if request is None and data.get("requested_increase_amount") is not None: errors.append("invalid_requested_increase_amount")
    if request is not None and (request <= 0 or request != request.to_integral_value()): errors.append("requested_increase_must_be_positive_integer_dollars")
    maximum = current * CLI[card_tier]["fraction"] if current is not None and card_tier in CLI else None
    within = maximum is not None and request is not None and request <= maximum
    result = {"missing": missing, "errors": errors, "tier": card_tier,
              "maximum_increase": str(maximum) if maximum is not None else None,
              "requested_within_limit": within,
              "new_credit_limit": str(current + request) if current is not None and request is not None else None}
    if missing or errors: result["pre_submission_action"] = "collect_or_correct_required_data"; return result
    if not within: result["pre_submission_action"] = "do_not_submit_or_deny; explain_maximum_and_request_revised_amount"; return result
    result["pre_submission_action"] = "submit_formal_cli_request_before_post_submission_checks"
    post = ("account_open_date", "as_of_date", "active_disputes", "pending_replacement", "past_due_amount", "utilization_percent", "consecutive_on_time_months")
    post_missing = required(data, post)
    result["post_submission_missing"] = post_missing
    if post_missing: result["post_submission_decision"] = "unknown_do_not_approve_or_deny_until_checks_complete"; return result
    age, util, past_due = elapsed(data["account_open_date"], data["as_of_date"]), money(data["utilization_percent"]), money(data["past_due_amount"])
    last = data.get("last_approved_cli_date")
    cooldown = elapsed(last, data["as_of_date"]) if last not in (None, "") else None
    if age is None or util is None or past_due is None or (last not in (None, "") and cooldown is None): result["post_submission_decision"] = "unknown_invalid_eligibility_fact"; return result
    rules = CLI[card_tier]
    try: payments_ok = int(data["consecutive_on_time_months"]) >= rules["months"]
    except (TypeError, ValueError): result["post_submission_decision"] = "unknown_invalid_eligibility_fact"; return result
    checks = {"insufficient_account_age": age >= rules["age"], "cooldown_period_active": cooldown is None or cooldown >= rules["cooldown"], "pending_disputes": not bool(data["active_disputes"]), "pending_replacement_card": not bool(data["pending_replacement"]), "past_due_balance": past_due <= 0, "high_utilization": util < rules["util"], "insufficient_payment_history": payments_ok}
    failures = [key for key, passed in checks.items() if not passed]
    result.update({"account_age_days": age, "cooldown_days_elapsed": cooldown, "post_submission_checks": checks, "failed_reasons": failures, "post_submission_decision": "deny" if failures else "approve"})
    if failures: result["denial_reason"] = failures[0]
    return result


def main():
    try: payload = json.load(sys.stdin)
    except Exception as exc: print(json.dumps({"error": "invalid_json", "detail": str(exc)})); return
    if not isinstance(payload, dict): print(json.dumps({"error": "top_level_object_required"})); return
    functions = {"identity": identity, "dispute": dispute, "replacement": replacement, "cli": cli}
    output = {}
    for name, function in functions.items():
        if name in payload:
            if not isinstance(payload[name], dict): output[name] = {"error": name + "_must_be_object"}
            else:
                try: output[name] = function(payload[name])
                except (KeyError, TypeError, ValueError) as exc: output[name] = {"error": "invalid_" + name + "_data", "detail": str(exc)}
    print(json.dumps(output or {"error": "provide_at_least_one_of_identity_dispute_replacement_cli"}, sort_keys=True, default=str))

if __name__ == "__main__":
    main()
