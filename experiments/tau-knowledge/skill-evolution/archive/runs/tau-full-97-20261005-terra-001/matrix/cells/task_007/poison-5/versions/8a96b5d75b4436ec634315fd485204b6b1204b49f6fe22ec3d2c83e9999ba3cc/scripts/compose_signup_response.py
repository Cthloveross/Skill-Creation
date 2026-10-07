#!/usr/bin/env python3
"""Validate extracted current-offer facts and compose a direct comparison.

Reads one JSON object from stdin and writes one JSON object to stdout. The caller
must extract all facts from the task's supplied evidence; this script never
invents offer values.
"""

import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD") from exc


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def require_notes(value, label):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty array of strings")
    return [require_text(note, f"{label} entry") for note in value]


def dollars_from_text(value):
    """Return a documented dollar amount when a simple currency amount is present."""
    match = re.search(r"\$\s*([0-9][0-9,]*(?:\.\d+)?)", value)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def normalize_offer(raw, label, as_of, require_fee_waiver=False, require_value=False):
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    offer = {
        "card": require_text(raw.get("card"), f"{label}.card"),
        "bonus": require_text(raw.get("bonus"), f"{label}.bonus"),
        "required_spend": require_text(raw.get("required_spend"), f"{label}.required_spend"),
        "qualification_period": require_text(
            raw.get("qualification_period"), f"{label}.qualification_period"
        ),
        "eligibility": require_notes(raw.get("eligibility"), f"{label}.eligibility"),
    }
    start_text = require_text(raw.get("window_start"), f"{label}.window_start")
    end_text = require_text(raw.get("window_end"), f"{label}.window_end")
    start = parse_date(start_text, f"{label}.window_start")
    end = parse_date(end_text, f"{label}.window_end")
    if start > end:
        raise ValueError(f"{label} window_start cannot be after window_end")
    if not start <= as_of <= end:
        raise ValueError(f"{label} is not current on as_of_date")
    offer["window_start"] = start.isoformat()
    offer["window_end"] = end.isoformat()
    if require_fee_waiver:
        offer["fee_waiver"] = require_text(raw.get("fee_waiver"), f"{label}.fee_waiver")
    if require_value:
        offer["documented_value"] = require_text(
            raw.get("documented_value"), f"{label}.documented_value"
        )
    return offer


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        as_of = parse_date(payload.get("as_of_date"), "as_of_date")
        leading = normalize_offer(payload.get("leading"), "leading", as_of, require_fee_waiver=True)
        alternative = normalize_offer(
            payload.get("lower_spend_alternative"),
            "lower_spend_alternative",
            as_of,
            require_value=True,
        )

        leading_spend = dollars_from_text(leading["required_spend"])
        alternative_spend = dollars_from_text(alternative["required_spend"])
        lower_spend = True
        if leading_spend is not None and alternative_spend is not None:
            lower_spend = alternative_spend < leading_spend
            if not lower_spend:
                raise ValueError("lower_spend_alternative must require less documented spend than leading")

        message = (
            f"As of {as_of.isoformat()}, the highest documented current sign-up incentive is "
            f"{leading['card']}.\n\n"
            f"{leading['card']}\n"
            f"- Bonus: {leading['bonus']}, plus {leading['fee_waiver']}.\n"
            f"- To qualify: {leading['required_spend']} within {leading['qualification_period']}.\n"
            f"- Campaign: {leading['window_start']} through {leading['window_end']}.\n"
            f"- Important eligibility: {'; '.join(leading['eligibility'])}.\n\n"
            f"Lower-spend current alternative: {alternative['card']}\n"
            f"- Bonus: {alternative['bonus']} ({alternative['documented_value']}).\n"
            f"- To qualify: {alternative['required_spend']} in {alternative['qualification_period']}.\n"
            f"- Available through: {alternative['window_end']}.\n"
            f"- Eligibility: {'; '.join(alternative['eligibility'])}.\n\n"
            f"Bottom line: {leading['card']} has the largest documented current incentive, "
            f"but it is practical only if you can meet its stated spend requirement and eligibility conditions. "
            f"{alternative['card']} is the lower-spend current option if those conditions are a better fit."
        )
        json.dump(
            {
                "as_of_date": as_of.isoformat(),
                "message": message,
                "validation": {
                    "leading_current": True,
                    "alternative_current": True,
                    "alternative_lower_spend": lower_spend,
                },
            },
            sys.stdout,
            sort_keys=True,
        )
        sys.stdout.write("\n")
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
