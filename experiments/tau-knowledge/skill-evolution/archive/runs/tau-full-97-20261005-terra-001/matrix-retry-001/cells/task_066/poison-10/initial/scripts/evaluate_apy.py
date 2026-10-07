#!/usr/bin/env python3
"""Rank documented APY configurations supplied as JSON on stdin.

All APY values are percentage points, not decimal rates. This helper only uses
runtime inputs; it does not encode financial product terms or perform actions.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


VALID_STATUS = {True, False, "unknown"}


def number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric, not boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def money_string(value):
    return format(value.quantize(Decimal("0.01")), "f")


def apy_string(value):
    return format(value.quantize(Decimal("0.0001")).normalize(), "f")


def best_bonus(entries, group_name):
    if entries is None:
        return Decimal("0"), None
    if not isinstance(entries, list):
        raise ValueError(f"{group_name} must be a list")
    eligible = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{group_name}[{index}] must be an object")
        if entry.get("eligible") is True:
            apy = number(entry.get("apy"), f"{group_name}[{index}].apy")
            if apy < 0:
                raise ValueError(f"{group_name}[{index}].apy cannot be negative")
            eligible.append((apy, str(entry.get("label", f"{group_name}[{index}]"))))
    if not eligible:
        return Decimal("0"), None
    # Stable maximum preserves the supplied ordering for equal documented bonuses.
    return max(eligible, key=lambda item: item[0])


def assess(candidate, balance):
    if not isinstance(candidate, dict):
        raise ValueError("each candidate must be an object")
    candidate_id = candidate.get("id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate.id must be a nonempty string")

    base = number(candidate.get("base_apy"), f"{candidate_id}.base_apy")
    minimum = number(candidate.get("minimum_balance", 0), f"{candidate_id}.minimum_balance")
    if base < 0 or minimum < 0:
        raise ValueError(f"{candidate_id}: base_apy and minimum_balance cannot be negative")

    applied_overrides = []
    overrides = candidate.get("minimum_balance_overrides", [])
    if not isinstance(overrides, list):
        raise ValueError(f"{candidate_id}.minimum_balance_overrides must be a list")
    eligible_minima = [minimum]
    for index, override in enumerate(overrides):
        if not isinstance(override, dict):
            raise ValueError(f"{candidate_id}.minimum_balance_overrides[{index}] must be an object")
        if override.get("eligible") is True:
            override_minimum = number(
                override.get("minimum_balance"),
                f"{candidate_id}.minimum_balance_overrides[{index}].minimum_balance",
            )
            if override_minimum < 0:
                raise ValueError(f"{candidate_id}: override minimum cannot be negative")
            eligible_minima.append(override_minimum)
            applied_overrides.append(str(override.get("label", f"override {index}")))
    effective_minimum = min(eligible_minima)

    failures = []
    unknowns = []
    if balance < effective_minimum:
        failures.append(
            f"balance {money_string(balance)} is below required minimum {money_string(effective_minimum)}"
        )

    requirements = candidate.get("requirements", [])
    if not isinstance(requirements, list):
        raise ValueError(f"{candidate_id}.requirements must be a list")
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            raise ValueError(f"{candidate_id}.requirements[{index}] must be an object")
        status = requirement.get("status")
        if status not in VALID_STATUS:
            raise ValueError(f"{candidate_id}.requirements[{index}].status must be true, false, or 'unknown'")
        name = str(requirement.get("name", f"requirement {index}"))
        if status is False:
            failures.append(name)
        elif status == "unknown":
            unknowns.append(name)

    checking_apy, checking_label = best_bonus(candidate.get("checking_boosts", []), f"{candidate_id}.checking_boosts")
    card_apy, card_label = best_bonus(candidate.get("card_bonuses", []), f"{candidate_id}.card_bonuses")

    additional_apy = Decimal("0")
    additional_labels = []
    additional = candidate.get("additional_bonuses", [])
    if not isinstance(additional, list):
        raise ValueError(f"{candidate_id}.additional_bonuses must be a list")
    for index, entry in enumerate(additional):
        if not isinstance(entry, dict):
            raise ValueError(f"{candidate_id}.additional_bonuses[{index}] must be an object")
        if entry.get("eligible") is True:
            apy = number(entry.get("apy"), f"{candidate_id}.additional_bonuses[{index}].apy")
            if apy < 0:
                raise ValueError(f"{candidate_id}.additional_bonuses[{index}].apy cannot be negative")
            additional_apy += apy
            additional_labels.append(str(entry.get("label", f"additional_bonuses[{index}]")))

    if failures:
        eligibility = False
    elif unknowns:
        eligibility = "unknown"
    else:
        eligibility = True

    total = base + checking_apy + card_apy + additional_apy
    return {
        "id": candidate_id,
        "eligibility": eligibility,
        "effective_minimum_balance": money_string(effective_minimum),
        "applied_minimum_balance_overrides": applied_overrides,
        "base_apy": apy_string(base),
        "selected_checking_boost": None if checking_label is None else {"label": checking_label, "apy": apy_string(checking_apy)},
        "selected_card_bonus": None if card_label is None else {"label": card_label, "apy": apy_string(card_apy)},
        "applied_additional_bonuses": additional_labels,
        "total_apy": apy_string(total),
        "ineligible_reasons": failures,
        "unknown_requirements": unknowns,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        balance = number(payload.get("balance"), "balance")
        if balance < 0:
            raise ValueError("balance cannot be negative")
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("candidates must be a nonempty list")
        results = [assess(candidate, balance) for candidate in candidates]

        # Fully eligible choices first, then conditional choices, then ineligible ones;
        # within each group, sort by calculated APY descending.
        rank = {True: 0, "unknown": 1, False: 2}
        results.sort(key=lambda item: (rank[item["eligibility"]], -Decimal(item["total_apy"]), item["id"]))
        recommendation = next((item["id"] for item in results if item["eligibility"] is True), None)
        output = {
            "balance": money_string(balance),
            "ranked_candidates": results,
            "best_fully_eligible_candidate": recommendation,
            "warning": "Results are a calculation from supplied documented facts. Unknown eligibility and card approval must be resolved before presenting an option as available.",
        }
        json.dump(output, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        json.dump({"error": str(exc)}, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
