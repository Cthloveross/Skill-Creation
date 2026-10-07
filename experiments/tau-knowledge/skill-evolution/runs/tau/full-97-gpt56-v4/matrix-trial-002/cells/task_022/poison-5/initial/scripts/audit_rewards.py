#!/usr/bin/env python3
"""Deterministic, per-transaction credit-card rewards audit.

Read one JSON object from stdin. See SKILL.md for input and output schemas.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any, Dict, Iterable, List, Optional, Tuple

D = Decimal

# Documented Business Silver offer. These are program rules, not customer data.
PROMO_OPEN_START = date(2024, 11, 14)
PROMO_OPEN_END = date(2025, 11, 14)

SILVER_EXCLUSIONS = {
    "Travel": ("Concur", "SAP Concur", "Expensify", "Navan"),
    "Software": (
        "Apple", "Microsoft", "Dell", "Xbox Game Pass", "PlayStation Plus",
        "Nintendo Switch Online", "Coursera", "Udemy", "LinkedIn Learning",
        "Skillshare", "Pluralsight",
    ),
}
ECO_EXCLUSIONS = ("Target", "Walmart", "Amazon", "ThredUp")


def as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", as_text(value)).casefold()


def parse_date(value: Any) -> date:
    text = as_text(value)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("expected YYYY-MM-DD or MM/DD/YYYY date, got %r" % text)


def parse_amount(value: Any) -> Decimal:
    text = as_text(value).replace("$", "").replace(",", "")
    # Plain tool results may append unit labels such as "points".
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError("no numeric amount in %r" % as_text(value))
    try:
        return D(match.group(0))
    except InvalidOperation as exc:
        raise ValueError("invalid numeric amount %r" % as_text(value)) from exc


def parse_integral_points(value: Any) -> int:
    amount = parse_amount(value)
    if amount != amount.to_integral_value():
        raise ValueError("posted points must be a whole number")
    return int(amount)


def money(points: int) -> str:
    """Render the stated one-cent-per-point equivalent without using float."""
    return format((D(points) / D("100")).quantize(D("0.01")), "f")


def floor_points(amount: Decimal, points_per_dollar: Decimal) -> int:
    return int((amount * points_per_dollar).to_integral_value(rounding=ROUND_FLOOR))


def merchant_matches(merchant: Any, listed_name: str) -> bool:
    """Match an explicit merchant and ordinary variants such as 'Target - ...'."""
    actual, listed = norm(merchant), norm(listed_name)
    return actual == listed or actual.startswith(listed + " ") or actual.startswith(listed + " -")


def matches_any_merchant(merchant: Any, names: Iterable[str]) -> Optional[str]:
    for name in names:
        if merchant_matches(merchant, name):
            return name
    return None


def add_months(value: date, months: int) -> date:
    """Calendar-month addition, clamping to month end where necessary."""
    month_number = value.month - 1 + months
    year, month = value.year + month_number // 12, month_number % 12 + 1
    month_ends = (31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                  31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return date(year, month, min(value.day, month_ends[month - 1]))


def account_is_silver_promo_eligible(opened: date, txn_date: date) -> bool:
    # Offer applies during the six-month window beginning on the eligible opening date.
    return PROMO_OPEN_START <= opened <= PROMO_OPEN_END and opened <= txn_date < add_months(opened, 6)


def record_blocks(raw: str) -> List[Dict[str, str]]:
    """Parse the stable human-readable record format returned by normal tools."""
    blocks = re.split(r"(?m)^\s*\d+\.\s+Record ID:\s*", raw)
    records: List[Dict[str, str]] = []
    for block in blocks[1:]:
        result: Dict[str, str] = {}
        first, *rest = block.splitlines()
        result["record_id"] = first.strip()
        for line in rest:
            match = re.match(r"^\s{0,8}([A-Za-z_]+):\s*(.*?)\s*$", line)
            if match:
                result[match.group(1)] = match.group(2)
        if len(result) > 1:
            records.append(result)
    return records


def get_records(payload: Dict[str, Any], array_key: str, raw_key: str) -> List[Dict[str, Any]]:
    direct = payload.get(array_key)
    if direct is not None:
        if not isinstance(direct, list) or not all(isinstance(x, dict) for x in direct):
            raise ValueError("%s must be an array of objects" % array_key)
        return direct
    raw = payload.get(raw_key, "")
    if raw in (None, ""):
        return []
    if not isinstance(raw, str):
        raise ValueError("%s must be text" % raw_key)
    return record_blocks(raw)


def canonical_category(value: Any) -> str:
    return as_text(value).casefold()


def rate_for_transaction(txn: Dict[str, Any], account_open_dates: Dict[str, date]) -> Tuple[Decimal, str, List[str]]:
    """Return baseline points/$, explanation, and applied rule labels."""
    card = as_text(txn.get("credit_card_type"))
    category = canonical_category(txn.get("category"))
    merchant = as_text(txn.get("merchant_name"))
    labels: List[str] = []

    if card == "Diamond Elite Card":
        return D("5"), "Diamond Elite eligible-purchase rate", ["diamond_5x"]

    if card == "Business Platinum Rewards Card":
        if category in {"travel", "software", "media"}:
            return D("4"), "Business Platinum enhanced %s rate" % category, ["bplat_4x"]
        return D("1.5"), "Business Platinum standard rate", ["bplat_standard_1_5x"]

    if card == "Business Silver Rewards Card":
        display_category = "Travel" if category == "travel" else "Software" if category == "software" else None
        excluded = matches_any_merchant(merchant, SILVER_EXCLUSIONS.get(display_category, ())) if display_category else None
        rate = D("10") if display_category and not excluded else D("1")
        if excluded:
            labels.append("business_silver_%s_exclusion:%s" % (category, excluded))
            explanation = "Business Silver documented %s exclusion (%s); standard rate" % (category, excluded)
        elif display_category:
            labels.append("business_silver_bonus")
            explanation = "Business Silver qualifying %s rate" % category
        else:
            labels.append("business_silver_standard")
            explanation = "Business Silver standard rate"

        opening = account_open_dates.get(card)
        if opening is None:
            raise ValueError("missing account opening date for Business Silver Rewards Card")
        txn_date = parse_date(txn.get("transaction_date"))
        if account_is_silver_promo_eligible(opening, txn_date):
            rate *= D("2")
            labels.append("business_silver_double_cash_back_promo")
            explanation += "; eligible double-cash-back promotion applied"
        return rate, explanation, labels

    if card == "EcoCard":
        excluded = matches_any_merchant(merchant, ECO_EXCLUSIONS)
        if category == "green" and not excluded:
            return D("5"), "EcoCard qualifying green rate", ["eco_green_5x"]
        if excluded:
            return D("1"), "EcoCard documented green-rate exclusion (%s)" % excluded, ["eco_exclusion:%s" % excluded]
        return D("1"), "EcoCard standard non-green rate", ["eco_standard_1x"]

    raise ValueError("unsupported card type %r" % card)


def audit(payload: Dict[str, Any]) -> Dict[str, Any]:
    accounts = get_records(payload, "accounts", "raw_accounts")
    transactions = get_records(payload, "transactions", "raw_transactions")
    eligible_statuses_raw = payload.get("eligible_statuses", ["COMPLETED"])
    if not isinstance(eligible_statuses_raw, list):
        raise ValueError("eligible_statuses must be an array")
    eligible_statuses = {norm(x) for x in eligible_statuses_raw}
    conditional_authorized = bool(payload.get("conditional_ecocard_bonus_authorized", False))

    input_errors: List[Dict[str, str]] = []
    openings: Dict[str, date] = {}
    for account in accounts:
        card = as_text(account.get("card_type") or account.get("credit_card_type"))
        opened = account.get("date_of_account_open")
        if not card:
            input_errors.append({"record_id": as_text(account.get("account_id") or account.get("record_id")), "error": "account card_type is missing"})
            continue
        if opened:
            try:
                openings[card] = parse_date(opened)
            except ValueError as exc:
                input_errors.append({"record_id": as_text(account.get("account_id") or account.get("record_id")), "error": str(exc)})

    discrepancies: List[Dict[str, Any]] = []
    matched: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    conditional: List[Dict[str, Any]] = []
    expected_total = actual_total = 0
    by_card: Dict[str, Counter] = defaultdict(Counter)

    for txn in transactions:
        tid = as_text(txn.get("transaction_id") or txn.get("record_id"))
        status = as_text(txn.get("status"))
        if norm(status) not in eligible_statuses:
            unresolved.append({"transaction_id": tid, "reason": "status %r is not in eligible_statuses" % status})
            continue
        try:
            amount = parse_amount(txn.get("transaction_amount"))
            if amount < 0:
                raise ValueError("negative transaction amount requires return/credit netting rules not supplied")
            expected_rate, basis, labels = rate_for_transaction(txn, openings)
            expected = floor_points(amount, expected_rate)
            actual = parse_integral_points(txn.get("rewards_earned"))
            txn_date = parse_date(txn.get("transaction_date"))
            card = as_text(txn.get("credit_card_type"))
            merchant = as_text(txn.get("merchant_name"))
        except (ValueError, InvalidOperation) as exc:
            unresolved.append({"transaction_id": tid, "reason": str(exc)})
            continue

        item: Dict[str, Any] = {
            "transaction_id": tid,
            "transaction_date": txn_date.isoformat(),
            "card_type": card,
            "merchant_name": merchant,
            "category": as_text(txn.get("category")),
            "amount": format(amount, "f"),
            "expected_rate_points_per_dollar": format(expected_rate, "f"),
            "expected_points": expected,
            "posted_points": actual,
            "delta_points": actual - expected,
            "delta_value_at_0_01_per_point": money(actual - expected),
            "rate_basis": basis,
            "applied_rules": labels,
        }
        expected_total += expected
        actual_total += actual
        by_card[card]["reviewed"] += 1
        by_card[card]["expected_points"] += expected
        by_card[card]["posted_points"] += actual
        if actual == expected:
            matched.append(item)
            by_card[card]["matched"] += 1
        else:
            item["finding"] = "overpaid" if actual > expected else "underpaid"
            discrepancies.append(item)
            by_card[card]["discrepancies"] += 1
            by_card[card]["delta_points"] += actual - expected

        # This is deliberately separate from the baseline, not a confirmed adjustment.
        if card == "EcoCard" and canonical_category(txn.get("category")) == "green" and not matches_any_merchant(merchant, ECO_EXCLUSIONS):
            extra = floor_points(amount, D("2"))
            conditional.append({
                "transaction_id": tid,
                "transaction_date": txn_date.isoformat(),
                "merchant_name": merchant,
                "amount": format(amount, "f"),
                "conditional_extra_points": extra,
                "conditional_extra_value_at_0_01_per_point": money(extra),
                "condition": "only if EcoCard was linked to a Green Account (savings) and both remained in good standing for this transaction",
                "authorized_to_present_conditionally": conditional_authorized,
            })

    discrepancies.sort(key=lambda x: (x["transaction_date"], x["transaction_id"]))
    matched.sort(key=lambda x: (x["transaction_date"], x["transaction_id"]))
    conditional.sort(key=lambda x: (x["transaction_date"], x["transaction_id"]))
    cards_summary = []
    for card in sorted(by_card):
        stat = by_card[card]
        cards_summary.append({
            "card_type": card,
            "reviewed": stat["reviewed"],
            "matched": stat["matched"],
            "discrepancies": stat["discrepancies"],
            "expected_points": stat["expected_points"],
            "posted_points": stat["posted_points"],
            "delta_points": stat["posted_points"] - stat["expected_points"],
        })

    conditional_total = sum(x["conditional_extra_points"] for x in conditional)
    return {
        "summary": {
            "transactions_supplied": len(transactions),
            "transactions_reviewed": len(matched) + len(discrepancies),
            "transactions_matched": len(matched),
            "transactions_with_discrepancies": len(discrepancies),
            "transactions_unresolved_or_skipped": len(unresolved),
            "baseline_expected_points": expected_total,
            "posted_points": actual_total,
            "baseline_delta_points": actual_total - expected_total,
            "baseline_delta_value_at_0_01_per_point": money(actual_total - expected_total),
            "delta_direction": "overpaid" if actual_total > expected_total else "underpaid" if actual_total < expected_total else "no net difference",
            "per_card": cards_summary,
        },
        "discrepancies": discrepancies,
        "matched": matched,
        "conditional_ecocard_bonus": {
            "included_in_baseline": False,
            "authorization_to_present_conditionally": conditional_authorized,
            "eligible_green_transactions_using_available_classification": conditional,
            "conditional_total_extra_points": conditional_total,
            "conditional_total_extra_value_at_0_01_per_point": money(conditional_total),
            "note": "This is not a confirmed discrepancy. Historical Green Account linkage and good-standing data is required to determine entitlement.",
        },
        "unresolved": unresolved,
        "input_errors": input_errors,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON input must be an object")
        print(json.dumps(audit(payload), ensure_ascii=False, indent=2, sort_keys=False))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"error": "invalid_audit_input", "message": str(exc)}))


if __name__ == "__main__":
    main()
