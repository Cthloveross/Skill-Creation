#!/usr/bin/env python3
"""Filter and promotion-rank documented business account candidates.

Reads one JSON object from stdin and emits one JSON object on stdout.  This helper
performs only explicit comparisons; it does not discover account facts or initiate
any banking action.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def fail(message):
    raise ValueError(message)


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must be a non-empty ISO date or timestamp string")
    raw = value.strip()
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        fail(f"{field} must start with YYYY-MM-DD")


def decimal_value(value, field):
    if isinstance(value, bool):
        fail(f"{field} must be numeric, not boolean")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{field} must be numeric")


def active_priority(promotions, account_type, today):
    matches = []
    for index, promo in enumerate(promotions):
        if not isinstance(promo, dict):
            fail(f"promotions[{index}] must be an object")
        if promo.get("account_type") != account_type:
            continue
        start = parse_date(promo.get("start"), f"promotions[{index}].start")
        end = parse_date(promo.get("end"), f"promotions[{index}].end")
        if end < start:
            fail(f"promotions[{index}] ends before it starts")
        priority = promo.get("priority")
        if not isinstance(priority, list) or not all(isinstance(x, str) for x in priority):
            fail(f"promotions[{index}].priority must be a list of account names")
        if start <= today <= end:
            matches.append(priority)
    # Multiple simultaneous policies are ambiguous; avoid silently inventing precedence.
    if len(matches) > 1:
        fail(f"more than one active promotion applies to {account_type}")
    return matches[0] if matches else []


def assess(candidate, account_type, req):
    facts = candidate.get("facts")
    if not isinstance(facts, dict):
        fail("each candidate.facts must be an object")
    reasons, failures = [], []
    if account_type == "checking" and "mobile_deposit_daily_min" in req:
        needed = decimal_value(req["mobile_deposit_daily_min"], "checking.mobile_deposit_daily_min")
        if needed < 0:
            fail("checking.mobile_deposit_daily_min cannot be negative")
        if "mobile_deposit_daily_limit" not in facts:
            failures.append("mobile_deposit_daily_limit is undocumented")
        else:
            limit = decimal_value(facts["mobile_deposit_daily_limit"], "facts.mobile_deposit_daily_limit")
            if limit >= needed:
                reasons.append({"requirement": "mobile_deposit_daily_min", "status": "pass", "documented_limit": str(limit), "required_minimum": str(needed)})
            else:
                failures.append(f"mobile_deposit_daily_limit {limit} is below required minimum {needed}")
    if account_type == "savings" and req.get("same_day_ach_required") is True:
        if facts.get("same_day_ach") is True:
            reasons.append({"requirement": "same_day_ach_required", "status": "pass", "documented_value": True})
        else:
            failures.append("same_day_ach is not explicitly documented as available")
    elif account_type == "savings" and "same_day_ach_required" in req and req["same_day_ach_required"] is not False:
        fail("savings.same_day_ach_required must be boolean")
    return reasons, failures


def main(data):
    if not isinstance(data, dict):
        fail("top-level input must be an object")
    today = parse_date(data.get("as_of"), "as_of")
    requirements = data.get("requirements", {})
    candidates = data.get("candidates", [])
    promotions = data.get("promotions", [])
    if not isinstance(requirements, dict) or not isinstance(candidates, list) or not isinstance(promotions, list):
        fail("requirements must be an object; candidates and promotions must be lists")

    recommendations, unqualified = [], []
    for account_type in ("checking", "savings"):
        req = requirements.get(account_type, {})
        if not isinstance(req, dict):
            fail(f"requirements.{account_type} must be an object")
        qualified = []
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                fail(f"candidates[{index}] must be an object")
            if candidate.get("account_type") != account_type:
                continue
            name = candidate.get("name")
            if not isinstance(name, str) or not name.strip():
                fail(f"candidates[{index}].name must be a non-empty string")
            reasons, failures = assess(candidate, account_type, req)
            record = {"name": name, "account_type": account_type, "evidence": candidate.get("evidence", [])}
            if failures:
                record["failures"] = failures
                unqualified.append(record)
            else:
                record["reasons"] = reasons
                qualified.append(record)
        if not qualified:
            continue
        priority = active_priority(promotions, account_type, today)
        for record in qualified:
            record["promotion_rank"] = priority.index(record["name"]) + 1 if record["name"] in priority else None
        # Active priority ranks before unranked candidates; otherwise retain input order.
        qualified.sort(key=lambda r: (r["promotion_rank"] is None, r["promotion_rank"] or 0))
        recommendations.append(qualified[0])

    return {"as_of": today.isoformat(), "recommendations": recommendations, "unqualified": unqualified}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
