#!/usr/bin/env python3
"""Calculate supported ATM-fee findings from reviewer-normalized transaction events.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper is
intentionally conservative: classification and fee/withdrawal matching must be supplied
by a reviewer from real transaction history.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid monetary value: %r" % (value,))
    if amount < 0:
        raise ValueError("amounts must be non-negative")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value):
    try:
        return datetime.strptime(value, "%m/%d/%Y")
    except (TypeError, ValueError):
        raise ValueError("date must be MM/DD/YYYY")


def canonical_product(value):
    key = " ".join(str(value).strip().lower().replace("account", "").split())
    if key in {"blue", "green", "light green"}:
        return key
    raise ValueError("account_product must be blue, green, or light green")


def expected_fee(product, classification, amount, free_index=None):
    if classification == "in_network":
        return Decimal("0.00"), "in-network under supplied ATM fee rules"
    if classification == "foreign":
        if product in {"blue", "green"}:
            return max(amount * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP), "foreign fee"
        if amount <= Decimal("100.00"):
            return Decimal("2.00"), "Light Green foreign tier <= 100"
        if amount <= Decimal("300.00"):
            return Decimal("3.50"), "Light Green foreign tier > 100 through 300"
        return Decimal("5.00"), "Light Green foreign tier > 300"
    if classification == "out_of_network":
        if product == "blue":
            return min(amount * Decimal("0.01"), Decimal("3.00")).quantize(CENT, rounding=ROUND_HALF_UP), "Blue domestic out-of-network fee"
        if product == "green":
            return Decimal("3.00"), "Green domestic out-of-network fee"
        if free_index is None:
            raise ValueError("Light Green out-of-network event needs monthly index")
        if free_index <= 4:
            return Decimal("0.00"), "Light Green free domestic out-of-network withdrawal %d of 4" % free_index
        return Decimal("1.50"), "Light Green domestic out-of-network withdrawal after four free"
    raise ValueError("unsupported classification")


def main(payload):
    product = canonical_product(payload.get("account_product"))
    events = payload.get("events")
    corrections = payload.get("existing_corrections", [])
    if not isinstance(events, list) or not isinstance(corrections, list):
        raise ValueError("events and existing_corrections must be arrays")

    normalized = []
    event_ids = set()
    for raw in events:
        if not isinstance(raw, dict):
            raise ValueError("every event must be an object")
        event_id = str(raw.get("id", "")).strip()
        if not event_id or event_id in event_ids:
            raise ValueError("each event requires a unique non-empty id")
        event_ids.add(event_id)
        classification = raw.get("classification")
        if classification not in {"foreign", "out_of_network", "in_network", "unknown"}:
            raise ValueError("invalid classification for " + event_id)
        normalized.append({
            "id": event_id,
            "date": parse_date(raw.get("date")),
            "withdrawal_amount": money(raw.get("withdrawal_amount")),
            "classification": classification,
            "charged_bank_fee": money(raw.get("charged_bank_fee")),
            "match_confident": raw.get("match_confident") is True,
            "status": str(raw.get("status", "posted")).lower(),
            "note": raw.get("note", ""),
        })

    # A calendar-month chronological index is required only for Light Green's
    # domestic out-of-network allowance. Stable input ordering breaks same-date ties.
    indexed = list(enumerate(normalized))
    indexed.sort(key=lambda item: (item[1]["date"], item[0]))
    monthly_oon_count = defaultdict(int)
    free_indexes = {}
    if product == "light green":
        for _, event in indexed:
            if event["classification"] == "out_of_network" and event["status"] == "posted":
                month_key = (event["date"].year, event["date"].month)
                monthly_oon_count[month_key] += 1
                free_indexes[event["id"]] = monthly_oon_count[month_key]

    result_events = []
    unresolved = []
    gross = Decimal("0.00")
    eligible_ids = set()
    for event in normalized:
        reasons = []
        if event["status"] != "posted":
            reasons.append("withdrawal or fee is not posted")
        if event["classification"] == "unknown":
            reasons.append("ATM classification is unknown")
        if event["withdrawal_amount"] is None:
            reasons.append("withdrawal amount is missing")
        if event["charged_bank_fee"] is None:
            reasons.append("bank fee is not confidently matched")
        if not event["match_confident"]:
            reasons.append("fee-to-withdrawal match is not confirmed")
        output = {
            "id": event["id"], "date": event["date"].strftime("%m/%d/%Y"),
            "classification": event["classification"], "status": event["status"],
        }
        if reasons:
            output["finding"] = "unresolved"
            output["reasons"] = reasons
            unresolved.append({"id": event["id"], "reasons": reasons})
            result_events.append(output)
            continue
        expected, rule = expected_fee(product, event["classification"], event["withdrawal_amount"], free_indexes.get(event["id"]))
        overcharge = max(Decimal("0.00"), event["charged_bank_fee"] - expected)
        output.update({
            "finding": "overcharged" if overcharge else "no_overcharge",
            "withdrawal_amount": fmt(event["withdrawal_amount"]),
            "charged_bank_fee": fmt(event["charged_bank_fee"]),
            "expected_bank_fee": fmt(expected),
            "overcharge": fmt(overcharge),
            "rule": rule,
        })
        if event["id"] in free_indexes:
            output["monthly_out_of_network_index"] = free_indexes[event["id"]]
        result_events.append(output)
        if overcharge:
            gross += overcharge
            eligible_ids.add(event["id"])

    linked_corrections = Decimal("0.00")
    correction_issues = []
    seen_correction_keys = set()
    for raw in corrections:
        if not isinstance(raw, dict):
            raise ValueError("every existing correction must be an object")
        event_id = str(raw.get("event_id", "")).strip()
        key = (event_id, str(raw.get("amount")))
        if key in seen_correction_keys:
            correction_issues.append({"event_id": event_id, "reason": "duplicate correction input ignored"})
            continue
        seen_correction_keys.add(key)
        if raw.get("match_confident") is not True:
            correction_issues.append({"event_id": event_id, "reason": "correction match is not confirmed"})
            continue
        if event_id not in eligible_ids:
            correction_issues.append({"event_id": event_id, "reason": "correction is not tied to a supported overcharge"})
            continue
        linked_corrections += money(raw.get("amount"))

    net = max(Decimal("0.00"), gross - linked_corrections)
    return {
        "account_product": product,
        "events": result_events,
        "unresolved": unresolved,
        "correction_issues": correction_issues,
        "gross_overcharge": fmt(gross),
        "existing_corrections_total": fmt(linked_corrections),
        "net_correction": fmt(net),
        "credit_supported": net > 0 and not unresolved,
        "warning": "A true result still requires verified identity, account ownership and checking status, transaction recheck, and explicit customer confirmation before a credit tool call.",
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        print(json.dumps(main(incoming), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
