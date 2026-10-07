#!/usr/bin/env python3
"""Calculate expected daily-compounded interest for a Silver savings cycle.

Reads one JSON object from stdin and writes one JSON object to stdout.
No network, filesystem input, or banking actions are performed.
"""

import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40

CHECKING_BOOSTS = {
    "bluest account": Decimal("0.45"),
    "green account": Decimal("0.25"),
    "gold years account": Decimal("0.60"),
}
CARD_BONUSES = {
    "bronze rewards card": Decimal("0.0"),
    "silver rewards card": Decimal("0.1"),
    "gold rewards card": Decimal("0.5"),
    "ecocard": Decimal("2.2"),
    "green rewards card": Decimal("0.0"),
    "crypto-cash back card": Decimal("0.5"),
    "platinum rewards card": Decimal("0.2"),
    "diamond elite card": Decimal("0.25"),
}
CENT = Decimal("0.01")
ZERO = Decimal("0")


def fail(message):
    print(json.dumps({"ok": False, "error": message}), flush=True)
    raise SystemExit(1)


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{field} must be a finite decimal number")
    if not result.is_finite():
        fail(f"{field} must be a finite decimal number")
    return result


def parse_days(raw_days):
    if not isinstance(raw_days, list) or not raw_days:
        fail("daily_balances must be a nonempty list")
    result = []
    prior = None
    for index, item in enumerate(raw_days):
        if not isinstance(item, dict):
            fail(f"daily_balances[{index}] must be an object")
        try:
            day = date.fromisoformat(item["date"])
        except (KeyError, TypeError, ValueError):
            fail(f"daily_balances[{index}].date must be YYYY-MM-DD")
        balance = decimal_value(item.get("balance"), f"daily_balances[{index}].balance")
        if balance < ZERO:
            fail(f"daily_balances[{index}].balance must not be negative")
        if prior is not None and day != prior + timedelta(days=1):
            fail("daily_balances must contain consecutive calendar dates in ascending order")
        result.append((day, balance))
        prior = day
    return result


def named_bonus(raw, allowed, field):
    if raw is None:
        return ZERO, []
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        fail(f"{field} must be a list of product-name strings")
    found = [(name, allowed[name.strip().lower()]) for name in raw if name.strip().lower() in allowed]
    if not found:
        return ZERO, []
    maximum = max(amount for _, amount in found)
    selected = [name for name, amount in found if amount == maximum]
    return maximum, selected


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"stdin must be one valid JSON object: {exc.msg}")
    if not isinstance(payload, dict):
        fail("stdin JSON must be an object")

    days = parse_days(payload.get("daily_balances"))
    checking_bonus, selected_checking = named_bonus(
        payload.get("checking_accounts", []), CHECKING_BOOSTS, "checking_accounts"
    )
    card_bonus, selected_cards = named_bonus(
        payload.get("credit_cards", []), CARD_BONUSES, "credit_cards"
    )
    relationship_eligible = payload.get("platinum_relationship_eligible", False)
    if not isinstance(relationship_eligible, bool):
        fail("platinum_relationship_eligible must be boolean")
    relationship_bonus = Decimal("0.025") if relationship_eligible else ZERO

    actual_interest = None
    if "actual_interest" in payload and payload["actual_interest"] is not None:
        actual_interest = decimal_value(payload["actual_interest"], "actual_interest")
        if actual_interest < ZERO:
            fail("actual_interest must not be negative")

    actual_apy = None
    if "actual_apy" in payload and payload["actual_apy"] is not None:
        actual_apy = decimal_value(payload["actual_apy"], "actual_apy")
        if actual_apy < ZERO:
            fail("actual_apy must not be negative")

    accrued = ZERO
    rows = []
    apys = set()
    for day, balance in days:
        base_apy = Decimal("4.0") if balance >= Decimal("10000") else Decimal("2.5")
        expected_apy = base_apy + checking_bonus + card_bonus + relationship_bonus
        daily_rate = (Decimal("1") + expected_apy / Decimal("100")) ** (Decimal("1") / Decimal("365")) - Decimal("1")
        accrual = (balance + accrued) * daily_rate
        accrued += accrual
        apys.add(expected_apy)
        rows.append({
            "date": day.isoformat(),
            "balance": str(balance),
            "base_apy": str(base_apy),
            "expected_apy": str(expected_apy),
            "daily_accrual": str(accrual),
        })

    expected_interest = money(accrued)
    difference = None
    credit_amount = ZERO
    credit_recommended = False
    if actual_interest is not None:
        difference = money(expected_interest - actual_interest)
        if difference > ZERO:
            credit_amount = difference
            credit_recommended = True

    output = {
        "ok": True,
        "calculation_method": "daily APY root rate with daily compounding; final cycle interest rounded to cents",
        "cycle_start": days[0][0].isoformat(),
        "cycle_end": days[-1][0].isoformat(),
        "days": len(days),
        "selected_checking_bonus_apy": str(checking_bonus),
        "selected_checking_accounts": selected_checking,
        "selected_card_bonus_apy": str(card_bonus),
        "selected_credit_cards": selected_cards,
        "relationship_bonus_apy": str(relationship_bonus),
        "expected_apy_values": [str(x) for x in sorted(apys)],
        "expected_interest": str(expected_interest),
        "actual_interest": None if actual_interest is None else str(money(actual_interest)),
        "amount_difference": None if difference is None else str(difference),
        "credit_recommended": credit_recommended,
        "credit_amount": str(credit_amount),
        "actual_apy": None if actual_apy is None else str(actual_apy),
        "daily_results": rows,
        "validation_note": "A positive recommendation is a calculation result only. The executor must still confirm account ownership, active product eligibility, posted interest transaction, and source balance data before applying a banking credit.",
    }
    print(json.dumps(output, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
