#!/usr/bin/env python3
"""Pure credit-card eligibility helper.

Input JSON schema:
{
  "as_of_date": "MM/DD/YYYY or YYYY-MM-DD", "account_open_date": "...",
  "card_tier": "entry|mid|premium|elite|invitation",
  "transaction_amount": number, "purchase_date": "...",
  "dispute_reason": string, "contacted_merchant": bool,
  "prior_disputes_last_12_months": integer,
  "current_credit_limit": number, "requested_increase_amount": number,
  "account_age_days": optional integer, "utilization_percent": optional number,
  "days_since_last_approved_cli": optional integer,
  "consecutive_on_time_months": optional integer,
  "has_pending_disputes": optional bool,
  "has_pending_replacement": optional bool,
  "past_due_amount": optional number
}
Output includes provisional-credit eligibility and CLI amount/basic-check results.
Missing values make the affected test false and are listed in unknown_inputs.
"""
import datetime as dt
import json
import sys


def date_value(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def tier_key(raw):
    text = str(raw or "").strip().lower()
    if text in {"entry", "entry-tier"}:
        return "entry"
    if text in {"mid", "mid-tier"}:
        return "mid"
    if text in {"premium", "premium-tier"}:
        return "premium"
    if text in {"elite", "elite-tier"}:
        return "elite"
    if text in {"invitation", "invitation-tier"}:
        return "invitation"
    return None


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main(data):
    tier = tier_key(data.get("card_tier"))
    as_of = date_value(data.get("as_of_date"))
    opened = date_value(data.get("account_open_date"))
    purchase = date_value(data.get("purchase_date"))
    unknown = []
    if not tier:
        unknown.append("card_tier")
    if not as_of:
        unknown.append("as_of_date")
    age = data.get("account_age_days")
    if not numeric(age):
        age = (as_of - opened).days if as_of and opened else None
    if age is None:
        unknown.append("account_age_days/account_open_date")

    provisional_max = {"entry": 2500, "mid": 5000, "premium": 10000,
                       "elite": 15000, "invitation": 25000}
    amount = data.get("transaction_amount")
    reason = data.get("dispute_reason")
    reason_ok = reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
    delivery_age_ok = True
    if reason == "goods_services_not_received":
        delivery_age_ok = bool(as_of and purchase and (as_of - purchase).days > 30)
        if not purchase:
            unknown.append("purchase_date")
    amount_ok = numeric(amount) and tier is not None and 25 <= amount <= provisional_max[tier]
    disputes = data.get("prior_disputes_last_12_months")
    disputes_ok = isinstance(disputes, int) and not isinstance(disputes, bool) and disputes <= 2
    if not isinstance(disputes, int) or isinstance(disputes, bool):
        unknown.append("prior_disputes_last_12_months")
    merchant_ok = reason == "unauthorized_fraudulent_charge" or data.get("contacted_merchant") is True
    if reason != "unauthorized_fraudulent_charge" and not isinstance(data.get("contacted_merchant"), bool):
        unknown.append("contacted_merchant")
    provisional_checks = {
        "account_open_at_least_60_days": numeric(age) and age >= 60,
        "eligible_reason": reason_ok,
        "goods_not_received_more_than_30_days": delivery_age_ok,
        "amount_within_tier_limit": amount_ok,
        "no_more_than_two_prior_disputes": disputes_ok,
        "merchant_contact_requirement_met": merchant_ok,
    }

    cli_age = {"entry": 120, "mid": 90, "premium": 60}
    cli_util = {"entry": 70, "mid": 80, "premium": 90}
    cli_months = {"entry": 6, "mid": 3, "premium": 3}
    cli_pct = {"entry": .25, "mid": .50, "premium": .50}
    cli_supported = tier in cli_age
    if not cli_supported:
        unknown.append("cli_tier_mapping")
    limit = data.get("current_credit_limit")
    requested = data.get("requested_increase_amount")
    max_increase = limit * cli_pct[tier] if cli_supported and numeric(limit) else None
    if max_increase is None:
        unknown.append("current_credit_limit")
    cooldown = data.get("days_since_last_approved_cli")
    utilization = data.get("utilization_percent")
    on_time = data.get("consecutive_on_time_months")
    cli_checks = {
        "requested_amount_within_maximum": numeric(requested) and max_increase is not None and requested <= max_increase,
        "minimum_account_age": cli_supported and numeric(age) and age >= cli_age[tier],
        "cooldown_elapsed": cli_supported and numeric(cooldown) and cooldown >= cli_age[tier],
        "no_pending_disputes": data.get("has_pending_disputes") is False,
        "no_pending_replacement": data.get("has_pending_replacement") is False,
        "no_past_due_balance": numeric(data.get("past_due_amount")) and data["past_due_amount"] <= 0,
        "utilization_below_threshold": cli_supported and numeric(utilization) and utilization < cli_util[tier],
        "consecutive_on_time_payments": cli_supported and numeric(on_time) and on_time >= cli_months[tier],
    }
    for key, value in (("days_since_last_approved_cli", cooldown), ("utilization_percent", utilization),
                       ("consecutive_on_time_months", on_time), ("has_pending_disputes", data.get("has_pending_disputes")),
                       ("has_pending_replacement", data.get("has_pending_replacement")), ("past_due_amount", data.get("past_due_amount"))):
        if value is None:
            unknown.append(key)
    output = {
        "normalized_tier": tier,
        "account_age_days": age,
        "provisional_credit_checks": provisional_checks,
        "eligible_for_provisional_credit": all(provisional_checks.values()),
        "maximum_cli_increase": max_increase,
        "new_credit_limit_if_approved": (limit + requested if numeric(limit) and numeric(requested) else None),
        "cli_checks": cli_checks,
        "cli_basic_eligibility_established": cli_supported and all(cli_checks.values()),
        "unknown_inputs": sorted(set(unknown)),
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        main(payload)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
