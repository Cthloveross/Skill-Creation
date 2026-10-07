#!/usr/bin/env python3
"""Assess referral eligibility and product fit without taking a banking action.

Read one JSON object from stdin and write one JSON object to stdout.

Input schema (all unknown facts should be null, not guessed):
{
  "as_of": "ISO-8601 timestamp",
  "funding_amount": number or decimal string or null,
  "referrer_tenure_days": integer or null,
  "annual_bonus_count": integer or null,
  "successful_bonus_timestamps": ["ISO-8601 timestamp", ...] or null,
  "eligibility": {
    "identity_verified": true|false|null,
    "referrer_is_checking_customer": true|false|null,
    "referred_new_customer": true|false|null,
    "different_registered_address": true|false|null,
    "distinct_business_primary_owner": true|false|null,
    "deposit_is_new_money": true|false|null,
    "referrer_in_good_standing": true|false|null,
    "referred_will_be_in_good_standing": true|false|null
  }
}

`annual_bonus_count` must be the applicable selected-program calendar-year count.
The script cannot determine that count from a general referral list.  Results are
advisory: `recommendation_permitted` never authorizes a referral submission.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "references" / "business_referral_programs.json").read_text(encoding="utf-8"))


def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
        if result.tzinfo is None:
            return None
        return result.astimezone(timezone.utc)
    except ValueError:
        return None


def tri(value):
    return value if isinstance(value, bool) else None


def status(condition, reason):
    if condition is True:
        return {"status": "pass", "reason": reason}
    if condition is False:
        return {"status": "fail", "reason": reason}
    return {"status": "unknown", "reason": reason}


def main():
    errors = []
    try:
        raw = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"input_errors": ["Input must be one JSON object: " + str(exc)]}, sort_keys=True))
        return
    if not isinstance(raw, dict):
        print(json.dumps({"input_errors": ["Input must be a JSON object."]}, sort_keys=True))
        return

    as_of = parse_time(raw.get("as_of"))
    if as_of is None:
        errors.append("as_of must be a timezone-aware ISO-8601 timestamp.")

    amount = None
    if raw.get("funding_amount") is not None:
        try:
            amount = Decimal(str(raw["funding_amount"]))
            if amount < 0:
                errors.append("funding_amount cannot be negative.")
        except (InvalidOperation, ValueError):
            errors.append("funding_amount must be numeric, a decimal string, or null.")

    tenure = raw.get("referrer_tenure_days")
    if tenure is not None and (not isinstance(tenure, int) or isinstance(tenure, bool) or tenure < 0):
        errors.append("referrer_tenure_days must be a nonnegative integer or null.")
        tenure = None
    annual_count = raw.get("annual_bonus_count")
    if annual_count is not None and (not isinstance(annual_count, int) or isinstance(annual_count, bool) or annual_count < 0):
        errors.append("annual_bonus_count must be a nonnegative integer or null.")
        annual_count = None

    eligibility = raw.get("eligibility") if isinstance(raw.get("eligibility"), dict) else {}
    gate_fields = [
        ("identity_verified", "Customer identity must be verified before account-specific checks or actions."),
        ("referrer_is_checking_customer", "Referrer must be a Rho-Bank checking customer."),
        ("referred_new_customer", "Referred party must have no Rho-Bank checking, savings, or closed account in the prior 12 months."),
        ("different_registered_address", "Referrer and referred party must have different registered addresses."),
        ("distinct_business_primary_owner", "Business primary owner/authorized signer must be distinct from existing Rho-Bank business-account primary owners.")
    ]
    gate = {key: status(tri(eligibility.get(key)), reason) for key, reason in gate_fields}
    gate_values = [tri(eligibility.get(key)) for key, _ in gate_fields]
    gate_passed = all(value is True for value in gate_values)

    rolling_count = None
    stamps = raw.get("successful_bonus_timestamps")
    if stamps is not None:
        if not isinstance(stamps, list):
            errors.append("successful_bonus_timestamps must be a list or null.")
        elif as_of is not None:
            parsed = [parse_time(x) for x in stamps]
            if any(x is None for x in parsed):
                errors.append("Every successful_bonus_timestamps item must be timezone-aware ISO-8601.")
            else:
                start = as_of - timedelta(days=CATALOG["global_terms"]["rolling_window_days"])
                rolling_count = sum(start <= item <= as_of for item in parsed)

    assessments = []
    for product in CATALOG["programs"]:
        checks = {
            "tenure": status(None if tenure is None else tenure >= product["referrer_tenure_days"], "Earliest checking tenure must meet the product threshold."),
            "funding": status(None if amount is None else amount >= Decimal(str(product["qualifying_deposit"])), "Planned qualifying deposit must meet the product minimum."),
            "new_money": status(tri(eligibility.get("deposit_is_new_money")), "Qualifying deposit must be new money, not an internal Rho-Bank transfer."),
            "rolling_nine_day_limit": status(None if rolling_count is None else rolling_count < 2, "No more than two successful bonuses may fall in the rolling nine-day window."),
            "annual_cap": status(None if annual_count is None else annual_count < product["annual_cap"], "Applicable calendar-year bonus count must be below the product annual cap."),
            "referrer_good_standing": status(tri(eligibility.get("referrer_in_good_standing")), "Referrer must remain in good standing."),
            "referred_good_standing": status(tri(eligibility.get("referred_will_be_in_good_standing")), "Referred account must remain in good standing.")
        }
        states = [entry["status"] for entry in checks.values()]
        fully_qualified = gate_passed and all(item == "pass" for item in states)
        potential = not any(item == "fail" for item in states)
        assessments.append({
            "product": product["name"],
            "referrer_bonus": product["referrer_bonus"],
            "referred_bonus": product["referred_bonus"],
            "qualifying_deposit": product["qualifying_deposit"],
            "deposit_window_days": product["deposit_window_days"],
            "referrer_tenure_days": product["referrer_tenure_days"],
            "annual_cap": product["annual_cap"],
            "checks": checks,
            "eligible": fully_qualified,
            "potentially_eligible_if_unknowns_confirmed": potential
        })

    eligible = sorted((x for x in assessments if x["eligible"]), key=lambda x: (-x["referrer_bonus"], x["product"]))
    missing_gate = [key for key, item in gate.items() if item["status"] == "unknown"]
    failed_gate = [key for key, item in gate.items() if item["status"] == "fail"]
    result = {
        "input_errors": errors,
        "eligibility_gate": gate,
        "rolling_successful_bonus_count": rolling_count,
        "product_assessments": assessments,
        "recommendation_permitted": bool(not errors and gate_passed and eligible),
        "eligible_products": eligible,
        "largest_referrer_bonus_product": eligible[0] if eligible else None,
        "missing_gate_confirmations": missing_gate,
        "failed_gate_conditions": failed_gate,
        "continuing_conditions": {
            "deposit_retention_days_after_qualifying_period": CATALOG["global_terms"]["deposit_retention_days_after_qualifying_period"],
            "possible_clawback_if_referred_account_closed_within_days": CATALOG["global_terms"]["possible_clawback_if_referred_account_closed_within_days"],
            "one_referral_code_and_no_promotion_stacking": True
        }
    }
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
