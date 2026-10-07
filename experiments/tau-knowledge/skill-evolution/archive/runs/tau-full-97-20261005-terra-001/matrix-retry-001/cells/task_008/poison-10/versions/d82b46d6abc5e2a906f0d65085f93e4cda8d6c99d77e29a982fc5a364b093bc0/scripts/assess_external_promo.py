#!/usr/bin/env python3
"""Conservatively classify an externally claimed credit-card promotion.

Reads one JSON object from stdin and writes one JSON object to stdout.
This utility is deliberately advisory: it never verifies identity, eligibility,
or invitation status and never performs a banking action.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def text(value):
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return None


def money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parsed_date(value):
    value = text(value)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def normalized(value):
    value = text(value)
    return value.casefold() if value else None


def required_object(container, key, errors):
    value = container.get(key)
    if not isinstance(value, dict):
        errors.append("'%s' must be an object" % key)
        return {}
    return value


def same_if_claimed(claim_value, candidate_value, converter=lambda x: x):
    """A candidate is incompatible only when a supplied claim conflicts."""
    left = converter(claim_value)
    if left is None:
        return True
    right = converter(candidate_value)
    return right is not None and left == right


def candidate_matches(claim, candidate, as_of):
    # Product is an identifier when supplied; campaigns are checked if both exist.
    if not same_if_claimed(claim.get("product"), candidate.get("product"), normalized):
        return False
    claim_campaign = normalized(claim.get("campaign_code"))
    candidate_campaign = normalized(candidate.get("campaign_code"))
    if claim_campaign is not None and candidate_campaign is not None and claim_campaign != candidate_campaign:
        return False
    if not same_if_claimed(claim.get("reward_type"), candidate.get("reward_type"), normalized):
        return False
    if not same_if_claimed(claim.get("reward_amount"), candidate.get("reward_amount"), money):
        return False
    if not same_if_claimed(claim.get("spend_amount"), candidate.get("spend_amount"), money):
        return False
    if not same_if_claimed(claim.get("period_months"), candidate.get("period_months"), number):
        return False

    if as_of is not None:
        start = parsed_date(candidate.get("offer_start"))
        end = parsed_date(candidate.get("offer_end"))
        if start is not None and as_of < start:
            return False
        if end is not None and as_of > end:
            return False
    return True


def main(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["top-level input must be an object"]}

    claim = required_object(payload, "claim", errors)
    customer = required_object(payload, "customer", errors)
    candidates = payload.get("candidate_offers", [])
    if not isinstance(candidates, list):
        errors.append("'candidate_offers' must be an array")
        candidates = []
    if errors:
        return {"ok": False, "errors": errors}

    as_of_value = payload.get("as_of")
    as_of = parsed_date(as_of_value)
    if as_of_value is not None and text(as_of_value) is not None and as_of is None:
        return {"ok": False, "errors": ["'as_of' must be YYYY-MM-DD or null"]}

    missing_identifiers = []
    if not text(claim.get("product")):
        missing_identifiers.append("product")
    if not text(claim.get("campaign_code")):
        missing_identifiers.append("campaign_code")
    if not text(claim.get("personalized_identifier")):
        missing_identifiers.append("personalized_identifier")

    matches = []
    for index, candidate in enumerate(candidates):
        if isinstance(candidate, dict) and candidate_matches(claim, candidate, as_of):
            matches.append(index)

    has_offer_identifier = bool(
        text(claim.get("product"))
        or text(claim.get("campaign_code"))
        or text(claim.get("personalized_identifier"))
    )
    # A candidate is only a possible verification. Personalized/invitation
    # eligibility and any internal promotion lookup remain external checks.
    if not has_offer_identifier:
        verification = "unverified_no_offer_identifier"
    elif len(matches) == 0:
        verification = "unverified_no_matching_candidate"
    elif len(matches) > 1:
        verification = "ambiguous_multiple_candidates"
    else:
        verification = "verified_candidate"

    has_profile = customer.get("has_profile") is True
    has_account = bool(text(customer.get("account_id")))
    identity_verified = customer.get("identity_verified") is True
    if verification != "verified_candidate":
        account_action = "do_not_apply_statement_credit"
    elif not has_profile or not has_account:
        account_action = "no_account_action_preapplicant_or_missing_account"
    elif not identity_verified:
        account_action = "identity_verification_required_before_account_action"
    else:
        account_action = "manual_eligibility_and_account_checks_required"

    next_steps = []
    if verification == "unverified_no_offer_identifier":
        next_steps.append("Request a non-sensitive product, campaign, or personalized offer identifier.")
    elif verification == "unverified_no_matching_candidate":
        next_steps.append("Explain that available verified offers do not confirm the claim.")
    elif verification == "ambiguous_multiple_candidates":
        next_steps.append("Obtain a campaign or personalized identifier to distinguish the candidate offers.")
    else:
        next_steps.append("Confirm invitation and customer eligibility outside this helper before relying on the candidate.")

    if not has_profile or not has_account:
        next_steps.append("Do not attempt a statement credit without an identified eligible card account.")
    elif not identity_verified:
        next_steps.append("Verify identity and log verification before any account-specific action.")
    else:
        next_steps.append("Confirm account ownership, product eligibility, terms, and qualification before any credit action.")

    wants_review = payload.get("customer_requests_honor_or_review") is True
    transfer = None
    if wants_review and verification != "verified_candidate":
        transfer = {
            "reason": "unconfirmed_external_communication",
            "summary": (
                "Customer requests review of a claimed external credit-card promotion. "
                "The claim could not be confirmed from supplied identifiers and candidate offer data. "
                "No statement credit has been applied."
            ),
        }

    return {
        "ok": True,
        "claim_verification": verification,
        "account_action": account_action,
        "missing_identifiers": missing_identifiers,
        "candidate_match_indexes": matches,
        "next_steps": next_steps,
        "transfer": transfer,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        result = {"ok": False, "errors": ["invalid JSON input: %s" % exc.msg]}
    except Exception as exc:  # Defensive serialization for stdin/runtime failures.
        result = {"ok": False, "errors": ["unable to read input: %s" % str(exc)]}
    else:
        try:
            result = main(payload)
        except Exception as exc:  # Never expose a partial assessment as successful.
            result = {"ok": False, "errors": ["assessment failed: %s" % str(exc)]}
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
