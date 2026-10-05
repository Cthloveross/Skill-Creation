#!/usr/bin/env python3
"""Evaluate structured bank-account candidates against stated customer needs.

Reads one JSON object from stdin and writes one JSON object to stdout. This is
an offline advisory utility: it does not retrieve account data or take actions.
"""
import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def numeric(value: Any, label: str, notes: List[str]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        notes.append(f"{label} must be a number or null.")
        return None
    if value < 0:
        notes.append(f"{label} must not be negative.")
        return None
    return float(value)


def obj(root: Dict[str, Any], key: str, notes: List[str]) -> Dict[str, Any]:
    value = root.get(key, {})
    if not isinstance(value, dict):
        notes.append(f"{key} must be an object.")
        return {}
    return value


def records(root: Dict[str, Any], key: str, notes: List[str]) -> List[Dict[str, Any]]:
    value = root.get(key, [])
    if not isinstance(value, list):
        notes.append(f"{key} must be an array.")
        return []
    bad = sum(not isinstance(item, dict) for item in value)
    if bad:
        notes.append(f"{key} contains {bad} non-object candidate(s), which were ignored.")
    return [item for item in value if isinstance(item, dict)]


def name_of(candidate: Dict[str, Any], kind: str, notes: List[str]) -> str:
    value = candidate.get("name")
    if not isinstance(value, str) or not value.strip():
        notes.append(f"{kind} candidate has no official name.")
        return "Unnamed candidate"
    return value.strip()


def bounded_range(needs: Dict[str, Any], prefix: str, notes: List[str]) -> Tuple[Optional[float], Optional[float]]:
    low = numeric(needs.get("expected_balance_min"), f"{prefix}.expected_balance_min", notes)
    high = numeric(needs.get("expected_balance_max"), f"{prefix}.expected_balance_max", notes)
    if low is not None and high is not None and low > high:
        notes.append(f"{prefix} expected balance minimum exceeds maximum.")
    return low, high


def tier_apy(tiers: Any, balance: Optional[float], label: str, notes: List[str]) -> Optional[float]:
    if balance is None:
        notes.append(f"{label}: conservative expected balance is unavailable; applicable APY cannot be determined.")
        return None
    if not isinstance(tiers, list) or not tiers:
        notes.append(f"{label}: no APY tiers were supplied.")
        return None
    usable: List[Tuple[float, float]] = []
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            notes.append(f"{label}: APY tier {index + 1} is invalid.")
            continue
        minimum = numeric(tier.get("minimum_balance"), f"{label}.apy_tiers[{index}].minimum_balance", notes)
        apy = numeric(tier.get("apy"), f"{label}.apy_tiers[{index}].apy", notes)
        if minimum is not None and apy is not None:
            usable.append((minimum, apy))
    applicable = [item for item in usable if item[0] <= balance]
    if not applicable:
        notes.append(f"{label}: no APY tier applies at the conservative expected balance.")
        return None
    return max(applicable, key=lambda item: item[0])[1]


def check_checking(candidate: Dict[str, Any], needs: Dict[str, Any]) -> Dict[str, Any]:
    notes: List[str] = []
    name = name_of(candidate, "checking", notes)
    low, high = bounded_range(needs, "checking_needs", notes)
    foreign_tx = numeric(candidate.get("foreign_transaction_fee_percent"), f"{name}.foreign_transaction_fee_percent", notes)
    foreign_atm = numeric(candidate.get("foreign_atm_fee"), f"{name}.foreign_atm_fee", notes)
    out_network = numeric(candidate.get("out_of_network_atm_fee"), f"{name}.out_of_network_atm_fee", notes)
    rebate = numeric(candidate.get("atm_rebate_cap"), f"{name}.atm_rebate_cap", notes)
    monthly = numeric(candidate.get("monthly_fee"), f"{name}.monthly_fee", notes)
    waiver = numeric(candidate.get("fee_waiver_balance"), f"{name}.fee_waiver_balance", notes)
    disclosures: List[str] = []
    compatible = True

    if needs.get("requires_zero_foreign_transaction_fee") is True:
        if foreign_tx != 0:
            compatible = False
            notes.append("Required zero foreign-transaction fee is not confirmed.")
    if needs.get("requires_zero_foreign_atm_fee") is True:
        if foreign_atm != 0:
            compatible = False
            notes.append("Required zero bank foreign-ATM fee is not confirmed.")
    minimum_rebate = numeric(needs.get("minimum_atm_rebate"), "checking_needs.minimum_atm_rebate", notes)
    if minimum_rebate is not None and minimum_rebate > 0 and (rebate is None or rebate < minimum_rebate):
        compatible = False
        notes.append("Requested ATM-rebate cap is not met or cannot be confirmed.")
    if rebate is not None:
        disclosures.append("State that ATM operator-fee reimbursement is capped and that operator charges are separate from bank fees.")
    if out_network is not None:
        disclosures.append("Disclose the separately documented out-of-network ATM bank fee; do not imply all ATM use is free.")

    waiver_status = "not_applicable"
    if monthly is not None and monthly > 0:
        disclosures.append("Disclose the monthly maintenance fee and its waiver condition.")
        if waiver is None:
            waiver_status = "unknown"
        elif low is not None and low >= waiver:
            waiver_status = "supported_throughout_stated_range"
        elif high is not None and high >= waiver:
            waiver_status = "possible_but_not_guaranteed"
            notes.append("Customer balance can fall below the maintenance-fee waiver threshold.")
        else:
            waiver_status = "not_supported_by_stated_range"
            notes.append("Customer balance does not reach the maintenance-fee waiver threshold.")

    score = (int(compatible), int(waiver_status in ("not_applicable", "supported_throughout_stated_range")), rebate if rebate is not None else -1, -(monthly if monthly is not None else 1e9))
    return {"name": name, "compatible_with_explicit_checking_needs": compatible,
            "fee_waiver_status": waiver_status,
            "facts": {"foreign_transaction_fee_percent": foreign_tx, "foreign_atm_fee": foreign_atm,
                      "out_of_network_atm_fee": out_network, "atm_rebate_cap": rebate,
                      "monthly_fee": monthly, "fee_waiver_balance": waiver},
            "required_disclosures": disclosures, "warnings": notes, "_score": score}


def check_savings(candidate: Dict[str, Any], needs: Dict[str, Any]) -> Dict[str, Any]:
    notes: List[str] = []
    name = name_of(candidate, "savings", notes)
    low, high = bounded_range(needs, "savings_needs", notes)
    opening = numeric(candidate.get("opening_deposit"), f"{name}.opening_deposit", notes)
    ongoing = numeric(candidate.get("ongoing_minimum_balance"), f"{name}.ongoing_minimum_balance", notes)
    free = numeric(candidate.get("free_withdrawals_per_month"), f"{name}.free_withdrawals_per_month", notes)
    excess = numeric(candidate.get("excess_withdrawal_fee"), f"{name}.excess_withdrawal_fee", notes)
    apy = tier_apy(candidate.get("apy_tiers"), low, name, notes)
    target = numeric(needs.get("minimum_apy"), "savings_needs.minimum_apy", notes)
    use_low = numeric(needs.get("withdrawals_per_month_min"), "savings_needs.withdrawals_per_month_min", notes)
    use_high = numeric(needs.get("withdrawals_per_month_max"), "savings_needs.withdrawals_per_month_max", notes)
    if use_low is not None and use_high is not None and use_low > use_high:
        notes.append("savings withdrawal minimum exceeds maximum.")

    opening_ok = opening is not None and low is not None and low >= opening
    ongoing_ok = ongoing is not None and low is not None and low >= ongoing
    apy_ok = target is not None and apy is not None and apy >= target
    for condition, message in ((opening_ok, "Opening deposit is not supported by the conservative expected balance."),
                               (ongoing_ok, "Ongoing minimum is not supported by the conservative expected balance."),
                               (apy_ok, "Minimum requested APY is not confirmed at the conservative expected balance.")):
        if not condition:
            notes.append(message)
    covers_max = free is not None and use_high is not None and free >= use_high
    covers_min = free is not None and use_low is not None and free >= use_low
    disclosures = ["State the opening deposit, ongoing minimum, applicable APY, and higher-tier threshold from evidence."]
    if not covers_max:
        disclosures.append("Disclose that the free withdrawal allowance may not cover the customer's maximum monthly use.")
        if excess is not None:
            disclosures.append("State the documented excess-withdrawal fee.")
    feasible = opening_ok and ongoing_ok and apy_ok
    score = (int(feasible), int(covers_max), int(covers_min), apy if apy is not None else -1, free if free is not None else -1)
    return {"name": name, "meets_balance_and_apy_needs": feasible,
            "free_withdrawals_cover_maximum_usage": covers_max,
            "free_withdrawals_cover_minimum_usage": covers_min,
            "apy_at_conservative_balance": apy,
            "facts": {"opening_deposit": opening, "ongoing_minimum_balance": ongoing,
                      "free_withdrawals_per_month": free, "excess_withdrawal_fee": excess},
            "required_disclosures": disclosures, "warnings": notes, "_score": score}


def public(item: Dict[str, Any]) -> Dict[str, Any]:
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
    global_notes: List[str] = []
    checking_needs = obj(root, "checking_needs", global_notes)
    savings_needs = obj(root, "savings_needs", global_notes)
    checking = [check_checking(item, checking_needs) for item in records(root, "checking_candidates", global_notes)]
    savings = [check_savings(item, savings_needs) for item in records(root, "savings_candidates", global_notes)]
    checking.sort(key=lambda item: item["_score"], reverse=True)
    savings.sort(key=lambda item: item["_score"], reverse=True)
    print(json.dumps({"warnings": global_notes, "checking": [public(item) for item in checking],
                      "savings": [public(item) for item in savings],
                      "best": {"checking": public(checking[0]) if checking else None,
                               "savings": public(savings[0]) if savings else None}}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
