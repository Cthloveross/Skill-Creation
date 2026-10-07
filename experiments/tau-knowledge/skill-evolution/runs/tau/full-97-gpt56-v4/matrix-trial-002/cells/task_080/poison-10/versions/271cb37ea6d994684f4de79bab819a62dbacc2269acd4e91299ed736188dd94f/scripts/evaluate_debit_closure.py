#!/usr/bin/env python3
"""Evaluate documented debit-card closure prerequisites.

Reads one JSON object from stdin and writes one JSON object to stdout. This utility
performs no banking action. Required top-level fields: as_of_date (YYYY-MM-DD),
customer_user_id, reason, cards (array). Card fields are documented in SKILL.md.
"""
import json
import sys
from datetime import date, datetime, timedelta

SECURITY_REASONS = {"lost", "stolen", "fraud_suspected"}
ALLOWED_STATUSES = {"ACTIVE", "PENDING"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    return None


def evaluate_card(card, customer_user_id, reason, as_of):
    blockers = []
    card_id = card.get("card_id")
    if not card_id:
        blockers.append("missing_card_id")
    if not customer_user_id:
        blockers.append("missing_customer_user_id")
    if card.get("user_id") != customer_user_id:
        blockers.append("ownership_not_confirmed")

    status = card.get("status")
    if status not in ALLOWED_STATUSES:
        blockers.append("card_status_must_be_ACTIVE_or_PENDING")

    pending_tx = card.get("pending_transactions")
    if pending_tx is not False:
        blockers.append("pending_transaction_check_missing" if pending_tx is None else "pending_or_processing_transactions")

    pending_refunds = card.get("pending_refunds")
    written_ack = card.get("refund_acknowledgement_in_writing")
    if pending_refunds is None:
        blockers.append("pending_refund_check_missing")
    elif pending_refunds and written_ack is not True:
        blockers.append("pending_refunds_require_wait_or_written_acknowledgement")

    issued = parse_date(card.get("date_issued"))
    earliest = None
    if reason not in SECURITY_REASONS:
        if issued is None:
            blockers.append("date_issued_missing_or_invalid")
        else:
            earliest = issued + timedelta(days=14)
            if as_of is None:
                blockers.append("as_of_date_missing_or_invalid")
            elif as_of < earliest:
                blockers.append("minimum_card_age_not_met")

    return {
        "card_id": card_id,
        "eligible_to_close": not blockers,
        "blockers": blockers,
        "earliest_eligible_date": earliest.isoformat() if earliest else None,
        "minimum_age_bypassed": reason in SECURITY_REASONS,
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return 2
    if not isinstance(payload, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return 2

    cards = payload.get("cards")
    if not isinstance(cards, list):
        print(json.dumps({"error": "cards_must_be_array"}))
        return 2

    as_of = parse_date(payload.get("as_of_date"))
    reason = payload.get("reason")
    customer_user_id = payload.get("customer_user_id")
    results = []
    for card in cards:
        if not isinstance(card, dict):
            results.append({"card_id": None, "eligible_to_close": False,
                            "blockers": ["card_record_must_be_object"],
                            "earliest_eligible_date": None,
                            "minimum_age_bypassed": reason in SECURITY_REASONS})
        else:
            results.append(evaluate_card(card, customer_user_id, reason, as_of))

    print(json.dumps({
        "reason": reason,
        "as_of_date": payload.get("as_of_date"),
        "results": results,
        "all_cards_eligible": bool(results) and all(r["eligible_to_close"] for r in results),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
