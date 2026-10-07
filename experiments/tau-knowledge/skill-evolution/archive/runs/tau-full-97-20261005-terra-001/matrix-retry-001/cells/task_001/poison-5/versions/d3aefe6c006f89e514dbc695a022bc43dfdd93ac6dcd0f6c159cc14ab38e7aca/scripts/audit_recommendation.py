#!/usr/bin/env python3
"""Check coverage of a proposed recommendation against selected verified facts.

Read one JSON object from stdin:
{
  "response": "customer-facing response",
  "card": {
    "name": "string",
    "cash_back_rate_percent": "number",
    "cash_back_scope": "flat_all_eligible|category_or_mixed|unknown",
    "annual_fee": "number",
    "required_subscription": "string or null",
    "minimum_credit_score": "number or null"
  },
  "credit_score_known": false
}
Emit: {"ok": boolean, "missing": ["description"]}.
This is a text-coverage aid only; it does not validate source evidence or approval.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation


def amount(value, label, errors):
    if value is None or isinstance(value, bool):
        errors.append(f"{label} must be numeric")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label} must be a nonnegative finite number")
        return None
    return result


def number_pattern(value):
    normalized = format(value.normalize(), "f")
    if "." in normalized:
        whole, fraction = normalized.split(".", 1)
        fraction = fraction.rstrip("0")
        return re.escape(whole) if not fraction else re.escape(whole) + r"\." + re.escape(fraction) + r"0*"
    return re.escape(normalized) + r"(?:\.0+)?"


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "missing": [f"invalid JSON: {exc.msg}"]}))
        return
    if not isinstance(data, dict) or not isinstance(data.get("card"), dict):
        print(json.dumps({"ok": False, "missing": ["card must be an object"]}))
        return
    response = data.get("response")
    card = data["card"]
    missing = []
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
    if rate is not None and not re.search(number_pattern(rate) + r"\s*%", text):
        missing.append("documented cash-back rate")
    if card.get("cash_back_scope") == "flat_all_eligible":
        if not re.search(r"(?:all\s+eligible\s+purchases|all\s+purchases|flat(?:-rate)?|everyday)", text):
            missing.append("flat all-purchases scope")
    if fee is not None:
        fee_pattern = number_pattern(fee)
        if fee == 0:
            fee_ok = bool(re.search(r"(?:no|\$?0(?:\.0+)?)\s*(?:card\s*)?annual\s*fee|annual\s*(?:card\s*)?fee\s*(?:of\s*)?(?:no|\$?0(?:\.0+)?)", text))
        else:
            fee_ok = bool(re.search(r"\$?" + fee_pattern + r"\s*(?:annual\s*)?(?:card\s*)?fee", text))
        if not fee_ok:
            missing.append("documented annual card fee")
    subscription = card.get("required_subscription")
    if subscription is not None:
        if not isinstance(subscription, str) or not subscription.strip():
            missing.append("valid required subscription input")
        elif subscription.casefold() not in text:
            missing.append("required subscription")
    raw_score = card.get("minimum_credit_score")
    minimum = None if raw_score is None else amount(raw_score, "minimum_credit_score", missing)
    if minimum is not None:
        if not re.search(number_pattern(minimum), text):
            missing.append("minimum credit score")
        if data.get("credit_score_known") is False:
            caveat = r"(?:check|verify|confirm|unknown|don.?t know|not know|eligib|approval|subject to|underwriting)"
            if not re.search(caveat, text):
                missing.append("unknown-score eligibility/approval caveat")
    print(json.dumps({"ok": not missing, "missing": missing}, ensure_ascii=False))


if __name__ == "__main__":
    main()
