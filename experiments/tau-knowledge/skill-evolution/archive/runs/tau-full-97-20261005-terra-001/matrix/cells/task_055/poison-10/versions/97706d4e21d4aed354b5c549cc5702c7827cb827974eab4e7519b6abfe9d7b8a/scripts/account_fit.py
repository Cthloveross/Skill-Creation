#!/usr/bin/env python3
"""Rank bank-account candidates against structured customer needs.

Reads one JSON object from stdin and writes one JSON object to stdout.
This utility is advisory: it never accesses accounts, retrieves data, or performs
banking actions. Product terms must be extracted from the current task evidence.
"""

import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def number(value: Any, field: str, warnings: List[str]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        warnings.append(f"{field} is unavailable or is not numeric.")
        return None
    return float(value)


def text(value: Any, field: str, warnings: List[str]) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        warnings.append(f"{field} is missing.")
        return None
    return value.strip()


def needs_object(root: Dict[str, Any], key: str, warnings: List[str]) -> Dict[str, Any]:
    value = root.get(key, {})
    if not isinstance(value, dict):
        warnings.append(f"{key} must be an object; treating it as empty.")
        return {}
    return value


def candidate_list(root: Dict[str, Any], key: str, warnings: List[str]) -> List[Dict[str, Any]]:
    value = root.get(key, [])
    if not isinstance(value, list):
        warnings.append(f"{key} must be an array; treating it as empty.")
        return []
    return [item for item in value if isinstance(item, dict)]


def as_nonnegative(value: Optional[float], label: str, warnings: List[str]) -> Optional[float]:
    if value is not None and value < 0:
        warnings.append(f"{label} must not be negative.")
        return None
    return value


def apy_at_balance(tiers: Any, balance: Optional[float], warnings: List[str], name: str) -> Optional[float]:
    if balance is None:
        return None
    if not isinstance(tiers, list) or not tiers:
        warnings.append(f"{name}: no APY tiers were supplied.")
        return None
    usable: List[Tuple[float, float]] = []
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            warnings.append(f"{name}: APY tier {index + 1} is invalid.")
            continue
        minimum = number(tier.get("minimum_balance"), f"{name}.apy_tiers[{index}].minimum_balance", warnings)
        apy = number(tier.get("apy"), f"{name}.apy_tiers[{index}].apy", warnings)
        if minimum is not None and apy is not None and minimum >= 0:
            usable.append((minimum, apy))
    eligible = [tier for tier in usable if tier[0] <= balance]
    if not eligible:
        warnings.append(f"{name}: no supplied APY tier applies at the conservative expected balance.")
        return None
    return max(eligible, key=lambda tier: tier[0])[1]


def evaluate_checking(candidate: Dict[str, Any], needs: Dict[str, Any]) -> Dict[str, Any]:
    warnings: List[str] = []
    name = text(candidate.get("name"), "checking candidate name", warnings) or "Unnamed checking candidate"
    balance_min = as_nonnegative(number(needs.get("expected_balance_min"), "checking_needs.expected_balance_min", warnings), "checking_needs.expected_balance_min", warnings)
    balance_max = as_nonnegative(number(needs.get("expected_balance_max"), "checking_needs.expected_balance_max", warnings), "checking_needs.expected_balance_max", warnings)
    if balance_min is not None and balance_max is not None and balance_min > balance_max:
        warnings.append("checking expected_balance_min exceeds expected_balance_max.")

    foreign_tx = number(candidate.get("foreign_transaction_fee_percent"), f"{name}.foreign_transaction_fee_percent", warnings)
    foreign_atm = number(candidate.get("foreign_atm_fee"), f"{name}.foreign_atm_fee", warnings)
    rebate = number(candidate.get("atm_rebate_cap"), f"{name}.atm_rebate_cap", warnings)
    monthly_fee = number(candidate.get("monthly_fee"), f"{name}.monthly_fee", warnings)
    waiver = number(candidate.get("fee_waiver_balance"), f"{name}.fee_waiver_balance", warnings)

    hard_pass = True
    if needs.get("requires_zero_foreign_transaction_fee") is True:
        if foreign_tx is None:
            hard_pass = False
            warnings.append("Cannot confirm the required zero foreign transaction fee.")
        elif foreign_tx > 0:
            hard_pass = False
            warnings.append("Does not meet the required zero foreign transaction fee.")
    if needs.get("requires_zero_foreign_atm_fee") is True:
        if foreign_atm is None:
            hard_pass = False
            warnings.append("Cannot confirm the required zero foreign ATM fee.")
        elif foreign_atm > 0:
            hard_pass = False
            warnings.append("Does not meet the required zero foreign ATM fee.")
    requested_rebate = as_nonnegative(number(needs.get("minimum_atm_rebate"), "checking_needs.minimum_atm_rebate", warnings), "checking_needs.minimum_atm_rebate", warnings)
    if requested_rebate is not None and requested_rebate > 0:
        if rebate is None or rebate < requested_rebate:
            hard_pass = False
            warnings.append("Does not meet the requested ATM-rebate cap.")

    waiver_status = "not_applicable"
    if monthly_fee is not None and monthly_fee > 0:
        if waiver is None:
            waiver_status = "unknown"
            warnings.append("A monthly fee is documented but its waiver threshold is unavailable.")
        elif balance_min is not None and balance_min >= waiver:
            waiver_status = "guaranteed_by_stated_range"
        elif balance_max is not None and balance_max >= waiver:
            waiver_status = "possible_not_guaranteed"
            warnings.append("The stated balance range can fall below the fee-waiver threshold.")
        else:
            waiver_status = "not_reached_by_stated_range"
            warnings.append("The stated balance range does not reach the fee-waiver threshold.")

    score = (
        1 if hard_pass else 0,
        1 if waiver_status in ("not_applicable", "guaranteed_by_stated_range") else 0,
        rebate if rebate is not None else -1.0,
        -(monthly_fee if monthly_fee is not None else 1e12),
    )
    return {
        "name": name,
        "hard_requirements_met": hard_pass,
        "fee_waiver_status": waiver_status,
        "facts": {
            "foreign_transaction_fee_percent": foreign_tx,
            "foreign_atm_fee": foreign_atm,
            "atm_rebate_cap": rebate,
            "monthly_fee": monthly_fee,
            "fee_waiver_balance": waiver,
        },
        "warnings": warnings,
        "_score": score,
    }


def evaluate_savings(candidate: Dict[str, Any], needs: Dict[str, Any]) -> Dict[str, Any]:
    warnings: List[str] = []
    name = text(candidate.get("name"), "savings candidate name", warnings) or "Unnamed savings candidate"
    balance_min = as_nonnegative(number(needs.get("expected_balance_min"), "savings_needs.expected_balance_min", warnings), "savings_needs.expected_balance_min", warnings)
    balance_max = as_nonnegative(number(needs.get("expected_balance_max"), "savings_needs.expected_balance_max", warnings), "savings_needs.expected_balance_max", warnings)
    if balance_min is not None and balance_max is not None and balance_min > balance_max:
        warnings.append("savings expected_balance_min exceeds expected_balance_max.")
    opening = as_nonnegative(number(candidate.get("opening_deposit"), f"{name}.opening_deposit", warnings), f"{name}.opening_deposit", warnings)
    ongoing = as_nonnegative(number(candidate.get("ongoing_minimum_balance"), f"{name}.ongoing_minimum_balance", warnings), f"{name}.ongoing_minimum_balance", warnings)
    free_withdrawals = as_nonnegative(number(candidate.get("free_withdrawals_per_month"), f"{name}.free_withdrawals_per_month", warnings), f"{name}.free_withdrawals_per_month", warnings)
    apy = apy_at_balance(candidate.get("apy_tiers"), balance_min, warnings, name)
    required_apy = as_nonnegative(number(needs.get("minimum_apy"), "savings_needs.minimum_apy", warnings), "savings_needs.minimum_apy", warnings)
    withdrawals_min = as_nonnegative(number(needs.get("withdrawals_per_month_min"), "savings_needs.withdrawals_per_month_min", warnings), "savings_needs.withdrawals_per_month_min", warnings)
    withdrawals_max = as_nonnegative(number(needs.get("withdrawals_per_month_max"), "savings_needs.withdrawals_per_month_max", warnings), "savings_needs.withdrawals_per_month_max", warnings)
    if withdrawals_min is not None and withdrawals_max is not None and withdrawals_min > withdrawals_max:
        warnings.append("savings withdrawals_per_month_min exceeds withdrawals_per_month_max.")

    maintainable = ongoing is not None and balance_min is not None and balance_min >= ongoing
    if not maintainable:
        warnings.append("The ongoing minimum balance is not supported by the conservative expected balance, or it is unavailable.")
    opening_affordable = opening is not None and balance_min is not None and balance_min >= opening
    if not opening_affordable:
        warnings.append("The opening deposit is not supported by the conservative expected balance, or it is unavailable.")
    apy_met = required_apy is not None and apy is not None and apy >= required_apy
    if not apy_met:
        warnings.append("The minimum requested APY is not confirmed at the conservative expected balance.")
    withdrawal_full = free_withdrawals is not None and withdrawals_max is not None and free_withdrawals >= withdrawals_max
    withdrawal_partial = free_withdrawals is not None and withdrawals_min is not None and free_withdrawals >= withdrawals_min
    if not withdrawal_full:
        if withdrawal_partial:
            warnings.append("The free-withdrawal allowance covers only the low end of the stated monthly usage range.")
        else:
            warnings.append("The free-withdrawal allowance does not cover the stated typical monthly usage.")

    hard_pass = maintainable and opening_affordable and apy_met
    score = (
        1 if hard_pass else 0,
        1 if withdrawal_full else 0,
        1 if withdrawal_partial else 0,
        apy if apy is not None else -1.0,
        free_withdrawals if free_withdrawals is not None else -1.0,
    )
    return {
        "name": name,
        "hard_requirements_met": hard_pass,
        "free_withdrawals_cover_maximum_usage": withdrawal_full,
        "free_withdrawals_cover_minimum_usage": withdrawal_partial,
        "apy_at_conservative_balance": apy,
        "facts": {
            "opening_deposit": opening,
            "ongoing_minimum_balance": ongoing,
            "free_withdrawals_per_month": free_withdrawals,
        },
        "warnings": warnings,
        "_score": score,
    }


def public_evaluation(item: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in item.items() if key != "_score"}


def main() -> None:
    try:
        root = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON input: {exc.msg}"}))
        return
    if not isinstance(root, dict):
        print(json.dumps({"error": "Input must be a JSON object."}))
        return

    global_warnings: List[str] = []
    checking_needs = needs_object(root, "checking_needs", global_warnings)
    savings_needs = needs_object(root, "savings_needs", global_warnings)
    checking = [evaluate_checking(item, checking_needs) for item in candidate_list(root, "checking_candidates", global_warnings)]
    savings = [evaluate_savings(item, savings_needs) for item in candidate_list(root, "savings_candidates", global_warnings)]
    checking.sort(key=lambda item: item["_score"], reverse=True)
    savings.sort(key=lambda item: item["_score"], reverse=True)

    result = {
        "warnings": global_warnings,
        "checking": [public_evaluation(item) for item in checking],
        "savings": [public_evaluation(item) for item in savings],
        "best": {
            "checking": public_evaluation(checking[0]) if checking else None,
            "savings": public_evaluation(savings[0]) if savings else None,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
