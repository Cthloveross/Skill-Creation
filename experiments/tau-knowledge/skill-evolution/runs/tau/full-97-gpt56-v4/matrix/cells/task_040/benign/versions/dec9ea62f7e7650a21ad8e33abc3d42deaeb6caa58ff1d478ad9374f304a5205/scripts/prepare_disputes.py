#!/usr/bin/env python3
"""Validate credit-card dispute records and calculate provisional-credit eligibility.
Reads one JSON object from stdin and writes one JSON object to stdout. No side effects.
"""
import json
import sys
from datetime import datetime, date

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
LIMITS = {
    "Bronze Rewards Card": 2500.0, "EcoCard": 2500.0,
    "Business Bronze Rewards Card": 2500.0, "Crypto-Cash Back Card": 2500.0,
    "Silver Rewards Card": 5000.0, "Business Silver Rewards Card": 5000.0,
    "Green Rewards Card": 5000.0, "Silver Zoom Card": 5000.0,
    "Gold Rewards Card": 10000.0, "Business Gold Rewards Card": 10000.0,
    "Platinum Rewards Card": 15000.0, "Business Platinum Rewards Card": 15000.0,
    "Diamond Elite Card": 25000.0,
}

def parsed(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None

def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)

def main(data):
    filing_date = parsed(data.get("filing_date"))
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    common_missing = [k for k in ("full_name", "user_id", "phone", "email", "address") if not profile.get(k)]
    prior = data.get("prior_disputes_last_12_months")
    out = []
    for item in data.get("disputes", []):
        d = item if isinstance(item, dict) else {}
        missing = list(common_missing)
        errors = []
        for key in ("transaction_id", "card_last_4_digits", "purchase_date", "issue_noticed_date", "card_action", "contacted_merchant", "dispute_reason", "resolution_requested"):
            if key not in d or d.get(key) in (None, ""):
                missing.append(key)
        if not number(d.get("transaction_amount")):
            missing.append("transaction_amount")
        if filing_date is None:
            missing.append("filing_date")
        opened = parsed(d.get("account_open_date"))
        purchase = parsed(d.get("purchase_date"))
        noticed = parsed(d.get("issue_noticed_date"))
        if opened is None: missing.append("account_open_date")
        if purchase is None: errors.append("purchase_date must use MM/DD/YYYY")
        if noticed is None: errors.append("issue_noticed_date must use MM/DD/YYYY")
        if d.get("card_action") not in ACTIONS: errors.append("invalid card_action")
        if d.get("dispute_reason") not in REASONS: errors.append("invalid dispute_reason")
        if d.get("resolution_requested") not in RESOLUTIONS: errors.append("invalid resolution_requested")
        if "contacted_merchant" in d and not isinstance(d.get("contacted_merchant"), bool): errors.append("contacted_merchant must be boolean")
        last4 = d.get("card_last_4_digits")
        if last4 not in (None, "") and (not isinstance(last4, str) or len(last4) != 4 or not last4.isdigit()): errors.append("card_last_4_digits must be exactly four digits")
        partial = d.get("partial_refund_amount")
        if d.get("resolution_requested") == "partial_refund":
            if not number(partial) or partial <= 0: missing.append("partial_refund_amount")
            elif number(d.get("transaction_amount")) and partial > d["transaction_amount"]: errors.append("partial_refund_amount exceeds transaction_amount")
        elif partial is not None:
            errors.append("partial_refund_amount is allowed only for partial_refund")

        limit = d.get("max_provisional_credit_limit", LIMITS.get(d.get("card_type")))
        eligibility_reasons = []
        decision_missing = []
        if not number(prior) or prior < 0: decision_missing.append("prior_disputes_last_12_months")
        if not number(limit): decision_missing.append("card_type or max_provisional_credit_limit")
        if filing_date is None or opened is None or purchase is None or not number(d.get("transaction_amount")):
            decision_missing.append("eligibility date/amount inputs")
        if decision_missing:
            errors.extend(x for x in decision_missing if x not in errors)
            eligible = False
        else:
            age = (filing_date - opened).days
            old_purchase = (filing_date - purchase).days
            reason = d.get("dispute_reason")
            amount = d["transaction_amount"]
            if age < 60: eligibility_reasons.append("account open fewer than 60 days")
            if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}: eligibility_reasons.append("reason is not eligible")
            if reason == "goods_services_not_received" and old_purchase <= 30: eligibility_reasons.append("goods/services-not-received purchase is not more than 30 days old")
            if amount < 25 or amount > limit: eligibility_reasons.append("amount is outside provisional-credit limit")
            if prior > 2: eligibility_reasons.append("more than two disputes in prior 12 months")
            if reason != "unauthorized_fraudulent_charge" and d.get("contacted_merchant") is not True: eligibility_reasons.append("merchant was not contacted for non-fraud dispute")
            eligible = not eligibility_reasons
        valid = not missing and not errors
        result = {"transaction_id": d.get("transaction_id"), "valid": valid, "missing": sorted(set(missing)), "errors": sorted(set(errors)), "eligibility": {"eligible_for_provisional_credit": eligible, "reasons": eligibility_reasons}}
        if valid:
            payload = {"transaction_id": d["transaction_id"], "card_action": d["card_action"], "card_last_4_digits": d["card_last_4_digits"], **profile, "contacted_merchant": d["contacted_merchant"], "purchase_date": d["purchase_date"], "issue_noticed_date": d["issue_noticed_date"], "dispute_reason": d["dispute_reason"], "resolution_requested": d["resolution_requested"], "eligible_for_provisional_credit": eligible}
            if d["resolution_requested"] == "partial_refund": payload["partial_refund_amount"] = d["partial_refund_amount"]
            result["payload"] = payload
        out.append(result)
    return {"results": out}

if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict): raise ValueError("top-level input must be an object")
        print(json.dumps(main(source), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
