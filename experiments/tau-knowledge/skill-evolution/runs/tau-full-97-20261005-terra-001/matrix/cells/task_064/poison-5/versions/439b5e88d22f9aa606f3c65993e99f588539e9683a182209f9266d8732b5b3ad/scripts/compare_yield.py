#!/usr/bin/env python3
"""Calculate and rank documented savings/card yield options.

Reads one JSON object from stdin and writes one JSON object to stdout. APY values
are percentage points. The caller supplies documented terms and eligibility facts;
this program does not infer product terms or approval status.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
VALID_STATES = {"met", "unknown", "failed"}


def as_decimal(value, field, option_index=None):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        where = "" if option_index is None else f" in option {option_index}"
        raise ValueError(f"{field}{where} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def json_number(value):
    return float(value)


def option_result(option, index, deposit, years):
    if not isinstance(option, dict):
        raise ValueError(f"option {index} must be an object")

    account = option.get("savings_account")
    if not isinstance(account, str) or not account.strip():
        raise ValueError(f"option {index} requires a nonempty savings_account")

    fields = {
        "base_apy": option.get("base_apy"),
        "card_apy_bonus": option.get("card_apy_bonus", 0),
        "other_apy_bonus": option.get("other_apy_bonus", 0),
        "opening_minimum": option.get("opening_minimum", 0),
        "ongoing_minimum": option.get("ongoing_minimum", 0),
        "annual_card_fee": option.get("annual_card_fee", 0),
        "maintenance_fee_annual": option.get("maintenance_fee_annual", 0),
    }
    values = {name: as_decimal(value, name, index) for name, value in fields.items()}
    if any(value < 0 for value in values.values()):
        raise ValueError(f"option {index} contains a negative value")

    eligibility = option.get("eligibility", {})
    if not isinstance(eligibility, dict):
        raise ValueError(f"eligibility in option {index} must be an object")

    unresolved = []
    failed = []
    for requirement, state in eligibility.items():
        if not isinstance(requirement, str) or not requirement.strip():
            raise ValueError(f"eligibility requirement in option {index} must be nonempty text")
        if state not in VALID_STATES:
            raise ValueError(
                f"eligibility state for {requirement!r} in option {index} "
                "must be met, unknown, or failed"
            )
        if state == "unknown":
            unresolved.append(requirement)
        elif state == "failed":
            failed.append(requirement)

    if deposit < values["opening_minimum"]:
        failed.append("opening minimum")
    if deposit < values["ongoing_minimum"]:
        failed.append("ongoing minimum")

    status = "ineligible" if failed else ("conditional" if unresolved else "eligible")
    effective_apy = values["base_apy"] + values["card_apy_bonus"] + values["other_apy_bonus"]
    estimated_interest = money(deposit * effective_apy / HUNDRED * years)
    total_fees = money((values["annual_card_fee"] + values["maintenance_fee_annual"]) * years)
    net_value = money(estimated_interest - total_fees)

    notes = option.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
        raise ValueError(f"notes in option {index} must be an array of strings")

    return {
        "savings_account": account,
        "card": option.get("card"),
        "status": status,
        "base_apy": json_number(values["base_apy"]),
        "card_apy_bonus": json_number(values["card_apy_bonus"]),
        "other_apy_bonus": json_number(values["other_apy_bonus"]),
        "effective_apy": json_number(effective_apy),
        "estimated_interest": json_number(estimated_interest),
        "annual_card_fee": json_number(money(values["annual_card_fee"])),
        "annual_maintenance_fee_assumed": json_number(money(values["maintenance_fee_annual"])),
        "total_estimated_fees": json_number(total_fees),
        "net_estimated_value": json_number(net_value),
        "unresolved_requirements": sorted(unresolved),
        "failed_requirements": sorted(set(failed)),
        "notes": notes,
    }


def calculate(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    deposit = as_decimal(payload.get("deposit"), "deposit")
    years = as_decimal(payload.get("term_years", 1), "term_years")
    if deposit < 0:
        raise ValueError("deposit must be nonnegative")
    if years <= 0:
        raise ValueError("term_years must be positive")

    options = payload.get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("options must be a nonempty array")

    results = [option_result(option, i, deposit, years) for i, option in enumerate(options)]
    priority = {"eligible": 0, "conditional": 1, "ineligible": 2}
    results.sort(
        key=lambda item: (
            priority[item["status"]],
            -item["net_estimated_value"],
            item["savings_account"].casefold(),
            str(item["card"] or "").casefold(),
        )
    )

    return {
        "deposit": json_number(money(deposit)),
        "term_years": json_number(years),
        "calculation_assumption": (
            "Constant deposit balance; APY-based simple estimate for the stated term; "
            "documented annual card and assumed maintenance fees deducted."
        ),
        "ranked_options": results,
        "best_eligible_option": next((x for x in results if x["status"] == "eligible"), None),
        "best_conditional_option": next((x for x in results if x["status"] == "conditional"), None),
    }


def main():
    try:
        print(json.dumps(calculate(json.load(sys.stdin)), sort_keys=True, separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
