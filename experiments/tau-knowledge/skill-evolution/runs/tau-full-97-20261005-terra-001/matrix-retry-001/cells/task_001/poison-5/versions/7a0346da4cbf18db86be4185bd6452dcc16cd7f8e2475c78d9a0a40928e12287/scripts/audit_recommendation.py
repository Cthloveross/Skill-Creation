#!/usr/bin/env python3
"""Check whether proposed recommendation text covers selected verified facts.

Reads the JSON schema documented in SKILL.md and emits
{"ok": boolean, "missing": ["description", ...]}. It is a coverage aid only.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation


def amount(value, label, missing):
    if value is None or isinstance(value, bool):
        missing.append(f"{label} must be numeric")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        missing.append(f"{label} must be numeric")
        return None
    if not result.is_finite() or result < 0:
        missing.append(f"{label} must be a nonnegative finite number")
        return None
    return result


def numeric_pattern(value):
    text = format(value.normalize(), "f")
    if "." not in text:
        return re.escape(text) + r"(?:\.0+)?"
    whole, fraction = text.split(".", 1)
    fraction = fraction.rstrip("0")
    return re.escape(whole) if not fraction else re.escape(whole) + r"\." + re.escape(fraction) + r"0*"


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "missing": [f"invalid JSON: {exc.msg}"]}))
        return
    if not isinstance(data, dict) or not isinstance(data.get("card"), dict):
        print(json.dumps({"ok": False, "missing": ["card must be an object"]}))
        return
    response, card, missing = data.get("response"), data["card"], []
    if not isinstance(response, str) or not response.strip():
        print(json.dumps({"ok": False, "missing": ["response must be a nonempty string"]}))
        return
    text = response.casefold()
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        missing.append("valid card name input")
    elif name.casefold() not in text:
        missing.append("recommended card name")
    rate = amount(card.get("cash_back_rate_percent"), "cash_back_rate_percent", missing)
    fee = amount(card.get("annual_fee"), "annual_fee", missing)
    if rate is not None and not re.search(numeric_pattern(rate) + r"\s*%", text):
        missing.append("documented cash-back rate")
    if card.get("cash_back_scope") == "flat_all_eligible" and not re.search(r"(?:all\s+eligible\s+purchases|all\s+purchases|flat(?:-rate)?|everyday)", text):
        missing.append("flat all-purchases scope")
    if fee is not None:
        if fee == 0:
            fee_ok = re.search(r"(?:no|\$?0(?:\.0+)?)\s*(?:card\s*)?annual\s*fee|annual\s*(?:card\s*)?fee\s*(?:of\s*)?(?:no|\$?0(?:\.0+)?)", text)
        else:
            fee_ok = re.search(r"\$?" + numeric_pattern(fee) + r"\s*(?:annual\s*)?(?:card\s*)?fee", text)
        if not fee_ok:
            missing.append("documented annual card fee")
    subscription = card.get("required_subscription")
    if subscription is not None:
        if not isinstance(subscription, str) or not subscription.strip():
            missing.append("valid required subscription input")
        elif subscription.casefold() not in text:
            missing.append("required subscription")
    raw_minimum = card.get("minimum_credit_score")
    minimum = None if raw_minimum is None else amount(raw_minimum, "minimum_credit_score", missing)
    if minimum is not None:
        if not re.search(numeric_pattern(minimum), text):
            missing.append("minimum credit score")
        if data.get("credit_score_known") is False and not re.search(r"(?:check|verify|confirm|unknown|don.?t know|not know|eligib|approval|subject to|underwriting)", text):
            missing.append("unknown-score eligibility/approval caveat")
    print(json.dumps({"ok": not missing, "missing": missing}, ensure_ascii=False))


if __name__ == "__main__":
    main()
