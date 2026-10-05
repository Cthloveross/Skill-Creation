#!/usr/bin/env python3
"""Calculate documented savings APY components and a complete-cycle interest difference.

Reads one JSON object from stdin and emits one JSON object to stdout. It does not access
accounts, invoke banking tools, or determine eligibility; callers must supply only
verified, documented facts.
"""

import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def number(value, label, errors, nonnegative=True):
    if isinstance(value, bool) or value is None:
        errors.append(f"{label} must be a finite number")
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be a finite number")
        return None
    if not math.isfinite(parsed):
        errors.append(f"{label} must be a finite number")
        return None
    if nonnegative and parsed < 0:
        errors.append(f"{label} must not be negative")
        return None
    return parsed


def component_list(raw, label, errors):
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append(f"{label} must be a list")
        return []
    result = []
    for index, item in enumerate(raw):
        prefix = f"{label}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a nonempty string")
            continue
        applicable = item.get("applicable")
        if not isinstance(applicable, bool):
            errors.append(f"{prefix}.applicable must be boolean")
            continue
        apy = number(item.get("apy"), f"{prefix}.apy", errors)
        if apy is not None:
            result.append({"name": name.strip(), "apy": apy, "applicable": applicable})
    return result


def cents(value):
    return float(Decimal(f"{value:.12f}").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def highest(items):
    applicable = [item for item in items if item["applicable"]]
    if not applicable:
        return None
    return sorted(applicable, key=lambda item: (-item["apy"], item["name"].casefold()))[0]


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        emit({"ok": False, "errors": [f"invalid JSON input: {exc}"]})
        return

    if not isinstance(payload, dict):
        emit({"ok": False, "errors": ["top-level JSON value must be an object"]})
        return

    errors = []
    base = number(payload.get("base_apy"), "base_apy", errors)
    checking = component_list(payload.get("checking_boosts", []), "checking_boosts", errors)
    cards = component_list(payload.get("card_bonuses", []), "card_bonuses", errors)
    additive = component_list(payload.get("additive_components", []), "additive_components", errors)
    if errors:
        emit({"ok": False, "errors": errors})
        return

    chosen_checking = highest(checking)
    chosen_card = highest(cards)
    approved_additive = [item for item in additive if item["applicable"]]
    selected = [{"name": "base_apy", "apy": base}]
    if chosen_checking:
        selected.append({"name": chosen_checking["name"], "apy": chosen_checking["apy"], "category": "highest_checking_boost"})
    if chosen_card:
        selected.append({"name": chosen_card["name"], "apy": chosen_card["apy"], "category": "highest_card_bonus"})
    for item in approved_additive:
        selected.append({"name": item["name"], "apy": item["apy"], "category": "additive_component"})

    expected_apy = sum(item["apy"] for item in selected)
    output = {
        "ok": True,
        "expected_apy": expected_apy,
        "selected_components": selected,
        "selection_notes": {
            "checking_policy": "only the highest applicable checking boost was selected",
            "card_policy": "only the highest applicable card bonus was selected",
            "additive_policy": "additive components were included exactly as supplied by the caller"
        },
        "report_ready": False
    }

    if "period" not in payload or payload["period"] is None:
        output["cycle_status"] = "not_calculated: period data was not supplied"
        emit(output)
        return

    period = payload["period"]
    if not isinstance(period, dict):
        emit({"ok": False, "errors": ["period must be an object"]})
        return

    balances = period.get("daily_balances")
    if not isinstance(balances, list) or not balances:
        emit({"ok": False, "errors": ["period.daily_balances must be a nonempty chronological list"]})
        return
    parsed_balances = []
    for index, balance in enumerate(balances):
        parsed = number(balance, f"period.daily_balances[{index}]", errors)
        if parsed is not None:
            parsed_balances.append(parsed)

    actual_interest = number(period.get("actual_interest"), "period.actual_interest", errors)
    actual_apy = number(period.get("actual_apy"), "period.actual_apy", errors)
    days_per_year = period.get("days_per_year", 365)
    if isinstance(days_per_year, bool) or days_per_year not in (365, 366):
        errors.append("period.days_per_year must be 365 or 366")
    if errors:
        emit({"ok": False, "errors": errors})
        return

    daily_rate = math.expm1(math.log1p(expected_apy / 100.0) / days_per_year)
    accrued = 0.0
    for balance in parsed_balances:
        accrued = (balance + accrued) * daily_rate

    expected_interest = cents(accrued)
    difference = cents(expected_interest - actual_interest)
    output.update({
        "cycle_status": "calculated",
        "cycle_days": len(parsed_balances),
        "daily_rate": daily_rate,
        "expected_interest": expected_interest,
        "actual_interest": cents(actual_interest),
        "actual_apy": actual_apy,
        "amount_difference": difference,
        "report_ready": difference > 0
    })
    if difference <= 0:
        output["report_blocker"] = "A positive interest-correction amount is required before this credit-first report workflow can proceed."
    emit(output)


if __name__ == "__main__":
    main()
