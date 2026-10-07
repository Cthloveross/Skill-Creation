#!/usr/bin/env python3
"""Classify a promotion claim against offers already verified in a KB.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs comparison only; it does not search, authenticate, or authorize banking
activity.
"""

import json
import sys
from decimal import Decimal, InvalidOperation

COMPARE_FIELDS = (
    "card_name",
    "product",
    "promotion_code",
    "offer_start",
    "offer_end",
    "spend_amount",
    "qualifying_months",
    "benefit_type",
    "benefit_amount",
)
NUMERIC_FIELDS = {"spend_amount", "qualifying_months", "benefit_amount"}
REQUIRED_TOP_LEVEL = (
    "kb_search_completed",
    "external_promotion_claim",
    "account_identified",
    "identity_verified",
    "claim",
    "verified_offers",
)


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def present(value):
    return value is not None and value != ""


def normalized_decimal(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid numeric offer term")
    try:
        text = str(value).strip().replace("$", "").replace(",", "")
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("invalid numeric offer term")
    if not number.is_finite():
        raise ValueError("numeric offer term must be finite")
    return format(number.normalize(), "f")


def normalize(field, value):
    if not present(value):
        return None
    if isinstance(value, (dict, list, tuple, set)):
        raise ValueError("offer comparison values must be scalar")
    if field in NUMERIC_FIELDS:
        return normalized_decimal(value)
    text = str(value).strip()
    if field == "promotion_code":
        return text.upper()
    return " ".join(text.casefold().split())


def invalid(message):
    emit({"ok": False, "error": message})
    return 1


def main():
    try:
        request = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        return invalid("stdin must contain one JSON object: %s" % exc)

    if not isinstance(request, dict):
        return invalid("top-level input must be an object")
    missing = [key for key in REQUIRED_TOP_LEVEL if key not in request]
    if missing:
        return invalid("missing required fields: " + ", ".join(missing))
    for key in REQUIRED_TOP_LEVEL[:4]:
        if not isinstance(request[key], bool):
            return invalid(key + " must be boolean")
    if not isinstance(request["claim"], dict):
        return invalid("claim must be an object")
    if not isinstance(request["verified_offers"], list):
        return invalid("verified_offers must be an array")
    if any(not isinstance(offer, dict) for offer in request["verified_offers"]):
        return invalid("each verified_offers entry must be an object")

    try:
        claim = {
            field: normalize(field, request["claim"].get(field))
            for field in COMPARE_FIELDS
        }
        offers = []
        for index, raw_offer in enumerate(request["verified_offers"]):
            normalized = {
                field: normalize(field, raw_offer.get(field))
                for field in COMPARE_FIELDS
            }
            offer_id = raw_offer.get("offer_id", str(index))
            offers.append((str(offer_id), normalized))
    except ValueError as exc:
        return invalid(str(exc))

    claimed_fields = [field for field, value in claim.items() if value is not None]
    base = {
        "ok": True,
        "candidate_count": 0,
        "matching_offer_ids": [],
        "conflicting_fields": [],
        "transfer_reason": None,
    }

    if not request["kb_search_completed"]:
        base.update({
            "status": "knowledge_search_required",
            "next_step": "Search the supplied knowledge base before deciding whether the external offer is verified.",
        })
        emit(base)
        return 0

    # A no-detail claim cannot be reliably matched to an offer merely because an
    # offer catalog exists. It remains an unconfirmed external communication.
    if not claimed_fields:
        if request["external_promotion_claim"]:
            base.update({
                "status": "unconfirmed_external_communication",
                "transfer_reason": "unconfirmed_external_communication",
                "next_step": "Do not honor the claim; transfer after documenting that no identifying offer terms were available.",
            })
        else:
            base.update({
                "status": "insufficient_offer_details",
                "next_step": "Request offer identifiers or terms before evaluating eligibility.",
            })
        emit(base)
        return 0

    matches = []
    all_conflicts = set()
    for offer_id, offer in offers:
        conflicts = []
        for field in claimed_fields:
            # A documented offer that omits a disclosed material term cannot
            # verify that term.
            if offer[field] != claim[field]:
                conflicts.append(field)
        if conflicts:
            all_conflicts.update(conflicts)
        else:
            matches.append(offer_id)

    base["candidate_count"] = len(matches)
    base["matching_offer_ids"] = matches
    base["conflicting_fields"] = sorted(all_conflicts)

    if not matches:
        if request["external_promotion_claim"]:
            base.update({
                "status": "unconfirmed_external_communication",
                "transfer_reason": "unconfirmed_external_communication",
                "next_step": "The documented offers do not verify all disclosed claim terms. Do not apply a credit; transfer for external-promotion review.",
            })
        else:
            base.update({
                "status": "no_documented_match",
                "next_step": "Do not apply a credit. Obtain corrected offer information or follow the applicable internal review process.",
            })
    elif len(matches) > 1:
        base.update({
            "status": "multiple_documented_candidates",
            "next_step": "Obtain an offer identifier and confirm the applicable account/product; do not select an offer by assumption.",
        })
    elif not request["account_identified"]:
        base.update({
            "status": "matched_offer_needs_account_identification",
            "next_step": "Identify and verify the customer, then confirm ownership and product eligibility before any account action.",
        })
    elif not request["identity_verified"]:
        base.update({
            "status": "matched_offer_needs_identity_verification",
            "next_step": "Complete required identity verification and logging before inspecting or changing the account.",
        })
    else:
        base.update({
            "status": "matched_offer_requires_eligibility_and_confirmation",
            "next_step": "Confirm product, opening date, net posted spend, offer window, account status, limits, and explicit customer confirmation before considering a promotional credit.",
        })

    emit(base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
