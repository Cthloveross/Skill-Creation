#!/usr/bin/env python3
"""Render a qualification-aware draft from structured promotion evidence.

Reads JSON from stdin and emits JSON to stdout. It accepts the analyze_offers
input schema plus product_scope and include_non_signup. It does not make network
calls or access customer data.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from analyze_offers import main as analyze


def text(value):
    return value.strip() if isinstance(value, str) and value.strip() else ""


def joined(values):
    values = [text(v) for v in values if text(v)]
    return "; ".join(values)


def reward_text(reward):
    if not isinstance(reward, dict):
        return "a documented bonus"
    kind = text(reward.get("kind")).replace("_", " ") or "bonus"
    amount = reward.get("amount")
    if amount is None:
        return "a {} bonus".format(kind)
    if kind in ("statement credit", "cash back", "cash"):
        return "${:,} {}".format(int(amount) if float(amount).is_integer() else float(amount), kind)
    return "{:,} {}".format(int(amount) if float(amount).is_integer() else float(amount), kind)


def conditions(record):
    q = record.get("qualification")
    if not isinstance(q, dict):
        q = {}
    parts = []
    if q.get("invitation_required") is True:
        parts.append("an invitation is required")
    if q.get("new_customer_required") is True:
        parts.append("new customers only")
    for key in ("eligibility", "spend_requirement", "spend_window", "good_standing", "other_conditions"):
        if text(q.get(key)):
            parts.append(text(q[key]))
    exclusions = q.get("exclusions")
    if isinstance(exclusions, list) and exclusions:
        parts.append("exclusions: " + joined(exclusions))
    return joined(parts)


def scope_ok(record, scope):
    record_scope = text(record.get("product_scope")).lower()
    return scope == "all" or not record_scope or record_scope == scope


def main(payload):
    result = analyze(payload)
    if not result.get("ok"):
        return result
    scope = text(payload.get("product_scope")).lower() or "all"
    if scope not in {"all", "consumer", "business"}:
        return {"ok": False, "errors": ["product_scope must be consumer, business, or all."], "warnings": []}
    bonuses = [r for r in result["ranked_active_signup_bonuses"] if scope_ok(r, scope)]
    non_signup = [r for r in result["active_non_signup_offers"] if scope_ok(r, scope)]
    date = result["as_of"]
    if not bonuses:
        response = "As of {}, I found no active sign-up bonuses in the supplied records for the requested product scope.".format(date)
        return dict(result, response=response, active_signup_bonuses=[])

    leader = bonuses[0]
    leader_conditions = conditions(leader)
    supplement = text(leader.get("supplemental_benefits"))
    first = "As of {}, the largest active sign-up bonus by documented value is {}: {}".format(date, leader["card"], reward_text(leader.get("reward")))
    if supplement:
        first += " plus {}".format(supplement)
    first += "."
    if leader_conditions:
        first += " It requires {}.".format(leader_conditions)
    lines = [first]

    if len(bonuses) > 1:
        lines.append("Other active sign-up options:")
        for record in bonuses[1:]:
            line = "- {}: {}".format(record["card"], reward_text(record.get("reward")))
            record_conditions = conditions(record)
            if record_conditions:
                line += ", with {}".format(record_conditions)
            line += "."
            lines.append(line)
        accessible = bonuses[1]
        lines.append("Bottom line: {} has the highest headline value, but its requirements may make it less accessible. {} is a lower-value alternative when its eligibility and spend requirements are a better fit.".format(leader["card"], accessible["card"]))

    if payload.get("include_non_signup") is True and non_signup:
        lines.append("Other current promotions (not sign-up bonuses):")
        for record in non_signup:
            detail = text(record.get("details")) or text(record.get("fulfillment")) or "see supplied terms"
            lines.append("- {}: {}.".format(record["card"], detail))
    return dict(result, response="\n\n".join(lines), active_signup_bonuses=bonuses)


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON input: {}".format(exc.msg)], "warnings": []}))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["Unexpected processing error: {}".format(exc)], "warnings": []}))
