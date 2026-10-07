#!/usr/bin/env python3
"""Render an evidence-derived, qualification-aware promotion-comparison draft.

Reads JSON from stdin and emits JSON to stdout. It accepts the analyze_offers
input schema plus product_scope and include_non_signup. No network or customer
data is accessed.
"""
import json
import os
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze


def text(value):
    return value.strip() if isinstance(value, str) and value.strip() else ""


def joined(values):
    return "; ".join(text(value) for value in values if text(value))


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def formatted_number(value):
    result = number(value)
    if result is None:
        return None
    if result == result.to_integral_value():
        return format(int(result), ",")
    return format(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ",.2f")


def reward_text(reward):
    if not isinstance(reward, dict):
        return "a documented bonus"
    kind = text(reward.get("kind")).replace("_", " ") or "bonus"
    amount = formatted_number(reward.get("amount"))
    if amount is None:
        return "a {} bonus".format(kind)
    if kind in {"statement credit", "cash back", "cash"}:
        return "${} {}".format(amount, kind)
    return "{} {}".format(amount, kind)


def fee_text(value):
    if isinstance(value, dict):
        return text(value.get("description")) or text(value.get("standard"))
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def conditions(record):
    qualification = record.get("qualification")
    qualification = qualification if isinstance(qualification, dict) else {}
    parts = []
    if qualification.get("invitation_required") is True:
        parts.append("an invitation is required")
    if qualification.get("new_customer_required") is True:
        parts.append("new customers only")
    for key in ("eligibility", "spend_requirement", "spend_window", "good_standing", "other_conditions"):
        if text(qualification.get(key)):
            parts.append(text(qualification[key]))
    exclusions = qualification.get("exclusions")
    if isinstance(exclusions, list) and exclusions:
        parts.append("exclusions: " + joined(exclusions))
    return joined(parts)


def scope_ok(record, requested_scope):
    record_scope = text(record.get("product_scope")).lower()
    return requested_scope == "all" or not record_scope or record_scope == requested_scope


def scope_label(record):
    scope = text(record.get("product_scope")).lower()
    return " This is a business-card option, not a consumer-card offer." if scope == "business" else ""


def record_line(record):
    line = "- {}: {}".format(record.get("card", "Unnamed card"), reward_text(record.get("reward")))
    record_conditions = conditions(record)
    if record_conditions:
        line += ", with {}".format(record_conditions)
    fee = fee_text(record.get("annual_fee"))
    if fee:
        line += ". Annual fee: {}".format(fee)
    supplemental = text(record.get("supplemental_benefits"))
    if supplemental:
        line += ". Also includes {}".format(supplemental)
    return line + "." + scope_label(record)


def main(payload):
    result = analyze(payload)
    if not result.get("ok"):
        return result
    requested_scope = text(payload.get("product_scope")).lower() or "all"
    if requested_scope not in {"all", "consumer", "business"}:
        return {"ok": False, "errors": ["product_scope must be consumer, business, or all."], "warnings": []}

    bonuses = [x for x in result["ranked_active_signup_bonuses"] if scope_ok(x, requested_scope)]
    non_signup = [x for x in result["active_non_signup_offers"] if scope_ok(x, requested_scope)]
    if not bonuses:
        response = "As of {}, I found no active sign-up bonuses in the supplied records for the requested product scope.".format(result["as_of"])
        return dict(result, response=response, active_signup_bonuses=[])

    leader = bonuses[0]
    lines = ["As of {}, the largest active sign-up bonus by documented value is {}: {}.".format(result["as_of"], leader["card"], reward_text(leader.get("reward")))]
    leader_conditions = conditions(leader)
    if leader_conditions:
        lines.append("It requires {}.".format(leader_conditions))
    leader_fee = fee_text(leader.get("annual_fee"))
    if leader_fee:
        lines.append("Annual fee: {}.".format(leader_fee))
    if text(leader.get("supplemental_benefits")):
        lines.append("It also includes {}.".format(text(leader["supplemental_benefits"])))
    if text(leader.get("product_scope")).lower() == "business":
        lines.append("This is a business-card option, not a consumer-card offer.")

    if len(bonuses) > 1:
        lines.append("Other active sign-up options:")
        lines.extend(record_line(record) for record in bonuses[1:])
        alternative = bonuses[1]
        lines.append("Bottom line: {} has the highest headline value, but its documented eligibility and spending requirements may make it less accessible. {} is a lower-value alternative when its eligibility and spend requirements are a better fit.".format(leader["card"], alternative["card"]))

    if payload.get("include_non_signup") is True and non_signup:
        lines.append("Other current promotions (not sign-up bonuses):")
        for record in non_signup:
            detail = text(record.get("details")) or text(record.get("fulfillment")) or "see supplied terms"
            lines.append("- {}: {}.".format(record.get("card", "Unnamed card"), detail))
    return dict(result, response="\n\n".join(lines), active_signup_bonuses=bonuses)


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: {}".format(exc.msg)], "warnings": []}))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["Unexpected processing error: {}".format(exc)], "warnings": []}))
