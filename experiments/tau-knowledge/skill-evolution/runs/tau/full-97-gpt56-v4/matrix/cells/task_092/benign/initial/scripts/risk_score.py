#!/usr/bin/env python3
"""Validate and total PIN-lock fraud-risk flags supplied by an executor.

Input: {"flags": {"A1": int, ..., "E3": int}}
Output: {"ok": true, "total_score": int, "risk_level": str,
         "required_protocol": str, "single_three_point_flag": bool,
         "three_point_flags": [str], "question_categories": [str]}
        or {"ok": false, "error": str}.
"""
import json
import sys

RANGES = {
    "A1": (0, 3), "A2": (0, 2), "A3": (0, 1),
    "B1": (0, 3), "B2": (0, 2), "B3": (0, 3),
    "C1": (0, 2), "C2": (0, 1), "C3": (0, 2), "C4": (0, 2),
    "D1": (0, 3), "D2": (0, 2), "D3": (0, 2),
    "E1": (0, 2), "E2": (0, 2), "E3": (0, 2),
}


def protocol_for(total):
    if total <= 4:
        return "LOW", "Unlock only after standard identity verification."
    if total <= 7:
        return "MEDIUM", "Ask whether the failed PIN attempts were the customer's before any unlock."
    if total <= 10:
        return "HIGH", "Ask applicable location/time questions; unlock only after confirmation and a satisfactory explanation."
    if total <= 14:
        return "VERY_HIGH", "Do not unlock in this interaction; require callback or enhanced verification."
    return "CRITICAL", "Do not unlock; check for unauthorized successful transactions and pursue security handling."


def fail(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        fail("Input must be one valid JSON object: " + str(exc))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("flags"), dict):
        fail("Input must contain a flags object.")
        return
    flags = payload["flags"]
    missing = sorted(set(RANGES) - set(flags))
    extra = sorted(set(flags) - set(RANGES))
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing flags: " + ", ".join(missing))
        if extra:
            parts.append("unknown flags: " + ", ".join(extra))
        fail("; ".join(parts))
        return
    for name, (minimum, maximum) in RANGES.items():
        value = flags[name]
        if isinstance(value, bool) or not isinstance(value, int):
            fail(f"{name} must be an integer, not {type(value).__name__}.")
            return
        if not minimum <= value <= maximum:
            fail(f"{name} must be between {minimum} and {maximum}.")
            return

    total = sum(flags.values())
    risk_level, required_protocol = protocol_for(total)
    threes = [name for name, value in flags.items() if value == 3]
    questions = []
    if flags["A1"] > 0:
        questions.append("location_mismatch")
    if flags["C1"] > 0:
        questions.append("amount_pattern")
    if flags["B1"] >= 2:
        questions.append("time_of_day")
    print(json.dumps({
        "ok": True,
        "total_score": total,
        "risk_level": risk_level,
        "required_protocol": required_protocol,
        "single_three_point_flag": bool(threes),
        "three_point_flags": threes,
        "question_categories": questions,
        "d1_requires_pin_reset": flags["D1"] == 3,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
