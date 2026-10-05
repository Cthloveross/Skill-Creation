#!/usr/bin/env python3
"""Rank documented promotional sign-up bonuses for a supplied date and invitation status.

Input: {"as_of": "YYYY-MM-DD or timestamp", "invitation_received": bool|null,
        "include_inactive": bool (optional)}
Output: JSON object described in SKILL.md.
"""
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path


def parse_date(value):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError("as_of must be an ISO date or timestamp beginning YYYY-MM-DD")
    return date.fromisoformat(value[:10])


def load_offers():
    path = Path(__file__).resolve().parent.parent / "references" / "promo_offers.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def active(record, as_of):
    return date.fromisoformat(record["window_start"]) <= as_of <= date.fromisoformat(record["window_end"])


def public_offer(record):
    return {
        "id": record.get("id"),
        "card": record["card"],
        "window_start": record["window_start"],
        "window_end": record["window_end"],
        "bonus": record.get("bonus"),
        "qualifying_spend_usd": record.get("qualifying_spend_usd"),
        "qualification_period": record.get("qualification_period"),
        "requirements": record.get("requirements", []),
        "exclusions": record.get("exclusions", []),
        "posting": record.get("posting"),
        "source_document_ids": record.get("source_document_ids", [])
    }


def main(payload):
    as_of = parse_date(payload.get("as_of"))
    invitation = payload.get("invitation_received", None)
    if invitation not in (True, False, None):
        raise ValueError("invitation_received must be true, false, or null")
    include_inactive = payload.get("include_inactive", True)
    if not isinstance(include_inactive, bool):
        raise ValueError("include_inactive must be boolean")

    data = load_offers()
    candidates, unavailable, needs_confirmation = [], [], []
    for record in data["signup_bonus_offers"]:
        in_window = active(record, as_of)
        invite_needed = record.get("requires_invitation", False)
        if in_window and (not invite_needed or invitation is True):
            entry = public_offer(record)
            entry["availability"] = "conditionally_actionable"
            entry["eligibility_note"] = (
                "The date window and known invitation condition are satisfied; new-customer, "
                "account, purchase, and approval requirements still apply."
            )
            candidates.append(entry)
        elif include_inactive:
            entry = public_offer(record)
            if not in_window:
                entry["unavailable_reason"] = (
                    "The supplied date is outside this offer's documented window "
                    f"({record['window_start']} through {record['window_end']})."
                )
            elif invitation is False:
                entry["unavailable_reason"] = "This offer requires an invitation, and no invitation was reported."
            else:
                entry["unavailable_reason"] = "This offer requires an invitation; invitation status is unknown."
                if "Whether an invitation was received" not in needs_confirmation:
                    needs_confirmation.append("Whether an invitation was received")
            unavailable.append(entry)

    def value(entry):
        raw = entry["bonus"].get("estimated_usd_value")
        return Decimal(raw) if raw is not None else Decimal("0")

    candidates.sort(key=lambda item: (value(item), Decimal(item.get("qualifying_spend_usd") or "0")), reverse=True)
    non_bonus = []
    for record in data["non_bonus_promotions"]:
        if active(record, as_of):
            non_bonus.append({
                "card": record["card"],
                "promotion": record["promotion"],
                "reason_not_signup_bonus": record["reason_not_signup_bonus"],
                "source_document_ids": record["source_document_ids"]
            })

    return {
        "as_of": as_of.isoformat(),
        "best_available": candidates[0] if candidates else None,
        "available_signup_bonus_candidates": candidates,
        "unavailable_or_not_actionable_signup_bonuses": unavailable,
        "active_non_bonus_promotions": non_bonus,
        "needs_confirmation": needs_confirmation,
        "interpretation": (
            "Ranked by documented estimated USD reward value among date-active offers whose "
            "known invitation requirement is satisfied. This is not an approval or eligibility decision."
        )
    }


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(request), ensure_ascii=False, sort_keys=True))
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
