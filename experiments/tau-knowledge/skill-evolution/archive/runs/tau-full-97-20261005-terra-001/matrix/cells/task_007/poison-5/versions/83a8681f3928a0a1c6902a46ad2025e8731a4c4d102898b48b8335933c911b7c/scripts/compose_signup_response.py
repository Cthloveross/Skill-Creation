#!/usr/bin/env python3
"""Validate extracted promotion facts and compose a direct current-offer comparison.

Reads one JSON object from stdin and emits one JSON object to stdout. Facts are
provided by the executor from supplied task evidence; this script never retrieves
or invents offer information.
"""

import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def iso_date(value, label):
    value = text(value, label)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD") from exc


def notes(value, label):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a nonempty array of strings")
    return [text(item, f"{label} entry") for item in value]


def spend_amount(value):
    """Parse the first explicitly dollar-denominated amount, if present."""
    found = re.search(r"\$\s*([0-9][0-9,]*(?:\.\d+)?)", value)
    if not found:
        return None
    try:
        return Decimal(found.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def offer(raw, label, as_of, needs_fee=False, needs_value=False):
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    start = iso_date(raw.get("window_start"), f"{label}.window_start")
    end = iso_date(raw.get("window_end"), f"{label}.window_end")
    if start > end:
        raise ValueError(f"{label} window_start cannot be after window_end")
    if not start <= as_of <= end:
        raise ValueError(f"{label} is not current on as_of_date")
    result = {
        "card": text(raw.get("card"), f"{label}.card"),
        "bonus": text(raw.get("bonus"), f"{label}.bonus"),
        "required_spend": text(raw.get("required_spend"), f"{label}.required_spend"),
        "qualification_period": text(raw.get("qualification_period"), f"{label}.qualification_period"),
        "eligibility": notes(raw.get("eligibility"), f"{label}.eligibility"),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
    }
    if needs_fee:
        result["fee_waiver"] = text(raw.get("fee_waiver"), f"{label}.fee_waiver")
    if needs_value:
        result["documented_value"] = text(raw.get("documented_value"), f"{label}.documented_value")
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        as_of = iso_date(payload.get("as_of_date"), "as_of_date")
        leading = offer(payload.get("leading"), "leading", as_of, needs_fee=True)
        alternative = offer(
            payload.get("lower_spend_alternative"),
            "lower_spend_alternative",
            as_of,
            needs_value=True,
        )

        leading_spend = spend_amount(leading["required_spend"])
        alternative_spend = spend_amount(alternative["required_spend"])
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
            f"but it is a fit only if you can meet its stated spend requirement and eligibility conditions. "
            f"{alternative['card']} is the practical lower-spend current alternative when those conditions are a better fit."
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
        raise SystemExit(2)


if __name__ == "__main__":
    main()
