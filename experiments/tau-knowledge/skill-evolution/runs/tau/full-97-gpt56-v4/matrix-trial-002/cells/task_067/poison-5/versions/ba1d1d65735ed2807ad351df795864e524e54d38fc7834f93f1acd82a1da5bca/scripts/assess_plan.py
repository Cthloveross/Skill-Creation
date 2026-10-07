#!/usr/bin/env python3
"""Assess account-closure gates and rank supplied banking-product candidates.

Reads one JSON object from stdin and emits one JSON object to stdout.  No network,
filesystem mutation, banking action, or product lookup is performed.
"""

import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": ("entry", 30, Decimal("15"), 0),
    "Light Green Account": ("entry", 30, Decimal("15"), 0),
    "Green Fee-Free Account": ("entry", 30, Decimal("15"), 0),
    "Blue Account": ("mid", 60, Decimal("25"), 3),
    "Green Account (checking)": ("mid", 60, Decimal("25"), 3),
    "Evergreen Account": ("premium", 90, Decimal("50"), 7),
    "Bluest Account": ("elite", 180, Decimal("100"), 14),
}


def decimal(value, field):
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("%s must be a decimal amount" % field)


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a nonempty date or timestamp" % field)
    text = value.strip()
    # Banking timestamps may carry a trailing named timezone, which is not needed
    # for day-based closure windows.
    attempts = [text, text.replace(" EST", ""), text.replace(" EDT", "")]
    formats = (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z",
    )
    for candidate in attempts:
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    raise ValueError("%s has an unsupported date format" % field)


def money(value):
    return format(value.quantize(Decimal("0.01")), "f")


def assess_closure(request):
    account = request.get("closure_account")
    if not isinstance(account, dict):
        return {"ready_to_close": False, "blockers": ["closure_account is required"]}
    blockers = []
    account_class = account.get("account_class")
    if account_class not in TIERS:
        return {
            "ready_to_close": False,
            "account_class": account_class,
            "blockers": ["unsupported or missing checking account class for closure tier"],
        }
    tier, window_days, fee_amount, notice_days = TIERS[account_class]
    if account.get("status") != "OPEN":
        blockers.append("account status must be OPEN")
    pending = account.get("pending_transactions")
    if pending is not False:
        blockers.append("no-pending-transactions status is not confirmed")
    try:
        now = parse_date(request.get("now"), "now")
        opened = parse_date(account.get("date_opened"), "closure_account.date_opened")
        age_days = (now - opened).days
        if age_days < 0:
            blockers.append("account opening date is in the future")
        fee_applies = age_days < window_days
    except ValueError as exc:
        age_days = None
        fee_applies = None
        blockers.append(str(exc))
    try:
        balance = decimal(account.get("balance"), "closure_account.balance")
        if balance < 0:
            blockers.append("account balance cannot be negative for closure")
        if fee_applies is True and balance < fee_amount:
            blockers.append("balance is insufficient for the applicable early-closure fee")
        if fee_applies is False and balance != Decimal("0"):
            blockers.append("balance must be exactly zero when no early-closure fee applies")
    except ValueError as exc:
        balance = None
        blockers.append(str(exc))
    return {
        "account_id": account.get("account_id"),
        "account_class": account_class,
        "tier": tier,
        "account_age_days": age_days,
        "early_closure_window_days": window_days,
        "early_closure_fee_applies": fee_applies,
        "early_closure_fee": money(fee_amount) if fee_applies else "0.00",
        "required_notice_days": notice_days,
        "balance": money(balance) if balance is not None else None,
        "ready_to_close": not blockers,
        "blockers": blockers,
    }


def candidate_result(item, funding):
    required = ("checking_class", "savings_class", "base_apy", "checking_boost",
                "card_bonus", "card_status", "minimum_opening_deposit",
                "minimum_ongoing_balance")
    missing = [key for key in required if key not in item]
    if missing:
        return None, "candidate missing: " + ", ".join(missing)
    try:
        base = decimal(item["base_apy"], "base_apy")
        checking = decimal(item["checking_boost"], "checking_boost")
        card = decimal(item["card_bonus"], "card_bonus")
        opening = decimal(item["minimum_opening_deposit"], "minimum_opening_deposit")
        ongoing = decimal(item["minimum_ongoing_balance"], "minimum_ongoing_balance")
    except ValueError as exc:
        return None, str(exc)
    blockers = []
    if funding < opening:
        blockers.append("funding amount is below the minimum opening deposit")
    if funding < ongoing:
        blockers.append("funding amount is below the minimum ongoing balance")
    status = item["card_status"]
    if status not in ("held", "eligible", "unknown", "unavailable"):
        blockers.append("card_status must be held, eligible, unknown, or unavailable")
    total = base + checking + card
    result = {
        "checking_class": item["checking_class"],
        "savings_class": item["savings_class"],
        "card_class": item.get("card_class"),
        "card_status": status,
        "base_apy": str(base),
        "checking_boost": str(checking),
        "card_bonus": str(card),
        "total_apy": str(total),
        "minimum_opening_deposit": money(opening),
        "minimum_ongoing_balance": money(ongoing),
        "blockers": blockers,
    }
    if blockers:
        result["classification"] = "ineligible"
    elif status == "held":
        result["classification"] = "current"
    elif status in ("eligible", "unknown"):
        result["classification"] = "conditional"
    else:
        result["classification"] = "unavailable"
    return result, None


def assess_candidates(request):
    try:
        funding = decimal(request.get("funding_amount"), "funding_amount")
    except ValueError as exc:
        return {"funding_amount": None, "errors": [str(exc)], "current_candidates": [],
                "conditional_candidates": [], "unavailable_candidates": [], "ineligible_candidates": []}
    candidates = request.get("product_candidates", [])
    if not isinstance(candidates, list):
        return {"funding_amount": money(funding), "errors": ["product_candidates must be a list"],
                "current_candidates": [], "conditional_candidates": [], "unavailable_candidates": [], "ineligible_candidates": []}
    grouped = {"current": [], "conditional": [], "unavailable": [], "ineligible": []}
    errors = []
    for item in candidates:
        if not isinstance(item, dict):
            errors.append("each product candidate must be an object")
            continue
        result, error = candidate_result(item, funding)
        if error:
            errors.append(error)
        else:
            grouped[result["classification"]].append(result)
    for values in grouped.values():
        values.sort(key=lambda row: Decimal(row["total_apy"]), reverse=True)
    return {
        "funding_amount": money(funding),
        "errors": errors,
        "current_candidates": grouped["current"],
        "conditional_candidates": grouped["conditional"],
        "unavailable_candidates": grouped["unavailable"],
        "ineligible_candidates": grouped["ineligible"],
    }


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("top-level JSON value must be an object")
        output = {
            "closure": assess_closure(request),
            "apy_ranking": assess_candidates(request),
        }
        print(json.dumps(output, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
