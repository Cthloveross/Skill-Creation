#!/usr/bin/env python3
"""Estimate a savings statement's daily-compounded interest from verified daily data.

Reads one JSON object from stdin and emits one JSON object on stdout. See SKILL.md for
input assumptions. This program makes no banking-system calls and does not establish
eligibility for any bonus.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parent.parent / "references" / "product_rules.json"
MONEY_QUANTUM = Decimal("0.01")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def error(message: str, details: list[str] | None = None) -> None:
    result: dict[str, Any] = {"status": "error", "message": message}
    if details:
        result["details"] = details
    emit(result)


def decimal_value(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a decimal number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a decimal number") from None
    if not parsed.is_finite():
        raise ValueError(f"{label} must be finite")
    return parsed


def optional_percent(row: dict[str, Any], field: str, global_data: dict[str, Any]) -> Decimal:
    value = row[field] if field in row else global_data.get(field, 0)
    parsed = decimal_value(value, field)
    if parsed < 0:
        raise ValueError(f"{field} cannot be negative")
    return parsed


def base_apy(tiers: list[dict[str, Any]], balance: Decimal) -> Decimal:
    selected = Decimal("0")
    for tier in tiers:
        threshold = decimal_value(tier["minimum_balance"], "tier minimum_balance")
        rate = decimal_value(tier["apy_percent"], "tier apy_percent")
        if balance >= threshold and threshold >= 0:
            selected = rate
    return selected


def cents(value: Decimal) -> str:
    return format(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        error("Input must be one valid JSON object", [str(exc)])
        return

    if not isinstance(payload, dict):
        error("Input must be a JSON object")
        return
    if payload.get("balances_exclude_uncredited_interest") is not True:
        error(
            "balances_exclude_uncredited_interest must be true",
            ["The calculator separately compounds accrued but uncredited interest and would otherwise double-count it."],
        )
        return

    account_type = payload.get("account_type")
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    accounts = rules["accounts"]
    if account_type not in accounts:
        error("Unsupported account_type", ["Use one of: " + ", ".join(accounts.keys())])
        return
    account = accounts[account_type]

    rows = payload.get("daily_balances")
    if not isinstance(rows, list) or not rows:
        error("daily_balances must be a nonempty array")
        return

    parsed_rows: list[tuple[date, dict[str, Any], Decimal]] = []
    dates_seen: set[date] = set()
    try:
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"daily_balances[{index}] must be an object")
            raw_date = row.get("date")
            if not isinstance(raw_date, str):
                raise ValueError(f"daily_balances[{index}].date must be YYYY-MM-DD")
            try:
                parsed_date = date.fromisoformat(raw_date)
            except ValueError:
                raise ValueError(f"daily_balances[{index}].date must be YYYY-MM-DD") from None
            if parsed_date in dates_seen:
                raise ValueError(f"Duplicate date: {raw_date}")
            dates_seen.add(parsed_date)
            balance = decimal_value(row.get("balance"), f"daily_balances[{index}].balance")
            if balance < 0:
                raise ValueError(f"daily_balances[{index}].balance cannot be negative")
            parsed_rows.append((parsed_date, row, balance))
    except ValueError as exc:
        error("Invalid daily balance data", [str(exc)])
        return

    parsed_rows.sort(key=lambda item: item[0])
    for previous, current in zip(parsed_rows, parsed_rows[1:]):
        if current[0] != previous[0] + timedelta(days=1):
            error(
                "daily_balances must contain consecutive calendar dates",
                [f"Gap between {previous[0].isoformat()} and {current[0].isoformat()}"],
            )
            return

    held_cards = payload.get("held_card_types", [])
    if not isinstance(held_cards, list) or not all(isinstance(item, str) for item in held_cards):
        error("held_card_types must be an array of card-name strings")
        return
    schedule: dict[str, Any] = account.get("card_bonus_percent", {})
    known_cards = [card for card in held_cards if card in schedule]
    unknown_cards = [card for card in held_cards if card not in schedule]
    selected_card = max((decimal_value(schedule[card], "card bonus") for card in known_cards), default=Decimal("0"))

    compound_accrual = Decimal("0")
    daily_output: list[dict[str, Any]] = []
    try:
        for day, row, ledger_balance in parsed_rows:
            has_daily_card = "card_bonus_percent" in row
            if has_daily_card and held_cards:
                raise ValueError(
                    f"{day.isoformat()} supplies card_bonus_percent while held_card_types is also supplied; use one card source"
                )
            card_bonus = (
                decimal_value(row["card_bonus_percent"], "card_bonus_percent")
                if has_daily_card
                else selected_card
            )
            if card_bonus < 0:
                raise ValueError("card_bonus_percent cannot be negative")
            checking_bonus = optional_percent(row, "checking_bonus_percent", payload)
            relationship_bonus = optional_percent(row, "relationship_bonus_percent", payload)
            direct_deposit_bonus = optional_percent(row, "direct_deposit_bonus_percent", payload)
            base = base_apy(account["tiers"], ledger_balance)
            total_apy = base + card_bonus + checking_bonus + relationship_bonus + direct_deposit_bonus
            # APY is converted to a daily effective rate under the documented estimator convention.
            daily_rate = Decimal(str(math.pow(float(Decimal("1") + total_apy / Decimal("100")), 1.0 / 365.0) - 1.0))
            interest = (ledger_balance + compound_accrual) * daily_rate
            compound_accrual += interest
            daily_output.append(
                {
                    "date": day.isoformat(),
                    "ledger_balance": cents(ledger_balance),
                    "base_apy_percent": str(base),
                    "card_bonus_percent": str(card_bonus),
                    "checking_bonus_percent": str(checking_bonus),
                    "relationship_bonus_percent": str(relationship_bonus),
                    "direct_deposit_bonus_percent": str(direct_deposit_bonus),
                    "total_apy_percent": str(total_apy),
                    "estimated_interest": cents(interest),
                }
            )
    except ValueError as exc:
        error("Invalid bonus data", [str(exc)])
        return

    output: dict[str, Any] = {
        "status": "ok",
        "account_type": account_type,
        "cycle_start": parsed_rows[0][0].isoformat(),
        "cycle_end": parsed_rows[-1][0].isoformat(),
        "day_count": len(parsed_rows),
        "daily_rate_convention": "(1 + APY / 100)^(1/365) - 1",
        "selected_documented_card_bonus_percent": str(selected_card) if held_cards else None,
        "undocumented_held_card_types": unknown_cards,
        "estimated_interest": cents(compound_accrual),
        "daily_details": daily_output,
        "warnings": [],
    }
    if unknown_cards:
        output["warnings"].append(
            "Some supplied card types have no account-specific schedule in the packaged rules and were not assigned a bonus."
        )
    if not held_cards and not any("card_bonus_percent" in row for _, row, _ in parsed_rows):
        output["warnings"].append("No card-bonus evidence was supplied; card bonus was treated as 0%.")

    if "posted_interest_credit" in payload:
        try:
            posted = decimal_value(payload["posted_interest_credit"], "posted_interest_credit")
            if posted < 0:
                raise ValueError("posted_interest_credit cannot be negative")
        except ValueError as exc:
            error("Invalid posted interest credit", [str(exc)])
            return
        output["posted_interest_credit"] = cents(posted)
        output["estimated_minus_posted"] = cents(compound_accrual - posted)

    emit(output)


if __name__ == "__main__":
    main()
