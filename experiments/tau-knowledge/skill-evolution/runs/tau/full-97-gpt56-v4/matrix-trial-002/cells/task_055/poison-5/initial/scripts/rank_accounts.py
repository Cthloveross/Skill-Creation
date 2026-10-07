#!/usr/bin/env python3
"""Rank normalized checking and savings candidates without performing bank actions.

Read one JSON object from stdin and write one JSON object to stdout. See SKILL.md for
schema. This helper only scores supplied facts; missing terms remain warnings.
"""
import json
import sys
from typing import Any, Dict, List, Optional

NUMERIC_FIELDS = {
    "opening_deposit", "ongoing_minimum", "maintenance_fee",
    "maintenance_fee_waiver_balance", "foreign_transaction_fee_percent",
    "foreign_atm_fee", "out_of_network_atm_fee", "atm_rebate_monthly",
    "base_apy_percent", "tier_threshold", "tier_apy_percent",
    "free_withdrawals_monthly", "excess_withdrawal_fee",
    "linked_checking_boost_percent",
}


def number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def fits_minimum(account: Dict[str, Any], balance: Optional[float]) -> Optional[bool]:
    minimum = number(account.get("ongoing_minimum"))
    if balance is None or minimum is None:
        return None
    return balance >= minimum


def checking_score(account: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    score = 0.0
    flags: List[str] = []
    warnings: List[str] = []
    balance = number(profile.get("travel_checking_balance"))

    if profile.get("foreign_atm_priority"):
        fee = number(account.get("foreign_atm_fee"))
        rebate = number(account.get("atm_rebate_monthly"))
        if fee is None:
            warnings.append("Foreign-ATM fee is not documented in this candidate record.")
        else:
            score += max(0.0, 10.0 - fee)
            if fee == 0:
                flags.append("Documented zero bank foreign-ATM fee")
        if rebate is None:
            warnings.append("ATM rebate cap is not documented in this candidate record.")
        else:
            score += min(rebate, 1000.0) / 10.0
            if rebate > 0:
                flags.append("Documented monthly ATM-rebate allowance")

    if profile.get("foreign_purchase_priority"):
        foreign_txn = number(account.get("foreign_transaction_fee_percent"))
        if foreign_txn is None:
            warnings.append("Foreign-transaction fee is not documented in this candidate record.")
        else:
            score += max(0.0, 5.0 - foreign_txn)
            if foreign_txn == 0:
                flags.append("Documented zero foreign-transaction fee")

    waiver = number(account.get("maintenance_fee_waiver_balance"))
    fee = number(account.get("maintenance_fee"))
    if fee is not None and fee > 0:
        if waiver is None or balance is None:
            warnings.append("Maintenance-fee waiver fit cannot be determined.")
        elif balance >= waiver:
            flags.append("Stated balance meets the documented maintenance-fee waiver threshold")
            score += 3.0
        else:
            warnings.append("Stated balance is below the documented maintenance-fee waiver threshold.")
            score -= min(fee, 1000.0) / 2.0

    out_network = number(account.get("out_of_network_atm_fee"))
    if out_network is not None and out_network > 0:
        warnings.append("A separate out-of-network ATM fee is documented; confirm when it applies.")

    return {"score": round(score, 4), "flags": flags, "warnings": warnings,
            "minimum_fit": fits_minimum(account, balance)}


def savings_score(account: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    score = 0.0
    flags: List[str] = []
    warnings: List[str] = []
    balance = number(profile.get("emergency_savings_balance"))
    withdrawals = number(profile.get("monthly_savings_withdrawals"))

    min_fit = fits_minimum(account, balance)
    if min_fit is False:
        warnings.append("Stated emergency-fund balance is below the documented ongoing minimum.")
        score -= 20.0
    elif min_fit is True:
        flags.append("Stated emergency-fund balance meets the documented ongoing minimum")
        score += 2.0
    else:
        warnings.append("Ongoing-minimum fit cannot be determined from supplied data.")

    base_apy = number(account.get("base_apy_percent"))
    tier_threshold = number(account.get("tier_threshold"))
    tier_apy = number(account.get("tier_apy_percent"))
    if base_apy is not None:
        applicable_apy = base_apy
        if tier_threshold is not None and tier_apy is not None and balance is not None and balance >= tier_threshold:
            applicable_apy = tier_apy
            flags.append("Stated balance reaches the documented higher APY tier")
        elif tier_threshold is not None and tier_apy is not None and balance is not None:
            flags.append("Stated balance remains in the documented lower APY tier")
        score += applicable_apy
    else:
        warnings.append("Base APY is not documented in this candidate record.")

    free = number(account.get("free_withdrawals_monthly"))
    excess_fee = number(account.get("excess_withdrawal_fee"))
    if withdrawals is None:
        warnings.append("Monthly withdrawal frequency is unknown.")
    elif free is None:
        warnings.append("Free-withdrawal allowance is not documented in this candidate record.")
    elif withdrawals <= free:
        flags.append("Stated withdrawal frequency is within the documented free allowance")
        score += 5.0
    else:
        overage = withdrawals - free
        warning = "Stated withdrawal frequency exceeds the documented free allowance by {} withdrawal(s).".format(int(overage) if overage.is_integer() else overage)
        if excess_fee is not None:
            warning += " A documented excess-withdrawal fee may apply."
            score -= overage * excess_fee
        else:
            warning += " The cost after the allowance is not documented."
        warnings.append(warning)

    linked_names = account.get("eligible_linked_checking_names")
    if isinstance(linked_names, list):
        existing = set(str(x) for x in profile.get("existing_checking_products", []) if isinstance(x, str))
        matches = [x for x in linked_names if isinstance(x, str) and x in existing]
        if matches:
            boost = number(account.get("linked_checking_boost_percent"))
            flags.append("An exact supplied linked-checking pairing matches: " + ", ".join(matches))
            if boost is not None:
                score += boost
        elif linked_names:
            warnings.append("No exact eligible linked-checking pairing was supplied for this candidate.")

    required_card = account.get("required_card")
    if isinstance(required_card, str) and required_card:
        known_cards = set(str(x) for x in profile.get("known_active_cards", []) if isinstance(x, str))
        if required_card not in known_cards:
            warnings.append("A required card benefit is unconfirmed: " + required_card)

    return {"score": round(score, 4), "flags": flags, "warnings": warnings,
            "minimum_fit": min_fit}


def validate(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object.")
    if not isinstance(payload.get("profile"), dict):
        raise ValueError("profile must be an object.")
    if not isinstance(payload.get("accounts"), list):
        raise ValueError("accounts must be an array.")
    for account in payload["accounts"]:
        if not isinstance(account, dict):
            raise ValueError("Each account must be an object.")
        if account.get("kind") not in ("checking", "savings"):
            raise ValueError("Each account kind must be checking or savings.")
        if not isinstance(account.get("id"), str) or not account["id"]:
            raise ValueError("Each account requires a nonempty string id.")
        if not isinstance(account.get("name"), str) or not account["name"]:
            raise ValueError("Each account requires a nonempty string name.")
        for field in NUMERIC_FIELDS:
            if field in account and account[field] is not None and number(account[field]) is None:
                raise ValueError("{} must be numeric or null for {}.".format(field, account["id"]))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        validate(payload)
        profile = payload["profile"]
        grouped: Dict[str, List[Dict[str, Any]]] = {"checking": [], "savings": []}
        for account in payload["accounts"]:
            assessment = checking_score(account, profile) if account["kind"] == "checking" else savings_score(account, profile)
            grouped[account["kind"]].append({
                "id": account["id"], "name": account["name"], **assessment
            })
        for entries in grouped.values():
            entries.sort(key=lambda item: (-item["score"], item["name"], item["id"]))
        print(json.dumps({
            "ranked_checking": grouped["checking"],
            "ranked_savings": grouped["savings"],
            "notice": "Scores are decision aids only. Review source terms, eligibility, fee categories, and all warnings before advising the customer."
        }, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
