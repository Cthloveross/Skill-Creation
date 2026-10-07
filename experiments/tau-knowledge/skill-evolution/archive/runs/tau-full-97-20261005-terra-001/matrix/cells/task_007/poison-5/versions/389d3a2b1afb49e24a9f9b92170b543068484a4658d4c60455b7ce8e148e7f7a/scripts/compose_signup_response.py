#!/usr/bin/env python3
"""Validate extracted promotion facts and compose a current-offer comparison.

Reads one JSON object from stdin and emits one JSON object to stdout. The caller
supplies facts extracted from task evidence; this script does not retrieve or
invent offer terms.
"""

import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def require_date(value, label):
    try:
        return date.fromisoformat(require_text(value, label))
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD") from exc


def require_notes(value, label):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty array of strings")
    return [require_text(item, f"{label} entry") for item in value]


def extract_dollar_amount(value, label):
    match = re.search(r"\$\s*([0-9][0-9,]*(?:\.\d+)?)", value)
    if not match:
        raise ValueError(f"{label} must include a dollar-denominated spend amount")
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"{label} contains an invalid dollar amount") from exc


def parse_offer(raw, label, as_of, need_fee=False, need_value=False):
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    start = require_date(raw.get("window_start"), f"{label}.window_start")
    end = require_date(raw.get("window_end"), f"{label}.window_end")
    if start > end:
        raise ValueError(f"{label} window_start cannot be after window_end")
    if not start <= as_of <= end:
        raise ValueError(f"{label} is not current on as_of_date")
    parsed = {
        "card": require_text(raw.get("card"), f"{label}.card"),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "bonus": require_text(raw.get("bonus"), f"{label}.bonus"),
        "required_spend": require_text(raw.get("required_spend"), f"{label}.required_spend"),
        "qualification_period": require_text(raw.get("qualification_period"), f"{label}.qualification_period"),
        "eligibility": require_notes(raw.get("eligibility"), f"{label}.eligibility"),
    }
    parsed["spend_amount"] = extract_dollar_amount(parsed["required_spend"], f"{label}.required_spend")
    if need_fee:
        parsed["fee_waiver"] = require_text(raw.get("fee_waiver"), f"{label}.fee_waiver")
    if need_value:
        parsed["documented_value"] = require_text(raw.get("documented_value"), f"{label}.documented_value")
    return parsed


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        as_of = require_date(payload.get("as_of_date"), "as_of_date")
        leading = parse_offer(payload.get("leading"), "leading", as_of, need_fee=True)
        alternative = parse_offer(
            payload.get("lower_spend_alternative"),
            "lower_spend_alternative",
            as_of,
            need_value=True,
        )
        if alternative["spend_amount"] >= leading["spend_amount"]:
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
            f"but it fits only if you can meet its stated spend requirement and eligibility conditions. "
            f"{alternative['card']} is the practical lower-spend current alternative when those conditions are a better fit."
        )
        json.dump(
            {
                "as_of_date": as_of.isoformat(),
                "message": message,
                "validation": {
                    "leading_current": True,
                    "alternative_current": True,
                    "alternative_lower_spend": True,
                },
            },
            sys.stdout,
            sort_keys=True,
        )
        sys.stdout.write("\n")
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
