#!/usr/bin/env python3
"""Select the highest eligible APY plan from runtime-supplied product facts.

Reads JSON from stdin and writes JSON to stdout. Rates are percentage points.
This utility makes no network calls and never initiates a banking action.
"""

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple


def decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a decimal number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def nonnegative(value: Any, field: str) -> Decimal:
    parsed = decimal(value, field)
    if parsed < 0:
        raise ValueError(f"{field} must not be negative")
    return parsed


def text_number(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return "0" if rendered in ("-0", "") else rendered


def best_option(
    options: Any, rate_key: str, label: str
) -> Tuple[Optional[str], Decimal]:
    if options is None:
        return None, Decimal("0")
    if not isinstance(options, list):
        raise ValueError(f"{label}_options must be a list")

    choices: List[Tuple[Decimal, str]] = []
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            raise ValueError(f"{label}_options[{index}] must be an object")
        if option.get("eligible") is not True:
            continue
        name = option.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{label}_options[{index}].name is required for eligible options")
        rate = nonnegative(option.get(rate_key, 0), f"{label}_options[{index}].{rate_key}")
        choices.append((rate, name.strip()))

    if not choices:
        return None, Decimal("0")
    # Stable name ordering gives deterministic output for equal rate options.
    rate, name = sorted(choices, key=lambda item: (-item[0], item[1]))[0]
    return name, rate


def evaluate_plan(plan: Dict[str, Any], balance: Decimal, index: int) -> Optional[Dict[str, Any]]:
    if plan.get("eligible") is not True:
        return None
    plan_id = plan.get("id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise ValueError(f"plans[{index}].id is required for eligible plans")

    opening = nonnegative(plan.get("minimum_opening_deposit", 0), f"plans[{index}].minimum_opening_deposit")
    ongoing = nonnegative(plan.get("minimum_ongoing_balance", 0), f"plans[{index}].minimum_ongoing_balance")
    if balance < opening or balance < ongoing:
        return None

    base = nonnegative(plan.get("base_apy"), f"plans[{index}].base_apy")
    other = nonnegative(plan.get("other_additive_bonus_apy", 0), f"plans[{index}].other_additive_bonus_apy")
    checking_name, checking_rate = best_option(plan.get("checking_options", []), "boost_apy", "checking")
    card_name, card_rate = best_option(plan.get("card_options", []), "bonus_apy", "card")
    assumptions = plan.get("assumptions", [])
    if not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions):
        raise ValueError(f"plans[{index}].assumptions must be a list of strings")

    total = base + checking_rate + card_rate + other
    return {
        "id": plan_id.strip(),
        "base_apy": text_number(base),
        "checking_product": checking_name,
        "checking_boost_apy": text_number(checking_rate),
        "credit_card_product": card_name,
        "card_bonus_apy": text_number(card_rate),
        "other_additive_bonus_apy": text_number(other),
        "total_apy": text_number(total),
        "minimum_opening_deposit": text_number(opening),
        "minimum_ongoing_balance": text_number(ongoing),
        "assumptions": assumptions,
    }


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    balance = nonnegative(payload.get("balance"), "balance")
    plans = payload.get("plans")
    if not isinstance(plans, list):
        raise ValueError("plans must be a list")

    eligible: List[Dict[str, Any]] = []
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            raise ValueError(f"plans[{index}] must be an object")
        result = evaluate_plan(plan, balance, index)
        if result is not None:
            eligible.append(result)

    eligible.sort(key=lambda item: (-Decimal(item["total_apy"]), item["id"]))
    return {
        "ok": True,
        "balance": text_number(balance),
        "eligible_plan_count": len(eligible),
        "best_plan": eligible[0] if eligible else None,
        "eligible_plans_ranked": eligible,
        "selection_policy": {
            "checking": "highest eligible boost only",
            "credit_card": "highest eligible bonus only",
            "cross_category": "checking and credit-card components may be additive when supplied as eligible"
        },
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("expected JSON input on stdin")
        print(json.dumps(main(json.loads(raw)), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, separators=(",", ":"), sort_keys=True))
        sys.exit(2)
