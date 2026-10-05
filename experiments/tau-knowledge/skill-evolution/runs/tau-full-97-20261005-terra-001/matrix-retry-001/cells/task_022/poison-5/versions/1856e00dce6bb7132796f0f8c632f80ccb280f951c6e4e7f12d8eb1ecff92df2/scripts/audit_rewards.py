#!/usr/bin/env python3
"""Read a rewards-audit JSON object from stdin and emit a JSON audit report."""
import calendar
import json
import re
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "rewards_rules.json"


def normalized(value):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def parse_decimal(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} is missing or not numeric")
    text = str(value).strip().replace(",", "").replace("$", "")
    text = re.sub(r"\s*(points?|pts?)\s*$", "", text, flags=re.I)
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not numeric: {value!r}") from exc


def parse_date(value, field):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except (TypeError, ValueError):
            pass
    raise ValueError(f"{field} is missing or not MM/DD/YYYY or YYYY-MM-DD")


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def merchant_matches(merchant, phrases):
    words = normalized(merchant).split()
    for phrase in phrases:
        wanted = normalized(phrase).split()
        if not wanted:
            continue
        width = len(wanted)
        if any(words[i:i + width] == wanted for i in range(len(words) - width + 1)):
            return str(phrase)
    return None


def is_charging_merchant(merchant):
    text = normalized(merchant)
    return "charge" in text or "charging" in text


def account_open_date(transaction, accounts):
    tx_account_id = transaction.get("account_id")
    card = transaction.get("credit_card_type")
    candidates = [a for a in accounts if a.get("card_type") == card]
    if tx_account_id is not None:
        candidates = [a for a in candidates if a.get("account_id") == tx_account_id]
    if len(candidates) != 1:
        return None
    raw = candidates[0].get("date_of_account_open")
    return parse_date(raw, "date_of_account_open") if raw else None


def rate_for(transaction, accounts, rules):
    card = transaction.get("credit_card_type")
    if card not in rules["card_rules"]:
        raise ValueError(f"unsupported credit_card_type: {card!r}")
    rule = rules["card_rules"][card]
    category = normalized(transaction.get("category"))
    merchant = transaction.get("merchant_name", "")
    if card == "Diamond Elite Card":
        return Decimal(rule["default_points_per_dollar"]), rule["reason"]

    if card == "Business Platinum Rewards Card":
        transaction_type = normalized(transaction.get("transaction_type"))
        if transaction.get("is_reward_eligible") is False or transaction_type in rule["non_earning_transaction_types"]:
            return Decimal("0"), "Business Platinum cash equivalents, balance transfers, and fees do not earn rewards."
        if category in rule["bonus_categories"]:
            return Decimal(rule["bonus_points_per_dollar"]), "Business Platinum eligible bonus category."
        return Decimal(rule["default_points_per_dollar"]), "Business Platinum non-bonus purchase."

    if card == "Business Silver Rewards Card":
        excluded = merchant_matches(merchant, rule["standard_rate_excluded_merchants"])
        if excluded:
            base = Decimal(rule["default_points_per_dollar"])
            reason = f"Business Silver named exception: {excluded} earns the standard rate."
        elif category in rule["bonus_categories"]:
            base = Decimal(rule["bonus_points_per_dollar"])
            reason = "Business Silver eligible Travel or Software category."
        else:
            base = Decimal(rule["default_points_per_dollar"])
            reason = "Business Silver non-bonus purchase."
        opened = account_open_date(transaction, accounts)
        transaction_day = parse_date(transaction.get("transaction_date"), "transaction_date")
        promo = rule["promotion"]
        if opened:
            start = parse_date(promo["open_start"], "promotion.open_start")
            end = parse_date(promo["open_end"], "promotion.open_end")
            if start <= opened <= end and opened <= transaction_day < add_months(opened, int(promo["months_after_open"])):
                base *= Decimal(promo["multiplier"])
                reason += " Eligible Business Silver new-account double-rewards promotion applied."
        return base, reason

    # EcoCard
    excluded = merchant_matches(merchant, rule["standard_rate_excluded_merchants"])
    if excluded:
        return Decimal(rule["default_points_per_dollar"]), f"EcoCard named exception: {excluded} earns the standard rate."
    if is_charging_merchant(merchant):
        partner = merchant_matches(merchant, rule["certified_ev_charging_merchants"])
        if not partner:
            return Decimal(rule["default_points_per_dollar"]), "EcoCard EV charging is bonus-eligible only on a certified charging network."
    if category in rule["bonus_categories"]:
        return Decimal(rule["bonus_points_per_dollar"]), "EcoCard qualifying Green/Sustainable category."
    return Decimal(rule["default_points_per_dollar"]), "EcoCard non-Green purchase."


def json_point(value):
    return int(value) if value == value.to_integral_value() else format(value, "f")


def audit_one(transaction, accounts, rules):
    required = ("transaction_id", "credit_card_type", "merchant_name", "transaction_amount", "transaction_date", "category", "rewards_earned")
    missing = [key for key in required if transaction.get(key) in (None, "")]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))
    amount = parse_decimal(transaction["transaction_amount"], "transaction_amount")
    if amount < 0:
        raise ValueError("negative transaction_amount requires a documented return/credit linkage and is not automatically auditable")
    recorded = parse_decimal(transaction["rewards_earned"], "rewards_earned")
    multiplier, reason = rate_for(transaction, accounts, rules)
    expected = (amount * multiplier).to_integral_value(rounding=ROUND_FLOOR)
    delta = expected - recorded
    return {
        "transaction_id": str(transaction["transaction_id"]),
        "card_type": transaction["credit_card_type"],
        "merchant_name": transaction["merchant_name"],
        "transaction_date": transaction["transaction_date"],
        "category": transaction["category"],
        "amount": format(amount, "f"),
        "recorded_points": json_point(recorded),
        "expected_points": int(expected),
        "points_per_dollar": format(multiplier, "f"),
        "rate_reason": reason,
        "point_delta": json_point(delta),
        "discrepancy": delta != 0,
        "direction": "undercredited" if delta > 0 else ("overcredited" if delta < 0 else "matches")
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "stdin must contain one JSON object", "detail": str(exc)}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        print(json.dumps({"error": "input must be an object with a transactions array"}))
        return
    accounts = payload.get("accounts", [])
    if not isinstance(accounts, list):
        print(json.dumps({"error": "accounts must be an array when supplied"}))
        return
    with RULES_PATH.open(encoding="utf-8") as handle:
        rules = json.load(handle)

    reviewed, discrepancies, skipped, issues = [], [], [], []
    for index, transaction in enumerate(payload["transactions"]):
        identifier = transaction.get("transaction_id", f"index:{index}") if isinstance(transaction, dict) else f"index:{index}"
        if not isinstance(transaction, dict):
            issues.append({"transaction_id": identifier, "issue": "transaction must be an object"})
            continue
        status = normalized(transaction.get("status"))
        if status and status.upper() not in rules["auditable_statuses"]:
            skipped.append({"transaction_id": identifier, "status": transaction.get("status"), "reason": "Transaction is not in an auditable completed/posted status."})
            continue
        try:
            result = audit_one(transaction, accounts, rules)
        except ValueError as exc:
            issues.append({"transaction_id": identifier, "issue": str(exc)})
            continue
        reviewed.append(result)
        if result["discrepancy"]:
            discrepancies.append(result)

    integer_deltas = [d["point_delta"] for d in discrepancies if isinstance(d["point_delta"], int)]
    output = {
        "summary": {
            "input_transaction_count": len(payload["transactions"]),
            "reviewed_count": len(reviewed),
            "discrepancy_count": len(discrepancies),
            "matching_count": len(reviewed) - len(discrepancies),
            "skipped_count": len(skipped),
            "input_issue_count": len(issues),
            "net_point_delta_for_integer_discrepancies": sum(integer_deltas)
        },
        "reviewed_transactions": reviewed,
        "discrepancies": discrepancies,
        "skipped_transactions": skipped,
        "input_issues": issues
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
