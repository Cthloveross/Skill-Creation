#!/usr/bin/env python3
"""Evaluate provisional-credit policy facts supplied as a JSON object on stdin."""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

CAPS = {
    "entry": Decimal("2500"), "mid": Decimal("5000"),
    "premium": Decimal("10000"), "elite": Decimal("15000"),
    "invitation": Decimal("25000"),
}
ALLOWED = {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}

def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("must be a date string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("must use YYYY-MM-DD or MM/DD/YYYY")

def money(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("must be numeric")
    if not result.is_finite():
        raise ValueError("must be finite")
    return result

def main(data):
    results = []
    try:
        today = parse_date(data.get("current_date"))
    except ValueError as exc:
        today, common_date_error = None, "current_date " + str(exc)
    else:
        common_date_error = None
    try:
        opened = parse_date(data.get("account_open_date"))
    except ValueError as exc:
        opened, open_error = None, "account_open_date " + str(exc)
    else:
        open_error = None
    tier = str(data.get("card_tier", "")).strip().lower()
    cap = CAPS.get(tier)
    try:
        prior = int(data.get("prior_disputes_12_months"))
        if prior < 0:
            raise ValueError
    except (TypeError, ValueError):
        prior, prior_error = None, "prior_disputes_12_months must be a nonnegative integer"
    else:
        prior_error = None

    disputes = data.get("disputes")
    if not isinstance(disputes, list):
        return {"results": [], "error": "disputes must be a list"}
    for item in disputes:
        failures = []
        if not isinstance(item, dict):
            results.append({"transaction_id": None, "eligible_for_provisional_credit": False,
                            "maximum_amount": str(cap) if cap is not None else None,
                            "failed_conditions": ["dispute item must be an object"]})
            continue
        transaction_id = item.get("transaction_id")
        reason = item.get("reason")
        if common_date_error: failures.append(common_date_error)
        if open_error: failures.append(open_error)
        if today and opened and (today - opened).days < 60:
            failures.append("account has been open fewer than 60 days")
        if cap is None:
            failures.append("card_tier must be entry, mid, premium, elite, or invitation")
        if prior_error:
            failures.append(prior_error)
        elif prior > 2:
            failures.append("more than 2 prior disputes in the last 12 months")
        if reason not in ALLOWED:
            failures.append("reason is not eligible for provisional credit")
        try:
            amount = money(item.get("amount"))
        except ValueError as exc:
            failures.append("amount " + str(exc))
            amount = None
        if amount is not None:
            if amount < Decimal("25"):
                failures.append("amount is below $25.00")
            if cap is not None and amount > cap:
                failures.append("amount exceeds the tier maximum")
        contacted = item.get("contacted_merchant")
        if not isinstance(contacted, bool):
            failures.append("contacted_merchant must be boolean")
        elif reason != "unauthorized_fraudulent_charge" and not contacted:
            failures.append("non-fraud dispute requires merchant contact")
        if reason == "goods_services_not_received":
            try:
                purchase = parse_date(item.get("purchase_date"))
            except ValueError as exc:
                failures.append("purchase_date " + str(exc))
            else:
                if today and (today - purchase).days <= 30:
                    failures.append("goods/services-not-received purchase is not more than 30 days old")
        results.append({
            "transaction_id": transaction_id,
            "eligible_for_provisional_credit": not failures,
            "maximum_amount": str(cap) if cap is not None else None,
            "failed_conditions": failures,
        })
    return {"results": results}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "results": []}, separators=(",", ":")))
        sys.exit(1)
