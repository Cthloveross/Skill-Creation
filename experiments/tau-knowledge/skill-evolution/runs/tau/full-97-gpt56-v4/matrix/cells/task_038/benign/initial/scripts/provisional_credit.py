#!/usr/bin/env python3
"""Evaluate documented provisional-credit rules.

Reads one JSON object from stdin and writes one JSON object to stdout.
Input fields: account_open_date, filing_date, purchase_date (MM/DD/YYYY or
YYYY-MM-DD), amount (number), card_tier (Entry/Mid/Premium/Elite/Invitation
or a supported card-name string), prior_disputes_last_12_months (integer),
contacted_merchant (boolean), dispute_reason (string).
Output: eligible boolean and failed_rules list. Invalid input is reported in
failed_rules and always yields eligible false.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

LIMITS = {
    "entry": Decimal("2500"), "mid": Decimal("5000"),
    "premium": Decimal("10000"), "elite": Decimal("15000"),
    "invitation": Decimal("25000"),
}
CARD_TIERS = {
    "bronze rewards card": "entry", "ecocard": "entry",
    "business bronze rewards card": "entry", "crypto-cash back card": "entry",
    "silver rewards card": "mid", "business silver rewards card": "mid",
    "green rewards card": "mid", "silver zoom card": "mid",
    "gold rewards card": "premium", "business gold rewards card": "premium",
    "platinum rewards card": "elite", "business platinum rewards card": "elite",
    "diamond elite card": "invitation",
}
QUALIFYING = {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}

def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use MM/DD/YYYY or YYYY-MM-DD")

def tier_of(value):
    key = str(value).strip().lower()
    if key in LIMITS:
        return key
    return CARD_TIERS.get(key)

def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"eligible": False, "failed_rules": ["invalid_json: " + str(exc)]}))
        return
    failures = []
    try:
        opened = parse_date(data.get("account_open_date"))
        filed = parse_date(data.get("filing_date"))
        purchased = parse_date(data.get("purchase_date"))
        if filed < opened:
            failures.append("invalid_account_or_filing_date")
        elif (filed - opened).days < 60:
            failures.append("account_under_60_days")
    except ValueError as exc:
        failures.append("invalid_date: " + str(exc))
        filed = purchased = None
    try:
        amount = Decimal(str(data.get("amount")))
        if not amount.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        amount = None
        failures.append("invalid_amount")
    tier = tier_of(data.get("card_tier"))
    if tier is None:
        failures.append("unknown_card_tier")
    reason = data.get("dispute_reason")
    if reason not in QUALIFYING:
        failures.append("nonqualifying_dispute_reason")
    if reason == "goods_services_not_received" and filed and purchased:
        if (filed - purchased).days <= 30:
            failures.append("goods_not_received_within_30_days")
    if amount is not None:
        if amount < Decimal("25"):
            failures.append("amount_under_25")
        if tier and amount > LIMITS[tier]:
            failures.append("amount_exceeds_tier_limit")
    previous = data.get("prior_disputes_last_12_months")
    if isinstance(previous, bool) or not isinstance(previous, int) or previous < 0:
        failures.append("invalid_prior_dispute_count")
    elif previous > 2:
        failures.append("more_than_two_prior_disputes")
    contacted = data.get("contacted_merchant")
    if not isinstance(contacted, bool):
        failures.append("missing_or_invalid_merchant_contact_status")
    elif reason != "unauthorized_fraudulent_charge" and not contacted:
        failures.append("merchant_not_contacted_for_nonfraud_dispute")
    print(json.dumps({"eligible": not failures, "failed_rules": failures}, separators=(",", ":")))

if __name__ == "__main__":
    main()
