#!/usr/bin/env python3
"""Recommend a reason for an unverified external-promotion handoff.

Reads one JSON object from stdin and writes one JSON object to stdout.
This helper never calls banking tools and never treats an offer as verified.
"""

import json
import sys
from typing import Any, Dict, Iterable

TIER_1 = {
    "fraud_or_security_concern",
    "account_closure_request",
    "deceased_account_holder",
    "legal_or_regulatory_matter",
    "account_ownership_dispute",
    "complex_billing_dispute",
    "abusive_customer_behavior",
    "third_party_inquiry",
    "technical_system_error",
    "customer_demands_after_unavailable_offer_refusal",
}


def text_values(value: Any) -> Iterable[str]:
    """Yield strings from arbitrary JSON without assigning meaning to keys."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from text_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from text_values(item)


def contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def as_bool(data: Dict[str, Any], key: str, inferred: bool = False) -> bool:
    value = data.get(key)
    return value if isinstance(value, bool) else inferred


def main(data: Dict[str, Any]) -> Dict[str, Any]:
    transcript = " ".join(text_values(data.get("clarifications", []))).lower()
    source = str(data.get("offer_source") or "external communication").strip()

    external_inferred = contains_any(
        transcript, ("flyer", "letter", "mailer", "mail offer", "email offer", "promotional offer")
    )
    external = as_bool(data, "external_offer_claimed", external_inferred)

    unverified_inferred = contains_any(
        transcript,
        (
            "cannot identify", "can't identify", "cannot locate", "can't locate",
            "does not match", "doesn't match", "could not verify", "couldn't verify",
            "cannot verify", "can't verify", "unavailable in the system",
        ),
    )
    search_done = as_bool(data, "kb_search_performed", unverified_inferred)
    verified = as_bool(data, "offer_verified", False)
    identifiers = as_bool(data, "offer_identifiers_provided", False)

    higher = data.get("higher_priority_reason")
    if higher is not None and higher not in TIER_1:
        return {
            "decision": "request_more_information",
            "reason": None,
            "summary": "No transfer prepared because the supplied higher-priority reason is not a valid Tier 1 reason.",
            "customer_message": "I need to review the issue details before selecting the correct support path.",
            "validation": {"error": "invalid higher_priority_reason", "valid_tier_1_reasons": sorted(TIER_1)},
        }

    if higher:
        return {
            "decision": "transfer",
            "reason": higher,
            "summary": "Customer requires specialist assistance for the applicable higher-priority issue. External-offer details, if any, should be reviewed by the receiving agent.",
            "customer_message": "I’ll connect you with the appropriate specialist for help.",
            "validation": {"selected_by": "explicit applicable Tier 1 reason"},
        }

    if external and search_done and not verified:
        missing = []
        if not identifiers:
            missing.extend(["product/card name", "offer or claim code", "promotion or expiration dates"])
        identifier_text = ", ".join(missing) if missing else "no additional identifiers"
        description = str(data.get("offer_description") or "").strip()
        detail = " Customer-described offer terms were noted but not verified." if description else ""
        return {
            "decision": "transfer",
            "reason": "unconfirmed_external_communication",
            "summary": (
                f"Customer seeks help with a claimed {source} promotion. Available knowledge was reviewed, "
                f"but the specific offer could not be verified. Missing or unresolved identifiers: {identifier_text}. "
                f"No redemption, enrollment, or eligibility determination was completed.{detail}"
            ),
            "customer_message": (
                "I can’t verify this specific offer from the information currently available, so I’ll send it "
                "for specialist review. I have not redeemed or enrolled you in the offer."
            ),
            "validation": {
                "external_offer_claimed": external,
                "kb_search_performed": search_done,
                "offer_verified": verified,
                "offer_identifiers_provided": identifiers,
                "selected_by": "Tier 2 unconfirmed external communication",
            },
        }

    prerequisites = []
    if not external:
        prerequisites.append("confirmation that the customer is claiming a specific external flyer, letter, email, or similar offer")
    if not search_done:
        prerequisites.append("knowledge-base review for the exact offer")
    if verified:
        prerequisites.append("use the verified offer's documented redemption or application instructions")
    if not identifiers and not verified:
        prerequisites.append("exact product/card name, offer or claim code, and promotion/expiration dates")

    return {
        "decision": "request_more_information",
        "reason": None,
        "summary": "An unconfirmed-external-communication transfer is not yet supported by the available facts.",
        "customer_message": (
            "Please provide the exact card or product name, any offer or claim code, and the promotion or "
            "expiration dates shown on the communication so the offer can be checked."
        ),
        "validation": {
            "external_offer_claimed": external,
            "kb_search_performed": search_done,
            "offer_verified": verified,
            "offer_identifiers_provided": identifiers,
            "missing_prerequisites": prerequisites,
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"decision": "request_more_information", "reason": None, "error": str(exc)}))
