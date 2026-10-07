#!/usr/bin/env python3
"""Produce a safe, non-action triage plan for ATM debit-card declines.

Reads a JSON object from stdin and emits a JSON object to stdout. This script
never accesses customer data and does not execute banking actions.
"""
import json
import sys

MONEY_FIELDS = ("requested_amount", "published_daily_limit", "amount_used_today")
BOOL_FIELDS = (
    "cards_declined_at_same_atm",
    "alternate_atm_tried",
    "alternate_atm_available",
    "cash_dispensed",
)


def fail(message):
    return {"ok": False, "error": message}


def valid_money(value):
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0)


def main(payload):
    if not isinstance(payload, dict):
        return fail("input must be a JSON object")
    for field in BOOL_FIELDS:
        if field not in payload or not isinstance(payload[field], bool):
            return fail("%s must be a boolean" % field)
    for field in MONEY_FIELDS:
        value = payload.get(field)
        if not valid_money(value):
            return fail("%s must be a nonnegative number or null" % field)

    same = payload["cards_declined_at_same_atm"]
    alternate_tried = payload["alternate_atm_tried"]
    alternate_available = payload["alternate_atm_available"]
    cash_dispensed = payload["cash_dispensed"]
    code = payload.get("decline_code")
    requested = payload.get("requested_amount")
    limit = payload.get("published_daily_limit")
    used = payload.get("amount_used_today")

    steps = []
    fields_to_collect = ["exact decline message or code", "ATM location", "timestamp", "requested amount", "whether cash was dispensed"]

    known_limit_exceeded = (
        requested is not None and limit is not None
        and (requested > limit or (used is not None and requested + used > limit))
    )

    if cash_dispensed:
        classification = "cash_dispensed_review_transaction_and_cash_count"
        steps.append("Do not characterize this as a no-cash decline; review the transaction and cash received before further diagnosis.")
    elif str(code).strip() == "58":
        classification = "terminal_specific_restriction"
        steps.append("Use a different ATM, terminal, or merchant; this terminal-specific issue is not resolved by changing card settings.")
    elif known_limit_exceeded:
        classification = "known_daily_withdrawal_limit_exceeded"
        steps.append("The requested amount exceeds the remaining supplied daily-limit capacity; explain the used amount and remaining capacity before considering any eligible, confirmed limit-change request.")
    elif same and not alternate_tried:
        classification = "likely_shared_atm_or_terminal_issue"
        steps.append("Do not retry repeatedly at the same ATM.")
        if alternate_available:
            steps.append("Try a nearby ATM at a different location or bank and retain the result.")
        else:
            steps.append("Locate a different ATM or bank-operated machine before treating this as a card-specific issue.")
    elif alternate_tried:
        classification = "repeat_decline_requires_verified_diagnosis"
        steps.append("Before any account lookup or card action, verify identity and authority, then check card status, linked account status, available balance, pending activity, daily usage, and applicable security/PIN conditions.")
    else:
        classification = "insufficient_pattern_for_card_diagnosis"
        steps.append("Collect the ATM location, exact message, amount, and whether another ATM produces the same result before taking any card action.")

    limit_assessment = "unknown: a published limit, remaining daily usage, and available funds are not all known"
    if requested is not None and limit is not None:
        if requested > limit:
            limit_assessment = "requested amount exceeds the supplied published daily limit"
        elif used is None:
            limit_assessment = "requested amount is within the supplied nominal daily limit; remaining capacity is unknown because same-day use is unknown"
        elif requested + used > limit:
            limit_assessment = "requested amount plus supplied same-day use exceeds the supplied daily limit"
        else:
            limit_assessment = "requested amount fits within the supplied limit after supplied same-day use; available balance, holds, status, and ATM operator limits still require confirmation"

    return {
        "ok": True,
        "classification": classification,
        "next_steps": steps,
        "limit_assessment": limit_assessment,
        "fields_to_collect": fields_to_collect,
        "banking_action_performed": False,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        result = main(json.loads(raw))
    except json.JSONDecodeError:
        result = fail("stdin must contain valid JSON")
    except Exception as exc:  # Defensive JSON-only failure behavior.
        result = fail("unable to build plan: %s" % exc)
    print(json.dumps(result, separators=(",", ":")))
