#!/usr/bin/env python3
"""Assess banking workflow prerequisites from caller-supplied JSON.

This program performs no I/O other than JSON stdin/stdout and never takes bank
actions. Monetary values are parsed with Decimal so balances are not compared
with binary floating-point arithmetic.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

CLOSURE_TIERS = {
    "Light Blue Account": (15, 30, 0),
    "Light Green Account": (15, 30, 0),
    "Green Fee-Free Account": (15, 30, 0),
    "Blue Account": (25, 60, 3),
    "Green Account (checking)": (25, 60, 3),
    "Evergreen Account": (50, 90, 7),
    "Bluest Account": (100, 180, 14),
}


def parse_date(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for parser in (
        lambda: datetime.fromisoformat(text.replace("Z", "+00:00")).date(),
        lambda: datetime.strptime(text, "%m/%d/%Y").date(),
        lambda: datetime.strptime(text, "%Y-%m-%d").date(),
    ):
        try:
            return parser()
        except ValueError:
            pass
    return None


def money(value: Any) -> Optional[Decimal]:
    try:
        if isinstance(value, bool) or value is None:
            return None
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def result(eligible: Optional[bool], blockers: List[str], **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"eligible": eligible, "blockers": blockers}
    out.update(extra)
    return out


def assess_closure(payload: Any, today: Optional[date]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return result(None, ["closure facts were not supplied"])
    account = payload.get("account")
    if not isinstance(account, dict):
        return result(None, ["closure account facts were not supplied"])

    blockers: List[str] = []
    account_class = account.get("account_class")
    tier = CLOSURE_TIERS.get(account_class)
    if tier is None:
        blockers.append("unsupported or missing checking account class for closure-tier assessment")
        return result(None, blockers)

    fee, early_days, notice_days = tier
    status = str(account.get("status", "")).upper()
    if status != "OPEN":
        blockers.append("account status is not confirmed as OPEN")

    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        blockers.append("transaction history was not supplied")
    elif any(isinstance(tx, dict) and str(tx.get("status", "")).lower() == "pending" for tx in transactions):
        blockers.append("account has pending transactions")

    opened = parse_date(account.get("date_opened"))
    if today is None:
        blockers.append("current date is invalid or missing")
    if opened is None:
        blockers.append("account opening date is invalid or missing")
    if today is not None and opened is not None and opened > today:
        blockers.append("account opening date is in the future")

    balance = money(account.get("balance"))
    if balance is None:
        blockers.append("current account balance is invalid or missing")

    elapsed: Optional[int] = None
    early: Optional[bool] = None
    fee_due: Optional[Decimal] = None
    if today is not None and opened is not None and opened <= today:
        elapsed = (today - opened).days
        early = elapsed < early_days
        fee_due = Decimal(fee if early else 0)
        if balance is not None:
            if early and balance < fee_due:
                blockers.append("balance is insufficient for the applicable early-closure fee")
            elif not early and balance != Decimal("0"):
                blockers.append("balance must be exactly zero when no early-closure fee applies")

    eligible: Optional[bool] = False if blockers else True
    if any("invalid or missing" in item or "not supplied" in item for item in blockers):
        eligible = None
    return result(
        eligible,
        blockers,
        elapsed_days=elapsed,
        early_closure=early,
        early_closure_fee=str(fee_due) if fee_due is not None else None,
        notice_days=notice_days,
    )


def assess_checking_opening(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return result(None, ["checking-opening eligibility facts were not supplied"])
    required = [
        ("verified", True, "customer is not confirmed verified"),
        ("age_years", None, "customer age is missing"),
        ("existing_checking_count", None, "existing checking-account count is missing"),
        ("closed_for_cause_past_6_months", False, "closed-for-cause history is not clear"),
        ("account_class_confirmed", True, "exact checking account class is not confirmed"),
    ]
    blockers: List[str] = []
    unknown = False
    for field, expected, message in required:
        value = payload.get(field)
        if value is None:
            blockers.append(message)
            unknown = True
        elif expected is not None and value != expected:
            blockers.append(message)
    age = payload.get("age_years")
    count = payload.get("existing_checking_count")
    if age is not None:
        try:
            if int(age) < 18:
                blockers.append("customer is under age 18")
        except (TypeError, ValueError):
            blockers.append("customer age is invalid")
            unknown = True
    if count is not None:
        try:
            if int(count) >= 4:
                blockers.append("opening would exceed the four personal-checking-account limit")
        except (TypeError, ValueError):
            blockers.append("existing checking-account count is invalid")
            unknown = True
    return result(None if unknown else not blockers, blockers)


def assess_savings_opening(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return result(None, ["savings-opening eligibility facts were not supplied"])
    blockers: List[str] = []
    unknown = False
    checks: List[Tuple[str, Any, str]] = [
        ("verified", True, "customer is not confirmed verified"),
        ("has_collections", False, "collections status is not clear or accounts are in collections"),
        ("has_negative_balance", False, "negative-balance status is not clear or an account has a negative balance"),
        ("account_class_confirmed", True, "exact savings account class is not confirmed"),
    ]
    for field, expected, message in checks:
        value = payload.get(field)
        if value is None:
            blockers.append(message)
            unknown = True
        elif value != expected:
            blockers.append(message)
    tenure = payload.get("active_checking_tenure_days")
    if tenure is None:
        blockers.append("active checking-account tenure is missing")
        unknown = True
    else:
        try:
            if int(tenure) < 14:
                blockers.append("no active checking account has been held for at least 14 days")
        except (TypeError, ValueError):
            blockers.append("active checking-account tenure is invalid")
            unknown = True
    count = payload.get("existing_savings_count")
    if count is None:
        blockers.append("existing savings-account count is missing")
        unknown = True
    else:
        try:
            if int(count) >= 5:
                blockers.append("customer has reached the five personal-savings-account limit")
        except (TypeError, ValueError):
            blockers.append("existing savings-account count is invalid")
            unknown = True
    return result(None if unknown else not blockers, blockers)


def rank_savings(candidates: Any, planned: Any) -> Dict[str, Any]:
    balance = money(planned)
    if not isinstance(candidates, list):
        return {"planned_savings_balance": None, "eligible_candidates": [], "blockers": ["savings candidates were not supplied"]}
    if balance is None or balance < 0:
        return {"planned_savings_balance": None, "eligible_candidates": [], "blockers": ["planned savings balance is invalid or missing"]}
    eligible: List[Dict[str, Any]] = []
    rejected: List[Dict[str, str]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            rejected.append({"account_class": "unknown", "reason": "candidate is not an object"})
            continue
        opening = money(candidate.get("opening_min"))
        ongoing = money(candidate.get("ongoing_min"))
        apy = money(candidate.get("apy_pct"))
        label = str(candidate.get("account_class", "unknown"))
        if opening is None or ongoing is None or apy is None:
            rejected.append({"account_class": label, "reason": "candidate is missing a numeric APY or balance threshold"})
        elif balance >= opening and balance >= ongoing:
            eligible.append({"account_class": label, "apy_pct": str(apy), "opening_min": str(opening), "ongoing_min": str(ongoing)})
        else:
            rejected.append({"account_class": label, "reason": "planned balance does not meet both opening and ongoing thresholds"})
    eligible.sort(key=lambda item: Decimal(item["apy_pct"]), reverse=True)
    return {
        "planned_savings_balance": str(balance),
        "eligible_candidates": eligible,
        "recommended_account_class": eligible[0]["account_class"] if eligible else None,
        "rejected_candidates": rejected,
        "blockers": [] if eligible else ["no supplied savings candidate fits the planned balance"],
    }


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        json.dump({"error": "invalid JSON input", "detail": str(exc)}, sys.stdout)
        return
    if not isinstance(data, dict):
        json.dump({"error": "input must be a JSON object"}, sys.stdout)
        return
    today = parse_date(data.get("now"))
    output = {
        "closure": assess_closure(data.get("closure"), today),
        "checking_opening": assess_checking_opening(data.get("checking_opening")),
        "savings_opening": assess_savings_opening(data.get("savings_opening")),
        "savings_ranking": rank_savings(data.get("savings_candidates"), data.get("planned_savings_balance")),
    }
    json.dump(output, sys.stdout, sort_keys=True)


if __name__ == "__main__":
    main()
