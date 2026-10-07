#!/usr/bin/env python3
"""Screen a supplied business-checking catalog without embedded product facts.
Reads one JSON object from stdin and emits one JSON object to stdout.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def number(value, label, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a nonnegative number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a nonnegative number")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be a nonnegative number")
    return result


def fmt(value):
    return None if value is None else format(value, "f")


def field(obj, key, label, unknowns):
    if key not in obj:
        unknowns.append(f"{label}: {key} is not documented")
        return "MISSING"
    return number(obj[key], f"{label}.{key}", nullable=True)


def iso_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label} must be YYYY-MM-DD")


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    accounts = data.get("accounts")
    profile = data.get("profile", {})
    req = data.get("requirements", {})
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("accounts must be a nonempty array")
    if not isinstance(profile, dict) or not isinstance(req, dict):
        raise ValueError("profile and requirements must be objects")

    age = number(profile["company_age_years"], "profile.company_age_years") if profile.get("company_age_years") is not None else None
    balance = number(profile["reliable_daily_balance"], "profile.reliable_daily_balance") if profile.get("reliable_daily_balance") is not None else None
    max_waiver = number(req["maximum_waiver_balance"], "requirements.maximum_waiver_balance") if req.get("maximum_waiver_balance") is not None else None
    zero_od = req.get("zero_overdraft_fee_required", False)
    avoid_fee = req.get("avoid_monthly_fee", False)
    wanted = req.get("desired_features", [])
    if not isinstance(zero_od, bool) or not isinstance(avoid_fee, bool):
        raise ValueError("boolean requirement fields must be true or false")
    if not isinstance(wanted, list) or not all(isinstance(x, str) and x for x in wanted):
        raise ValueError("requirements.desired_features must be an array of nonempty strings")

    promotion_active, priorities = False, []
    if data.get("promotion") is not None:
        promo = data["promotion"]
        if not isinstance(promo, dict):
            raise ValueError("promotion must be an object")
        priorities = promo.get("ordered_account_names")
        if not isinstance(priorities, list) or not all(isinstance(x, str) and x for x in priorities):
            raise ValueError("promotion.ordered_account_names must be an array of strings")
        if data.get("current_date") is not None:
            today = iso_date(data["current_date"], "current_date")
            start = iso_date(promo.get("active_from"), "promotion.active_from")
            end = iso_date(promo.get("active_to"), "promotion.active_to")
            if end < start:
                raise ValueError("promotion.active_to must not precede active_from")
            promotion_active = start <= today <= end

    accepted, rejected = [], []
    for raw in accounts:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
            raise ValueError("each account needs a nonempty name")
        name = raw["name"].strip()
        unknowns, reasons, assumptions = [], [], []
        monthly = field(raw, "monthly_fee", name, unknowns)
        overdraft = field(raw, "overdraft_fee", name, unknowns)
        waiver = field(raw, "fee_waiver_balance", name, unknowns)
        max_age = field(raw, "max_company_age_years", name, unknowns)
        features = raw.get("features", [])
        if not isinstance(features, list) or not all(isinstance(x, str) for x in features):
            raise ValueError(f"{name}.features must be an array of strings")

        if zero_od:
            if overdraft in ("MISSING", None):
                reasons.append("zero overdraft fee is required, but $0 is not documented")
            elif overdraft != 0:
                reasons.append(f"overdraft fee is {fmt(overdraft)}, not $0")
        if max_age not in ("MISSING", None):
            if age is None:
                unknowns.append(f"{name}: company age is needed to test eligibility")
            elif age > max_age:
                reasons.append(f"company age exceeds the maximum of {fmt(max_age)} years")
        if max_waiver is not None:
            if waiver == "MISSING":
                unknowns.append(f"{name}: fee-waiver threshold is needed for the stated maximum")
            elif waiver is not None and waiver > max_waiver:
                reasons.append(f"fee-waiver threshold {fmt(waiver)} exceeds stated maximum {fmt(max_waiver)}")

        fee_waived = None
        if avoid_fee:
            if monthly == "MISSING":
                unknowns.append(f"{name}: monthly fee is needed to assess fee avoidance")
            elif monthly == 0:
                fee_waived = True
            elif waiver in ("MISSING", None):
                reasons.append("has a monthly fee without a documented usable waiver")
            elif balance is None:
                unknowns.append(f"{name}: reliable daily balance is needed to assess waiver")
            elif balance < waiver:
                reasons.append(f"reliable daily balance is below the {fmt(waiver)} waiver threshold")
            else:
                fee_waived = True
                assumptions.append("reliable_daily_balance remains at or above the waiver threshold")

        matched = [x for x in wanted if x in features]
        item = {"name": name, "monthly_fee": None if monthly == "MISSING" else fmt(monthly),
                "overdraft_fee": None if overdraft == "MISSING" else fmt(overdraft),
                "fee_waiver_balance": None if waiver == "MISSING" else fmt(waiver),
                "fee_waived_under_profile": fee_waived, "matched_features": matched,
                "unmatched_requested_features": [x for x in wanted if x not in features],
                "unknowns": unknowns, "assumptions": assumptions}
        if reasons:
            item["rejection_reasons"] = reasons
            rejected.append(item)
        elif unknowns:
            item["decision_status"] = "insufficient_documentation"
            rejected.append(item)
        else:
            priority = priorities.index(name) if promotion_active and name in priorities else len(priorities)
            item["_sort"] = (priority, -len(matched), monthly if monthly is not None else Decimal("999999"), name.lower())
            accepted.append(item)

    accepted.sort(key=lambda x: x.pop("_sort"))
    return {"ok": True, "promotion_active": promotion_active, "recommendations": accepted,
            "rejected": rejected,
            "validation": {"recommendation_available": bool(accepted),
                           "hard_requirements_applied": {"zero_overdraft_fee_required": zero_od,
                               "avoid_monthly_fee": avoid_fee, "maximum_waiver_balance": fmt(max_waiver)},
                           "note": "Results are advisory and require source verification."}}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":"), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":"), sort_keys=True))
