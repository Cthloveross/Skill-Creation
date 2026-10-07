#!/usr/bin/env python3
"""Deterministically assess referral-window and annual-cap availability.

Reads a JSON object from stdin; writes one JSON object to stdout. No network or
bank actions are performed. See SKILL.md for the schema.
"""

import json
import sys
from datetime import date, datetime, time, timedelta, timezone


def parse_datetime(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonempty ISO date or timestamp")
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time.min).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(f"invalid {field_name}: {value!r}") from exc


def iso_utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def bool_state(value):
    if value is True:
        return True
    if value is False:
        return False
    return None


def norm(value):
    return str(value or "").strip().casefold()


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_datetime(payload.get("as_of"), "as_of")
    raw_referrals = payload.get("referrals")
    raw_programs = payload.get("programs")
    if not isinstance(raw_referrals, list) or not isinstance(raw_programs, list):
        raise ValueError("referrals and programs must be arrays")

    referrals = []
    for index, item in enumerate(raw_referrals):
        if not isinstance(item, dict):
            raise ValueError(f"referrals[{index}] must be an object")
        when = parse_datetime(item.get("date"), f"referrals[{index}].date")
        referrals.append({
            "when": when,
            "status": norm(item.get("status")),
            "account_type": str(item.get("account_type") or "").strip(),
        })

    programs = {}
    for index, item in enumerate(raw_programs):
        if not isinstance(item, dict) or not str(item.get("account_type") or "").strip():
            raise ValueError(f"programs[{index}].account_type is required")
        key = norm(item["account_type"])
        try:
            annual_cap = int(item["annual_cap"])
            tenure_days = int(item["min_referrer_tenure_days"])
            bonus = float(item["referrer_bonus"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"programs[{index}] requires numeric referrer_bonus, annual_cap, and min_referrer_tenure_days") from exc
        if annual_cap < 0 or tenure_days < 0 or bonus < 0:
            raise ValueError(f"programs[{index}] numeric values cannot be negative")
        programs[key] = {
            "account_type": str(item["account_type"]).strip(),
            "annual_cap": annual_cap,
            "min_referrer_tenure_days": tenure_days,
            "referrer_bonus": bonus,
        }

    completed = [r for r in referrals if r["status"] == "complete" and r["when"] <= as_of]
    cutoff = as_of - timedelta(days=9)
    in_window = [r for r in completed if r["when"] >= cutoff]
    in_window.sort(key=lambda r: r["when"])
    remaining_slots = max(0, 2 - len(in_window))
    next_slot_after = None
    if len(in_window) >= 2:
        # The cutoff is inclusive; capacity returns immediately after this instant.
        next_slot_after = iso_utc(in_window[0]["when"] + timedelta(days=9))

    referrer = payload.get("referrer") or {}
    if not isinstance(referrer, dict):
        raise ValueError("referrer must be an object when supplied")
    referrer_blockers = []
    for field, label in (
        ("identity_verified", "Identity has not been verified"),
        ("authority_confirmed", "Account-holder authority has not been confirmed"),
        ("current_checking_confirmed", "Current eligible checking status has not been confirmed"),
    ):
        state = bool_state(referrer.get(field))
        if state is not True:
            referrer_blockers.append({"key": field, "label": label, "status": state})

    earliest = referrer.get("earliest_checking_opened_at")
    earliest_dt = parse_datetime(earliest, "referrer.earliest_checking_opened_at") if earliest else None
    if earliest_dt is None:
        referrer_blockers.append({"key": "earliest_checking_opened_at", "label": "Earliest checking opening date has not been confirmed", "status": None})
    tenure_days = None if earliest_dt is None else max(0, int((as_of - earliest_dt).total_seconds() // 86400))

    program_summaries = {}
    for key, program in programs.items():
        annual_complete = sum(
            1 for r in completed
            if norm(r["account_type"]) == key and r["when"].year == as_of.year
        )
        program_summaries[key] = {
            "account_type": program["account_type"],
            "referrer_bonus": program["referrer_bonus"],
            "completed_in_current_year": annual_complete,
            "annual_cap": program["annual_cap"],
            "annual_slots_remaining": max(0, program["annual_cap"] - annual_complete),
            "min_referrer_tenure_days": program["min_referrer_tenure_days"],
            "referrer_tenure_days": tenure_days,
            "tenure_met": None if tenure_days is None else tenure_days >= program["min_referrer_tenure_days"],
        }

    evaluated = []
    candidates = payload.get("candidates") or []
    if not isinstance(candidates, list):
        raise ValueError("candidates must be an array when supplied")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        account_key = norm(candidate.get("account_type"))
        program = program_summaries.get(account_key)
        blockers = list(referrer_blockers)
        if program is None:
            blockers.append({"key": "supported_program", "label": "No supported program definition was supplied for this account type", "status": None})
        else:
            if remaining_slots <= 0:
                blockers.append({"key": "rolling_window", "label": "The two-bonus rolling nine-day limit is reached", "status": False})
            if program["annual_slots_remaining"] <= 0:
                blockers.append({"key": "annual_cap", "label": "The program's calendar-year cap is reached", "status": False})
            if program["tenure_met"] is not True:
                blockers.append({"key": "program_tenure", "label": "The program tenure threshold is not confirmed as met", "status": program["tenure_met"]})
        requirements = candidate.get("requirements") or []
        if not isinstance(requirements, list):
            raise ValueError(f"candidates[{index}].requirements must be an array")
        for req_index, req in enumerate(requirements):
            if not isinstance(req, dict) or not req.get("key") or not req.get("label"):
                raise ValueError(f"candidates[{index}].requirements[{req_index}] needs key and label")
            state = bool_state(req.get("status"))
            if state is not True:
                blockers.append({"key": str(req["key"]), "label": str(req["label"]), "status": state})
        evaluated.append({
            "name": str(candidate.get("name") or "Unnamed candidate"),
            "account_type": str(candidate.get("account_type") or ""),
            "referrer_bonus": None if program is None else program["referrer_bonus"],
            "ready_to_recommend": len(blockers) == 0,
            "blockers": blockers,
        })

    ready = sorted((c for c in evaluated if c["ready_to_recommend"]), key=lambda c: (-c["referrer_bonus"], c["name"]))
    conditional = sorted((c for c in evaluated if not c["ready_to_recommend"]), key=lambda c: (-(c["referrer_bonus"] or 0), c["name"]))
    result = {
        "ok": True,
        "as_of": iso_utc(as_of),
        "rolling_window": {
            "successful_complete_count": len(in_window),
            "cap": 2,
            "remaining_slots": remaining_slots,
            "included_completed_dates": [iso_utc(r["when"]) for r in in_window],
            "next_slot_after": next_slot_after,
        },
        "referrer_tenure_days": tenure_days,
        "referrer_blockers": referrer_blockers,
        "programs": list(program_summaries.values()),
        "ready_candidates": ready,
        "conditional_candidates": conditional,
    }
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
