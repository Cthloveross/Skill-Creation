#!/usr/bin/env python3
"""Read audit JSON from stdin and write a deterministic reward audit JSON to stdout."""
import json
import re
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_DOWN

COMPLETED = {"COMPLETED", "POSTED"}
BS_EXCLUSIONS = {
    "concur", "sap concur", "expensify", "navan",
    "apple", "microsoft", "dell",
    "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
}
ECO_EXCLUSIONS = {"target", "walmart", "amazon", "thredup"}
ECO_PARTNER_NETWORKS = {"tesla supercharger", "chargepoint", "evgo"}
PROMO_START = date(2024, 11, 14)
PROMO_END = date(2025, 11, 14)


def norm(value):
    """Case/punctuation-insensitive label used solely for supplied policy names."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value).lower())).strip()


def parse_date(value):
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must be MM/DD/YYYY or YYYY-MM-DD")


def parse_amount(value):
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    amount = Decimal(str(value))
    if amount < 0:
        raise ValueError("transaction_amount must be nonnegative")
    return amount


def whole_points(amount, points_per_dollar):
    return int((amount * Decimal(str(points_per_dollar))).to_integral_value(rounding=ROUND_DOWN))


def merchant_matches(merchant_key, policy_keys):
    # Exact names are preferred. Prefix permits transaction descriptors such as
    # "Target Eco Collection" while not treating unrelated names as exclusions.
    return merchant_key in policy_keys or any(merchant_key.startswith(x + " ") for x in policy_keys)


def add_months_six(opened):
    month = opened.month + 6
    year = opened.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(opened.day, days[month - 1]))


def silver_promo_applies(opened, transacted):
    return (PROMO_START <= opened <= PROMO_END and opened <= transacted < add_months_six(opened))


def account_opening_for(tx, account_dates):
    if tx.get("account_open_date"):
        return parse_date(tx["account_open_date"])
    choices = account_dates.get(str(tx.get("credit_card_type", "")), [])
    if len(choices) == 1:
        return choices[0]
    if not choices:
        raise ValueError("no matching account opening date")
    raise ValueError("multiple accounts of this card type; provide account_open_date")


def expected_for(tx, account_dates):
    card = str(tx["credit_card_type"])
    category = norm(tx["category"])
    merchant = norm(tx["merchant_name"])
    amount = parse_amount(tx["transaction_amount"])
    transacted = parse_date(tx["transaction_date"])
    notes = []

    if card == "Diamond Elite Card":
        rate, rule = Decimal("5"), "Diamond Elite eligible-purchase rate (5.0% cash back)"
    elif card == "Business Platinum Rewards Card":
        if category in {"travel", "software", "media"}:
            rate, rule = Decimal("4"), "Business Platinum enhanced coded category (4.0% cash back)"
        else:
            rate, rule = Decimal("1.5"), "Business Platinum other-purchase rate (1.5% cash back)"
    elif card == "Business Silver Rewards Card":
        excluded = merchant_matches(merchant, BS_EXCLUSIONS)
        if category in {"travel", "software"} and not excluded:
            rate, rule = Decimal("10"), "Business Silver enhanced coded category (10.0% cash back)"
        else:
            rate, rule = Decimal("1") , "Business Silver standard rate (1.0% cash back)"
            if excluded:
                notes.append("Explicit Business Silver merchant exclusion overrides the category.")
        opened = account_opening_for(tx, account_dates)
        if silver_promo_applies(opened, transacted):
            rate *= 2
            rule += "; eligible new-account double-cash-back promotion applied"
        else:
            notes.append("Business Silver double-promotion not applicable from supplied opening/transaction dates.")
    elif card == "EcoCard":
        excluded = merchant_matches(merchant, ECO_EXCLUSIONS)
        partner = merchant_matches(merchant, ECO_PARTNER_NETWORKS)
        if excluded:
            rate, rule = Decimal("1"), "EcoCard explicit merchant exclusion (standard sustainability rate)"
        elif category == "green" or partner:
            rate, rule = Decimal("5"), "EcoCard qualifying green purchase (5 sustainability points per dollar)"
        else:
            rate, rule = Decimal("1"), "EcoCard standard sustainability rate (1 point per dollar)"
        if partner and category != "green":
            notes.append("Certified EV network recognized despite non-Green category label.")
    else:
        raise ValueError("unsupported credit_card_type")

    return whole_points(amount, rate), str(rate), rule, notes


def main(payload):
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        raise ValueError("accounts and transactions must both be arrays")

    account_dates = {}
    account_errors = []
    for a in accounts:
        try:
            card = str(a["card_type"])
            opened = parse_date(a["date_of_account_open"])
            account_dates.setdefault(card, []).append(opened)
        except (KeyError, ValueError) as exc:
            account_errors.append("invalid account row: " + str(exc))

    audits, skipped, issues = [], [], list(account_errors)
    discrepancies = []
    for index, tx in enumerate(transactions):
        ident = tx.get("transaction_id", "row_" + str(index + 1)) if isinstance(tx, dict) else "row_" + str(index + 1)
        if not isinstance(tx, dict):
            skipped.append({"transaction_id": ident, "reason": "transaction is not an object"})
            continue
        status = str(tx.get("status", "")).upper()
        if status not in COMPLETED:
            skipped.append({"transaction_id": ident, "reason": "not completed/posted", "status": tx.get("status")})
            continue
        try:
            recorded_raw = tx["rewards_earned"]
            recorded_decimal = Decimal(str(recorded_raw))
            if recorded_decimal != recorded_decimal.to_integral_value():
                raise ValueError("rewards_earned must be an integer")
            recorded = int(recorded_decimal)
            expected, rate, rule, notes = expected_for(tx, account_dates)
            difference = recorded - expected
            row = {
                "transaction_id": ident,
                "transaction_date": str(tx["transaction_date"]),
                "card_type": tx["credit_card_type"],
                "merchant_name": tx["merchant_name"],
                "recorded_points": recorded,
                "expected_points": expected,
                "points_per_dollar": rate,
                "rule": rule,
                "difference_points": difference,
                "cashback_redemption_value_difference_usd": (format((Decimal(abs(difference)) / Decimal("100")), ".2f")
                    if tx["credit_card_type"] != "EcoCard" else None),
                "notes": notes,
                "result": "match" if difference == 0 else ("over_earned" if difference > 0 else "under_earned")
            }
            audits.append(row)
            if difference:
                discrepancies.append(row)
        except (KeyError, ValueError, InvalidOperation) as exc:
            skipped.append({"transaction_id": ident, "reason": "cannot audit: " + str(exc)})

    validation = {
        "input_transactions": len(transactions),
        "audited_transactions": len(audits),
        "skipped_transactions": len(skipped),
        "every_input_accounted_for": len(audits) + len(skipped) == len(transactions),
        "discrepancy_count_matches_list": len(discrepancies) == sum(1 for row in audits if row["difference_points"] != 0),
        "warnings": issues,
    }
    return {
        "audits": audits,
        "discrepancies": discrepancies,
        "skipped": skipped,
        "summary": {
            "audited_count": len(audits),
            "match_count": len(audits) - len(discrepancies),
            "discrepancy_count": len(discrepancies),
            "over_earned_count": sum(1 for r in discrepancies if r["difference_points"] > 0),
            "under_earned_count": sum(1 for r in discrepancies if r["difference_points"] < 0),
            "net_points_difference_recorded_minus_expected": sum(r["difference_points"] for r in audits),
        },
        "validation": validation,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), indent=2, sort_keys=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
