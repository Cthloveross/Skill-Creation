#!/usr/bin/env python3
"""Validate and plan credit-card dispute tool calls.

Input JSON:
{
  "as_of": "MM/DD/YYYY" | "YYYY-MM-DD" | ISO timestamp,
  "profile": {"full_name": str, "user_id": str, "phone": str,
              "email": str, "address": str},
  "prior_disputes": [{"dispute_date": date-string}, ...],
  "transactions": [{
    "transaction_id": str, "amount": number or money-string,
    "purchase_date": "MM/DD/YYYY", "issue_noticed_date": "MM/DD/YYYY",
    "reason": allowed reason, "resolution_requested": allowed resolution,
    "partial_refund_amount": number (only for partial_refund),
    "contacted_merchant": boolean, "card_action": allowed card action,
    "card_last_4_digits": "1234", "card_type": known card type,
    "account_open_date": date-string
  }]
}

`prior_disputes` must be supplied from a successful complete dispute-history lookup;
an empty list means the successful lookup found no disputes. Output contains one result per
transaction. A result is ready only if it has valid filing fields and all provisional-credit
evidence. Each ready result contains exact arguments for
file_credit_card_transaction_dispute_4829.
"""
import json
import sys
from datetime import datetime, date, timedelta

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
TIER_CAPS = {
    "Bronze Rewards Card": 2500.0,
    "EcoCard": 2500.0,
    "Business Bronze Rewards Card": 2500.0,
    "Crypto-Cash Back Card": 2500.0,
    "Silver Rewards Card": 5000.0,
    "Business Silver Rewards Card": 5000.0,
    "Green Rewards Card": 5000.0,
    "Silver Zoom Card": 5000.0,
    "Gold Rewards Card": 10000.0,
    "Business Gold Rewards Card": 10000.0,
    "Platinum Rewards Card": 15000.0,
    "Business Platinum Rewards Card": 15000.0,
    "Diamond Elite Card": 25000.0,
}


def parse_date(value):
    """Return a date for supported date strings, or raise ValueError."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("invalid date: " + text) from exc


def money(value):
    if isinstance(value, bool):
        raise ValueError("must be a number")
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    result = float(value)
    if result < 0:
        raise ValueError("must not be negative")
    return result


def recent_dispute_count(records, as_of):
    """Count filed disputes dated within the preceding 365 days, inclusive."""
    cutoff = as_of - timedelta(days=365)
    count = 0
    errors = []
    for index, record in enumerate(records):
        try:
            filed = parse_date(record.get("dispute_date"))
        except (AttributeError, ValueError):
            errors.append("prior_disputes[%d] has no valid dispute_date" % index)
            continue
        if cutoff <= filed <= as_of:
            count += 1
    return count, errors


def eligibility(tx, as_of, prior_count):
    """Return (bool, rationale list, evidence-error list)."""
    errors, rationale = [], []
    try:
        opened = parse_date(tx.get("account_open_date"))
        account_ok = (as_of - opened).days >= 60
        rationale.append("account_open_at_least_60_days=" + str(account_ok).lower())
    except ValueError:
        errors.append("account_open_date is required to determine provisional-credit eligibility")
        account_ok = False
    try:
        amount = money(tx.get("amount"))
    except (TypeError, ValueError):
        errors.append("valid transaction amount is required to determine provisional-credit eligibility")
        amount = 0.0
    card_type = tx.get("card_type")
    cap = TIER_CAPS.get(card_type)
    if cap is None:
        errors.append("known card_type is required to determine the provisional-credit limit")
        amount_ok = False
    else:
        amount_ok = 25.0 <= amount <= cap
        rationale.append("amount_within_tier_limit=" + str(amount_ok).lower())
    reason = tx.get("reason")
    reason_ok = reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
    if reason == "goods_services_not_received":
        try:
            purchase = parse_date(tx.get("purchase_date"))
            delivery_age_ok = (as_of - purchase).days > 30
            rationale.append("not_received_purchase_more_than_30_days_old=" + str(delivery_age_ok).lower())
            reason_ok = reason_ok and delivery_age_ok
        except ValueError:
            errors.append("purchase_date is required for goods_services_not_received eligibility")
            reason_ok = False
    rationale.append("eligible_reason=" + str(reason_ok).lower())
    history_ok = prior_count <= 2
    rationale.append("no_more_than_two_prior_disputes_in_12_months=" + str(history_ok).lower())
    merchant = tx.get("contacted_merchant")
    if not isinstance(merchant, bool):
        errors.append("contacted_merchant must be boolean")
        merchant_ok = False
    else:
        merchant_ok = reason == "unauthorized_fraudulent_charge" or merchant
        rationale.append("merchant_contact_requirement_met=" + str(merchant_ok).lower())
    return (not errors and account_ok and amount_ok and reason_ok and history_ok and merchant_ok), rationale, errors


def plan_case(tx, profile, as_of, prior_count):
    errors = []
    for field in ("transaction_id",):
        if not isinstance(tx.get(field), str) or not tx[field].strip():
            errors.append(field + " is required")
    for field in ("full_name", "user_id", "phone", "email", "address"):
        if not isinstance(profile.get(field), str) or not profile[field].strip():
            errors.append("profile." + field + " is required")
    if tx.get("reason") not in REASONS:
        errors.append("reason must be one of the supported dispute reasons")
    if tx.get("resolution_requested") not in RESOLUTIONS:
        errors.append("resolution_requested must be a supported resolution")
    if tx.get("card_action") not in ACTIONS:
        errors.append("card_action must be keep_active or cancel_and_reissue")
    last4 = tx.get("card_last_4_digits")
    if not isinstance(last4, str) or len(last4) != 4 or not last4.isdigit():
        errors.append("card_last_4_digits must be exactly four digits")
    if not isinstance(tx.get("contacted_merchant"), bool):
        errors.append("contacted_merchant must be boolean")
    for field in ("purchase_date", "issue_noticed_date"):
        try:
            parse_date(tx.get(field))
        except ValueError:
            errors.append(field + " must be a valid date")
    if tx.get("resolution_requested") == "partial_refund":
        try:
            partial = money(tx.get("partial_refund_amount"))
            if partial <= 0:
                errors.append("partial_refund_amount must be greater than zero")
        except (TypeError, ValueError):
            errors.append("partial_refund_amount is required and must be numeric for partial_refund")
    elif "partial_refund_amount" in tx and tx.get("partial_refund_amount") is not None:
        errors.append("partial_refund_amount is allowed only for partial_refund")

    eligible, rationale, eligibility_errors = eligibility(tx, as_of, prior_count)
    errors.extend(eligibility_errors)
    result = {
        "transaction_id": tx.get("transaction_id"),
        "ready": False,
        "eligible_for_provisional_credit": eligible if not eligibility_errors else None,
        "eligibility_rationale": rationale,
        "errors": errors,
    }
    if errors:
        return result
    args = {
        "transaction_id": tx["transaction_id"],
        "card_action": tx["card_action"],
        "card_last_4_digits": last4,
        "full_name": profile["full_name"],
        "user_id": profile["user_id"],
        "phone": profile["phone"],
        "email": profile["email"],
        "address": profile["address"],
        "contacted_merchant": tx["contacted_merchant"],
        "purchase_date": parse_date(tx["purchase_date"]).strftime("%m/%d/%Y"),
        "issue_noticed_date": parse_date(tx["issue_noticed_date"]).strftime("%m/%d/%Y"),
        "dispute_reason": tx["reason"],
        "resolution_requested": tx["resolution_requested"],
        "eligible_for_provisional_credit": eligible,
    }
    if tx["resolution_requested"] == "partial_refund":
        args["partial_refund_amount"] = money(tx["partial_refund_amount"])
    result.update({"ready": True, "filing_arguments": args})
    return result


def main():
    try:
        data = json.load(sys.stdin)
        as_of = parse_date(data.get("as_of"))
        profile = data.get("profile") or {}
        records = data.get("prior_disputes")
        transactions = data.get("transactions")
        if not isinstance(records, list):
            raise ValueError("prior_disputes must be a list from a successful dispute-history lookup")
        if not isinstance(transactions, list):
            raise ValueError("transactions must be a list")
        prior_count, history_errors = recent_dispute_count(records, as_of)
        results = []
        for tx in transactions:
            if not isinstance(tx, dict):
                results.append({"transaction_id": None, "ready": False, "errors": ["transaction must be an object"]})
                continue
            item = plan_case(tx, profile, as_of, prior_count)
            if history_errors:
                item["ready"] = False
                item.pop("filing_arguments", None)
                item["eligible_for_provisional_credit"] = None
                item["errors"].extend(history_errors)
            results.append(item)
        print(json.dumps({"as_of": as_of.isoformat(), "prior_disputes_in_last_12_months": prior_count,
                          "results": results}, separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)

if __name__ == "__main__":
    main()
