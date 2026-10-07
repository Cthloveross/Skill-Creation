#!/usr/bin/env python3
"""Conservatively classify an externally claimed credit-card promotion.

Reads one JSON object from stdin and emits one JSON object on stdout. This
advisory helper does not verify identity or eligibility and takes no action.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def clean_text(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def normalized(value):
    value = clean_text(value)
    return value.casefold() if value else None


def decimal_value(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def iso_date(value):
    value = clean_text(value)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def require_object(payload, key, errors):
    value = payload.get(key)
    if not isinstance(value, dict):
        errors.append("'%s' must be an object" % key)
        return {}
    return value


def equivalent_required(claim_value, offer_value, converter):
    """A supplied material claim must be present and equal in a candidate."""
    claim_normal = converter(claim_value)
    if claim_normal is None:
        return True
    offer_normal = converter(offer_value)
    return offer_normal is not None and claim_normal == offer_normal


def candidate_matches(claim, offer, as_of):
    fields = (
        ("product", normalized),
        ("campaign_code", normalized),
        ("reward_type", normalized),
        ("reward_amount", decimal_value),
        ("spend_amount", decimal_value),
        ("period_months", decimal_value),
    )
    for field, converter in fields:
        if not equivalent_required(claim.get(field), offer.get(field), converter):
            return False

    if as_of is not None:
        start = iso_date(offer.get("offer_start"))
        end = iso_date(offer.get("offer_end"))
        if start is not None and as_of < start:
            return False
        if end is not None and as_of > end:
            return False
    return True


def get_account_status(customer):
    has_profile = customer.get("has_profile")
    has_account = bool(clean_text(customer.get("account_id")))
    if has_profile is False:
        return "customer_reports_no_profile"
    if has_profile is True and has_account:
        return "profile_and_card_account_identifier_supplied"
    if has_profile is True:
        return "profile_known_no_card_account_identified"
    return "no_account_profile_status_available"


def account_sentence(status):
    sentences = {
        "customer_reports_no_profile": "Customer reports no profile or eligible card account.",
        "profile_and_card_account_identifier_supplied": "A card account identifier was supplied but has not been verified for eligibility.",
        "profile_known_no_card_account_identified": "A profile may exist, but no card account was identified.",
        "no_account_profile_status_available": "No account/profile status is available.",
    }
    return sentences[status]


def claimed_terms(claim):
    parts = []
    if claim.get("reward_amount") is not None:
        parts.append("reward amount %s" % claim.get("reward_amount"))
    if clean_text(claim.get("reward_type")):
        parts.append("reward type %s" % clean_text(claim.get("reward_type")))
    if claim.get("spend_amount") is not None:
        parts.append("spend requirement %s" % claim.get("spend_amount"))
    if claim.get("period_months") is not None:
        parts.append("qualification period %s months" % claim.get("period_months"))
    return "; ".join(parts) if parts else "terms not fully supplied"


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["top-level input must be an object"]}

    errors = []
    claim = require_object(payload, "claim", errors)
    customer = require_object(payload, "customer", errors)
    candidates = payload.get("candidate_offers", [])
    if not isinstance(candidates, list):
        errors.append("'candidate_offers' must be an array")
        candidates = []
    if errors:
        return {"ok": False, "errors": errors}

    as_of_raw = payload.get("as_of")
    as_of = iso_date(as_of_raw)
    if as_of_raw is not None and clean_text(as_of_raw) is not None and as_of is None:
        return {"ok": False, "errors": ["'as_of' must be YYYY-MM-DD or null"]}

    identifier_fields = ("product", "campaign_code", "personalized_identifier")
    missing_identifiers = [field for field in identifier_fields if not clean_text(claim.get(field))]
    has_identifier = len(missing_identifiers) < len(identifier_fields)

    matches = [
        index for index, offer in enumerate(candidates)
        if isinstance(offer, dict) and candidate_matches(claim, offer, as_of)
    ]
    if not has_identifier:
        verification = "unverified_no_offer_identifier"
    elif not matches:
        verification = "unverified_no_matching_candidate"
    elif len(matches) > 1:
        verification = "ambiguous_multiple_candidates"
    else:
        verification = "verified_candidate"

    status = get_account_status(customer)
    has_profile = customer.get("has_profile") is True
    has_account = bool(clean_text(customer.get("account_id")))
    identity_verified = customer.get("identity_verified") is True
    if verification != "verified_candidate":
        action = "do_not_apply_statement_credit"
    elif not has_profile or not has_account:
        action = "no_account_action_preapplicant_or_missing_account"
    elif not identity_verified:
        action = "identity_verification_required_before_account_action"
    else:
        action = "manual_eligibility_and_account_checks_required"

    steps = []
    if verification == "unverified_no_offer_identifier":
        steps.append("Request a non-sensitive product, campaign, or personalized flyer identifier.")
    elif verification == "unverified_no_matching_candidate":
        steps.append("Explain that available verified offers do not confirm the claim.")
    elif verification == "ambiguous_multiple_candidates":
        steps.append("Obtain a campaign or personalized identifier to distinguish candidate offers.")
    else:
        steps.append("Confirm invitation and customer eligibility outside this helper before relying on the candidate.")

    if not has_profile or not has_account:
        steps.append("Do not attempt a statement credit without an identified eligible card account.")
    elif not identity_verified:
        steps.append("Verify identity before any account-specific action.")
    else:
        steps.append("Confirm ownership, eligibility, qualification, and the exact credit before action.")

    wants_review = payload.get("customer_requests_honor_or_review") is True
    persisted = payload.get("persisted_after_unavailable_offer_refusal") is True
    demands_human = payload.get("explicit_human_transfer_demand") is True
    transfer = None
    if wants_review and verification != "verified_candidate":
        tier_one = persisted and demands_human
        reason = ("customer_demands_after_unavailable_offer_refusal" if tier_one
                  else "unconfirmed_external_communication")
        history = ("Customer persisted after unavailable-offer refusals and expressly demands a human. "
                   if tier_one else "Customer requests review of the unconfirmed external communication. ")
        identifiers = [field for field in identifier_fields if clean_text(claim.get(field))]
        transfer = {
            "reason": reason,
            "summary": (
                history + "Claimed terms: " + claimed_terms(claim) + ". "
                + "Provided identifiers: " + (", ".join(identifiers) if identifiers else "none") + ". "
                + "Available candidate data did not confirm the claim. "
                + account_sentence(status) + " No statement credit was applied."
            ),
        }

    return {
        "ok": True,
        "claim_verification": verification,
        "account_action": action,
        "account_status": status,
        "missing_identifiers": missing_identifiers,
        "candidate_match_indexes": matches,
        "next_steps": steps,
        "transfer": transfer,
    }


if __name__ == "__main__":
    try:
        source = sys.stdin.read()
        result = main(json.loads(source))
    except json.JSONDecodeError as exc:
        result = {"ok": False, "errors": ["invalid JSON input: %s" % exc.msg]}
    except Exception as exc:
        result = {"ok": False, "errors": ["assessment failed: %s" % str(exc)]}
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
