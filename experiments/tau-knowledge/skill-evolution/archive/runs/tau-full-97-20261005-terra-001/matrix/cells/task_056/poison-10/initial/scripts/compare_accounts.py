#!/usr/bin/env python3
"""Deterministically screen a supplied business-checking catalog.

Reads the JSON schema documented in SKILL.md from stdin and writes JSON only.
No product facts are embedded in this helper.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def money(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a nonnegative number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a nonnegative number")
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be a nonnegative number")
    return parsed


def optional_nonnegative(obj, key, unknowns, label):
    if key not in obj:
        unknowns.append(f"{label}: {key} is not documented")
        return "MISSING"
    return money(obj[key], f"{label}.{key}", allow_none=True)


def parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label} must be YYYY-MM-DD")


def display(value):
    if value is None:
        return None
    return format(value, "f")


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    accounts = data.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("accounts must be a nonempty array")
    profile = data.get("profile", {})
    requirements = data.get("requirements", {})
    if not isinstance(profile, dict) or not isinstance(requirements, dict):
        raise ValueError("profile and requirements must be objects")

    age = None
    if "company_age_years" in profile and profile["company_age_years"] is not None:
        age = money(profile["company_age_years"], "profile.company_age_years")
    balance = None
    if "reliable_daily_balance" in profile and profile["reliable_daily_balance"] is not None:
        balance = money(profile["reliable_daily_balance"], "profile.reliable_daily_balance")
    max_waiver = None
    if "maximum_waiver_balance" in requirements and requirements["maximum_waiver_balance"] is not None:
        max_waiver = money(requirements["maximum_waiver_balance"], "requirements.maximum_waiver_balance")
    desired = requirements.get("desired_features", [])
    if not isinstance(desired, list) or not all(isinstance(x, str) and x for x in desired):
        raise ValueError("requirements.desired_features must be an array of nonempty strings")

    zero_od = requirements.get("zero_overdraft_fee_required", False)
    avoid_fee = requirements.get("avoid_monthly_fee", False)
    if not isinstance(zero_od, bool) or not isinstance(avoid_fee, bool):
        raise ValueError("boolean requirement fields must be true or false")

    current = None
    if "current_date" in data and data["current_date"] is not None:
        current = parse_date(data["current_date"], "current_date")
    promotion_names = []
    promotion_active = False
    promotion = data.get("promotion")
    if promotion is not None:
        if not isinstance(promotion, dict):
            raise ValueError("promotion must be an object")
        names = promotion.get("ordered_account_names")
        if not isinstance(names, list) or not all(isinstance(x, str) and x for x in names):
            raise ValueError("promotion.ordered_account_names must be an array of strings")
        promotion_names = names
        start = parse_date(promotion.get("active_from"), "promotion.active_from")
        end = parse_date(promotion.get("active_to"), "promotion.active_to")
        if end < start:
            raise ValueError("promotion.active_to must not precede active_from")
        promotion_active = current is not None and start <= current <= end

    accepted, rejected = [], []
    for raw in accounts:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
            raise ValueError("each account needs a nonempty name")
        name = raw["name"].strip()
        unknowns, reasons, assumptions = [], [], []
        monthly = optional_nonnegative(raw, "monthly_fee", unknowns, name)
        overdraft = optional_nonnegative(raw, "overdraft_fee", unknowns, name)
        waiver = optional_nonnegative(raw, "fee_waiver_balance", unknowns, name)
        max_age = optional_nonnegative(raw, "max_company_age_years", unknowns, name)
        features = raw.get("features", [])
        if not isinstance(features, list) or not all(isinstance(x, str) for x in features):
            raise ValueError(f"{name}.features must be an array of strings")

        if zero_od:
            if overdraft == "MISSING" or overdraft is None:
                reasons.append("zero overdraft fee is required, but the overdraft fee is not documented as $0")
            elif overdraft != 0:
                reasons.append(f"overdraft fee is {display(overdraft)}, not $0")
        if max_age not in ("MISSING", None):
            if age is None:
                unknowns.append(f"{name}: company age is needed to test its age eligibility")
            elif age > max_age:
                reasons.append(f"company age exceeds the documented maximum of {display(max_age)} years")
        if max_waiver is not None:
            if waiver == "MISSING":
                unknowns.append(f"{name}: fee-waiver threshold is needed for the stated maximum")
            elif waiver is not None and waiver > max_waiver:
                reasons.append(f"fee-waiver threshold {display(waiver)} exceeds the stated maximum of {display(max_waiver)}")
        fee_waived = None
        if avoid_fee:
            if monthly == "MISSING":
                unknowns.append(f"{name}: monthly fee is needed to assess fee avoidance")
            elif monthly == 0:
                fee_waived = True
            elif waiver in ("MISSING", None):
                reasons.append("has a monthly fee without a documented usable fee waiver")
            elif balance is None:
                unknowns.append(f"{name}: reliable daily balance is needed to assess its fee waiver")
            elif balance < waiver:
                reasons.append(f"reliable daily balance is below its {display(waiver)} fee-waiver threshold")
            else:
                fee_waived = True
                assumptions.append("reliable_daily_balance remains at or above the stated waiver threshold")

        matched = [feature for feature in desired if feature in features]
        missing = [feature for feature in desired if feature not in features]
        candidate = {
            "name": name,
            "monthly_fee": None if monthly == "MISSING" else display(monthly),
            "overdraft_fee": None if overdraft == "MISSING" else display(overdraft),
            "fee_waiver_balance": None if waiver == "MISSING" else display(waiver),
            "fee_waived_under_profile": fee_waived,
            "matched_features": matched,
            "unmatched_requested_features": missing,
            "unknowns": unknowns,
            "assumptions": assumptions,
        }
        if reasons:
            candidate["rejection_reasons"] = reasons
            rejected.append(candidate)
        else:
            # Lower score is better; promotions only decide among eligible candidates.
            monthly_score = Decimal("999999") if monthly == "MISSING" else monthly
            waiver_score = Decimal("999999") if waiver in ("MISSING", None) else waiver
            promo_score = promotion_names.index(name) if promotion_active and name in promotion_names else len(promotion_names)
            candidate["_sort"] = (promo_score, -len(matched), monthly_score, waiver_score, name.lower())
            accepted.append(candidate)

    accepted.sort(key=lambda item: item["_sort"])
    for item in accepted:
        item.pop("_sort", None)
    return {
        "ok": True,
        "promotion_active": promotion_active,
        "recommendations": accepted,
        "rejected": rejected,
        "validation": {
            "hard_requirements_applied": {
                "zero_overdraft_fee_required": zero_od,
                "avoid_monthly_fee": avoid_fee,
                "maximum_waiver_balance": display(max_waiver),
            },
            "recommendation_available": bool(accepted),
            "note": "Rankings are advisory and require source verification before customer communication.",
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":"), sort_keys=True))
