#!/usr/bin/env python3
"""Policy-driven, read-only audit of posted credit-card reward points.

Reads the JSON schema documented in SKILL.md from stdin and writes one JSON object.
No banking tool is invoked and no records are changed.
"""

import calendar
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_FLOOR


def norm(value):
    return " ".join(str(value or "").casefold().split())


def parse_date(value):
    return date.fromisoformat(str(value))


def parse_decimal(value):
    text = str(value).strip().replace("$", "").replace(",", "")
    return Decimal(text)


def parse_points(value):
    match = re.fullmatch(r"\s*(-?\d+)\s*(?:points?)?\s*", str(value), re.I)
    if not match:
        raise ValueError("rewards_earned must be a whole-number point value")
    return int(match.group(1))


def add_months(day, months):
    index = day.month - 1 + int(months)
    year = day.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def money_from_points(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), "f")


def completed(status):
    return norm(status) == "completed"


def excluded_merchant_match(merchant, excluded_merchants):
    """Return the canonical listed exclusion matched by a merchant, if any.

    Policies frequently name a merchant brand while a posted transaction appends a
    product or service descriptor.  Treat only an exact name or a word-boundary
    extension of the listed name as a match; a merely similar prefix is not enough.
    """
    actual = norm(merchant)
    for listed in excluded_merchants:
        candidate = norm(listed)
        if not candidate:
            continue
        if actual == candidate:
            return candidate
        if actual.startswith(candidate):
            remainder = actual[len(candidate):]
            if remainder and not remainder[0].isalnum():
                return candidate
    return None


def audit(payload):
    errors = []
    accounts = payload.get("accounts")
    transactions = payload.get("transactions")
    policy = payload.get("policy", {})
    programs = policy.get("programs", {}) if isinstance(policy, dict) else {}
    if not isinstance(accounts, list) or not isinstance(transactions, list):
        return {"assessed": [], "mismatches": [], "under_credited": [], "over_credited": [],
                "not_assessed": [], "errors": ["accounts and transactions must both be arrays"]}

    # Card type is the only account linkage exposed by many transaction feeds. Refuse
    # promotion calculation where it identifies more than one account.
    account_by_type = {}
    duplicate_types = set()
    for account in accounts:
        card_type = str(account.get("card_type", "")).strip()
        if not card_type:
            errors.append("An account has no card_type")
            continue
        key = norm(card_type)
        if key in account_by_type:
            duplicate_types.add(key)
        account_by_type[key] = account

    program_by_type = {norm(key): value for key, value in programs.items()}
    assessed = []
    mismatches = []
    under_credited = []
    over_credited = []
    not_assessed = []

    for tx in transactions:
        txid = tx.get("transaction_id")
        label = {"transaction_id": txid}
        if not completed(tx.get("status")):
            not_assessed.append({**label, "reason": "Only COMPLETED posted transactions are eligible for automatic calculation"})
            continue
        card_key = norm(tx.get("credit_card_type"))
        program = program_by_type.get(card_key)
        if not isinstance(program, dict):
            not_assessed.append({**label, "reason": "No supplied policy program matches this card type"})
            continue
        try:
            amount = parse_decimal(tx.get("transaction_amount"))
            tx_date = parse_date(tx.get("transaction_date"))
            actual = parse_points(tx.get("rewards_earned"))
            base_rate = parse_decimal(program["base_rate_percent"])
            bonus_rate = parse_decimal(program["bonus_rate_percent"])
        except (KeyError, ValueError, InvalidOperation) as exc:
            not_assessed.append({**label, "reason": "Malformed required transaction or policy value: " + str(exc)})
            continue
        if amount < 0 or base_rate < 0 or bonus_rate < 0:
            not_assessed.append({**label, "reason": "Negative amount or rate cannot be automatically assessed"})
            continue

        category_set = {norm(x) for x in program.get("bonus_categories", [])}
        exclusions = program.get("excluded_merchants", [])
        if not isinstance(exclusions, list):
            not_assessed.append({**label, "reason": "excluded_merchants must be an array when supplied"})
            continue
        matched_exclusion = excluded_merchant_match(tx.get("merchant_name"), exclusions)
        is_excluded = matched_exclusion is not None
        is_bonus_category = norm(tx.get("category")) in category_set
        rate = bonus_rate if is_bonus_category and not is_excluded else base_rate
        reason = "bonus category" if is_bonus_category and not is_excluded else "base rate"
        if is_excluded:
            reason = "explicit merchant exclusion at base rate"

        promo_applied = False
        promotion = program.get("promotion")
        if promotion is not None:
            if card_key in duplicate_types:
                not_assessed.append({**label, "reason": "Multiple accounts share this card type; account-opening promotion eligibility is ambiguous"})
                continue
            account = account_by_type.get(card_key)
            if not account:
                not_assessed.append({**label, "reason": "No matching account is available for promotion eligibility"})
                continue
            try:
                opened = parse_date(account["date_of_account_open"])
                open_start = parse_date(promotion["open_start"])
                open_end = parse_date(promotion["open_end"])
                window_end = add_months(opened, int(promotion["months_after_open"]))
                multiplier = parse_decimal(promotion["multiplier"])
            except (KeyError, ValueError, InvalidOperation) as exc:
                not_assessed.append({**label, "reason": "Malformed promotion or account-opening value: " + str(exc)})
                continue
            if multiplier < 0:
                not_assessed.append({**label, "reason": "Promotion multiplier cannot be negative"})
                continue
            if open_start <= opened <= open_end and opened <= tx_date < window_end:
                rate *= multiplier
                promo_applied = True
                reason += "; promotion multiplier applied"
            else:
                reason += "; promotion not eligible for this account/date"

        expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
        record = {
            "transaction_id": txid,
            "card_type": tx.get("credit_card_type"),
            "transaction_date": tx.get("transaction_date"),
            "merchant_name": tx.get("merchant_name"),
            "category": tx.get("category"),
            "amount": format(amount, "f"),
            "rate_percent": format(rate, "f"),
            "rate_reason": reason,
            "matched_exclusion": matched_exclusion,
            "promotion_applied": promo_applied,
            "actual_points": actual,
            "expected_points": expected,
            "difference_points": expected - actual,
            "discrepancy_type": (
                "under_credited" if expected > actual else
                "over_credited" if expected < actual else "matches"
            ),
            "actual_cash_value": money_from_points(actual),
            "expected_cash_value": money_from_points(expected),
        }
        assessed.append(record)
        if expected != actual:
            mismatches.append(record)
            if expected > actual:
                under_credited.append(record)
            else:
                over_credited.append(record)

    return {
        "assessed": assessed,
        "mismatches": mismatches,
        "under_credited": under_credited,
        "over_credited": over_credited,
        "not_assessed": not_assessed,
        "errors": errors,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        result = audit(payload)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        result = {"assessed": [], "mismatches": [], "under_credited": [], "over_credited": [],
                  "not_assessed": [], "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
