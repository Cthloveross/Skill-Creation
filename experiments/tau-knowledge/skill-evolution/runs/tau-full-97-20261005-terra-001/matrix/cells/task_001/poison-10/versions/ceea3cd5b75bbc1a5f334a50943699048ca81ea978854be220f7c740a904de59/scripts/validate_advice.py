#!/usr/bin/env python3
"""Check whether a drafted card recommendation includes supplied required terms.

The caller supplies all terms from current task documents; this script has no
embedded product facts and does not determine whether the selected offer is correct.
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

DASHES = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-"})


def fail(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "missing": [], "checks": {}, "errors": errors}


def normal(value: str) -> str:
    return value.translate(DASHES).casefold()


def decimal(value: Any, label: str, errors: list[str], nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        errors.append(f"{label} must be numeric")
        return None
    try:
        output = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not output.is_finite() or output < 0:
        errors.append(f"{label} must be a finite number at least 0")
        return None
    return output


def any_phrase(text: str, phrases: Any) -> bool:
    return isinstance(phrases, list) and any(
        isinstance(phrase, str) and phrase and normal(phrase) in text for phrase in phrases
    )


def main(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return fail(["input must be a JSON object"])
    response = payload.get("response")
    selected = payload.get("selected_offer")
    app = payload.get("application_terms", {})
    errors: list[str] = []
    if not isinstance(response, str) or not response.strip():
        errors.append("response must be a nonempty string")
    if not isinstance(selected, dict):
        errors.append("selected_offer must be an object")
    if not isinstance(app, dict):
        errors.append("application_terms must be an object")
    if errors:
        return fail(errors)

    name = selected.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("selected_offer.name must be a nonempty string")
    rate = decimal(selected.get("cash_back_rate_percent"), "selected_offer.cash_back_rate_percent", errors)
    annual_fee = decimal(selected.get("annual_fee"), "selected_offer.annual_fee", errors)
    score = decimal(selected.get("min_credit_score"), "selected_offer.min_credit_score", errors, True)
    prerequisites = selected.get("confirmed_prerequisites", [])
    if not isinstance(prerequisites, list) or any(not isinstance(item, str) or not item for item in prerequisites):
        errors.append("selected_offer.confirmed_prerequisites must be an array of nonempty strings")
    if errors:
        return fail(errors)

    text = normal(response)
    rate_pattern = re.escape(format(rate.normalize(), "f").rstrip("0").rstrip(".")) + r"\s*%"
    fee_number = format(annual_fee.quantize(Decimal("0.01")), "f")
    fee_pattern = r"(?:\$?" + re.escape(fee_number) + r"|\$?" + re.escape(str(int(annual_fee))) + r")"
    checks = {
        "card_name": normal(name.strip()) in text,
        "cash_back_rate": bool(re.search(rate_pattern, text)),
        "annual_fee": bool(re.search(r"annual fee.{0,35}" + fee_pattern + "|" + fee_pattern + r".{0,35}annual fee", text)),
        "minimum_credit_score": score is None or bool(re.search(r"(?:credit score|score).{0,35}" + re.escape(str(int(score))), text)),
        "confirmed_prerequisites": all(normal(item) in text for item in prerequisites),
        "application_channel": any_phrase(text, app.get("channel_phrases", [])),
        "application_preparation": any_phrase(text, app.get("preparation_phrases", [])),
        "application_consent": any_phrase(text, app.get("consent_phrases", [])),
    }
    # Empty documented application categories are not requirements.
    for key, source_key in (("application_channel", "channel_phrases"), ("application_preparation", "preparation_phrases"), ("application_consent", "consent_phrases")):
        if app.get(source_key, []) == []:
            checks[key] = True
    missing = [key for key, present in checks.items() if not present]
    return {"ok": not missing, "missing": missing, "checks": checks, "errors": []}


def run() -> None:
    try:
        output = main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        output = fail([f"invalid JSON input: {exc.msg}"])
    except Exception as exc:
        output = fail([f"unable to process input: {exc}"])
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    run()
