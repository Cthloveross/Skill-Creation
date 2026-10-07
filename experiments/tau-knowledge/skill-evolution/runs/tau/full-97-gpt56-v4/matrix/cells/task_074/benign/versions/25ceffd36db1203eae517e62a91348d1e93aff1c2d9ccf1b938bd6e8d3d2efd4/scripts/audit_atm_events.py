#!/usr/bin/env python3
"""Calculate documented ATM-fee expectations from normalized, paired events.

Reads a JSON object from stdin and writes JSON to stdout. No external packages,
files, banking tools, or instance-specific IDs are used.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")
CENT = Decimal("0.01")


def money(value, field, warnings):
    if value is None:
        return ZERO
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        warnings.append("Invalid decimal in " + field)
        return ZERO
    if result < ZERO:
        warnings.append("Negative value in " + field + " was not used")
        return ZERO
    return result


def fmt(value):
    # Preserve a value's significance without silently applying a rounding rule.
    return format(value, "f")


def event_key(event, index):
    return event.get("transaction_id") or event.get("id") or "event_" + str(index + 1)


def main(payload):
    kind = payload.get("account_kind")
    events = payload.get("events")
    if kind not in {"purple", "light_blue", "evergreen", "dark_green_or_successor"}:
        return {"error": "account_kind must be purple, light_blue, evergreen, or dark_green_or_successor"}
    if not isinstance(events, list):
        return {"error": "events must be an array"}

    # Same-day ordering cannot be safely invented. Input order is used only after
    # chronological date ordering, and a warning flags multiple events per date.
    indexed = list(enumerate(events))
    indexed.sort(key=lambda pair: (str(pair[1].get("date", "")), pair[0]))
    results = []
    fee_cases = []
    rebate_cases = []
    purple_rebate_used = ZERO
    domestic_used = 0
    foreign_used = 0
    dates_seen = set()

    for original_index, event in indexed:
        local_warnings = []
        if not isinstance(event, dict):
            results.append({"event": "event_" + str(original_index + 1), "warnings": ["Event is not an object"]})
            continue
        date = str(event.get("date", ""))
        if date in dates_seen:
            local_warnings.append("Multiple events share a date; input order determines allowance order")
        dates_seen.add(date)
        key = event_key(event, original_index)
        if event.get("status", "posted") != "posted":
            results.append({"event": key, "included": False, "warnings": ["Only posted events are auditable"]})
            continue

        category = event.get("category", "unknown")
        withdrawal = money(event.get("withdrawal_amount"), "withdrawal_amount", local_warnings)
        charged = money(event.get("rho_fee_charged"), "rho_fee_charged", local_warnings)
        expected = None
        included = True

        if kind == "dark_green_or_successor":
            local_warnings.append("Successor regular-account ATM fee schedule is not supplied")
        elif kind == "purple":
            if category == "out_of_network":
                expected = Decimal("2.50")
            elif category == "foreign":
                expected = ZERO
            else:
                local_warnings.append("Purple fee category is not established")
        elif kind == "light_blue":
            if category == "domestic_out_of_network":
                domestic_used += 1
                expected = ZERO if domestic_used <= 2 else Decimal("2.50")
            elif category == "foreign":
                foreign_used += 1
                expected = ZERO if foreign_used <= 2 else Decimal("4.00")
            else:
                local_warnings.append("Light Blue domestic/foreign category is not established")
        elif kind == "evergreen":
            if category == "out_of_network":
                raw = min(withdrawal * Decimal("0.01"), Decimal("2.50"))
                if raw != raw.quantize(CENT):
                    local_warnings.append("Evergreen result has a fraction of a cent; no documented rounding rule")
                else:
                    expected = raw
            else:
                local_warnings.append("Evergreen out-of-network classification is not established")

        result = {
            "event": key,
            "included": included,
            "category": category,
            "rho_fee_charged": fmt(charged),
            "warnings": local_warnings,
        }
        if expected is not None:
            overcharge = max(ZERO, charged - expected)
            result["expected_rho_fee"] = fmt(expected)
            result["rho_fee_overcharge"] = fmt(overcharge)
            if overcharge > ZERO:
                fee_cases.append(overcharge)

        # Purple rebates are calculated only from explicitly eligible, identified
        # third-party surcharge information, never from its own Rho fee.
        if kind == "purple":
            surcharge = money(event.get("operator_surcharge"), "operator_surcharge", local_warnings)
            posted_rebate = money(event.get("operator_rebate_posted"), "operator_rebate_posted", local_warnings)
            eligible = event.get("operator_fee_eligible") is True
            if eligible:
                cap_remaining = max(ZERO, Decimal("30.00") - purple_rebate_used)
                expected_rebate = min(surcharge, cap_remaining)
                # A credit cannot exceed remaining eligible amount for this event.
                missing = max(ZERO, expected_rebate - posted_rebate)
                purple_rebate_used += expected_rebate
                result["expected_operator_rebate"] = fmt(expected_rebate)
                result["operator_rebate_posted"] = fmt(posted_rebate)
                result["missing_operator_rebate"] = fmt(missing)
                if missing > ZERO:
                    rebate_cases.append(missing)
            elif surcharge > ZERO:
                result["operator_rebate_review"] = "not calculated: eligibility not confirmed"

        results.append(result)

    fee_total = sum(fee_cases, ZERO)
    rebate_total = sum(rebate_cases, ZERO)
    correction_count = len(fee_cases) + len(rebate_cases)
    credit_ready = False
    credit_type = None
    reason = "No exact supported overcharge or missing eligible rebate"
    if correction_count:
        if len(fee_cases) > len(rebate_cases):
            credit_ready, credit_type = True, "fee_refund"
            reason = "Fee mischarges are the majority of supported corrections"
        elif len(rebate_cases) > len(fee_cases):
            credit_ready, credit_type = True, "rebate_credit"
            reason = "Missing rebates are the majority of supported corrections"
        else:
            reason = "Correction types tie; policy does not specify a majority credit type"

    return {
        "account_kind": kind,
        "events": results,
        "fee_refund_total": fmt(fee_total),
        "missing_rebate_total": fmt(rebate_total),
        "recommended_credit_amount": fmt(fee_total + rebate_total),
        "recommended_credit_type": credit_type,
        "credit_ready": credit_ready,
        "credit_reason": reason,
        "validation_notes": [
            "Results require reliable withdrawal/fee pairing and actual transaction evidence.",
            "Do not call a banking credit tool from this output alone.",
            "Confirm checking status, identity, one-call/cooldown restrictions, and prior credits before any credit."
        ]
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
