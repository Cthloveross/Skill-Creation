#!/usr/bin/env python3
"""Evaluate documented provisional-credit rules.

Reads one JSON object from stdin. Required keys: account_open_date, as_of_date,
card_type, transaction_amount, purchase_date, dispute_reason,
contacted_merchant, disputes_past_12_months. Dates are MM/DD/YYYY. Emits a
JSON decision object; invalid or incomplete input is never treated as eligible.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

FMT = "%m/%d/%Y"
REASONS = {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
LIMITS = {
    "Bronze Rewards Card": "2500", "EcoCard": "2500", "Business Bronze Rewards Card": "2500", "Crypto-Cash Back Card": "2500",
    "Silver Rewards Card": "5000", "Business Silver Rewards Card": "5000", "Green Rewards Card": "5000", "Silver Zoom Card": "5000",
    "Gold Rewards Card": "10000", "Business Gold Rewards Card": "10000",
    "Platinum Rewards Card": "15000", "Business Platinum Rewards Card": "15000", "Diamond Elite Card": "25000",
}
REQUIRED = ("account_open_date", "as_of_date", "card_type", "transaction_amount", "purchase_date", "dispute_reason", "contacted_merchant", "disputes_past_12_months")

def date(value, name):
    if not isinstance(value, str): raise ValueError(f"{name} must be MM/DD/YYYY")
    try: return datetime.strptime(value, FMT).date()
    except ValueError: raise ValueError(f"{name} must be a real MM/DD/YYYY date")

def evaluate(d):
    missing = [k for k in REQUIRED if k not in d]
    if missing: return {"valid_input": False, "eligible_for_provisional_credit": False, "errors": ["missing required fields: " + ", ".join(missing)]}
    try:
        opened, today, purchase = date(d["account_open_date"], "account_open_date"), date(d["as_of_date"], "as_of_date"), date(d["purchase_date"], "purchase_date")
        if isinstance(d["transaction_amount"], bool): raise ValueError("transaction_amount must be numeric")
        amount = Decimal(str(d["transaction_amount"]))
        if not amount.is_finite() or amount < 0: raise ValueError("transaction_amount must be nonnegative and finite")
        count = d["disputes_past_12_months"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0: raise ValueError("disputes_past_12_months must be a nonnegative integer")
        if not isinstance(d["contacted_merchant"], bool): raise ValueError("contacted_merchant must be boolean")
    except (ValueError, InvalidOperation) as exc:
        return {"valid_input": False, "eligible_for_provisional_credit": False, "errors": [str(exc)]}
    account_days, purchase_days = (today-opened).days, (today-purchase).days
    reason, limit = d["dispute_reason"], LIMITS.get(d["card_type"])
    failures = []
    if account_days < 60: failures.append("account has been open fewer than 60 days")
    if reason not in REASONS: failures.append("dispute reason is not eligible for provisional credit")
    if reason == "goods_services_not_received" and purchase_days <= 30: failures.append("goods/services-not-received purchase is not more than 30 days old")
    if limit is None: failures.append("card type has no documented provisional-credit tier limit")
    else:
        limit = Decimal(limit)
        if amount < Decimal("25"): failures.append("transaction amount is under $25.00")
        if amount > limit: failures.append("transaction amount exceeds card tier limit")
    if count > 2: failures.append("more than two disputes were filed in the past 12 months")
    if reason != "unauthorized_fraudulent_charge" and not d["contacted_merchant"]: failures.append("merchant was not contacted for a non-fraud dispute")
    return {"valid_input": True, "eligible_for_provisional_credit": not failures, "reasons": failures, "account_age_days": account_days, "purchase_age_days": purchase_days, "transaction_amount": format(amount, ".2f"), "tier_limit": format(limit, ".2f") if limit is not None else None}

def main():
    try:
        obj = json.load(sys.stdin)
        if not isinstance(obj, dict): raise ValueError("input must be a JSON object")
        result = evaluate(obj)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"valid_input": False, "eligible_for_provisional_credit": False, "errors": [str(exc)]}
    print(json.dumps(result, sort_keys=True))
if __name__ == "__main__": main()
