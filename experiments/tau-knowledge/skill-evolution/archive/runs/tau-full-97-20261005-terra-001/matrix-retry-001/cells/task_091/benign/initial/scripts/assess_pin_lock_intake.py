#!/usr/bin/env python3
"""Assess PIN-lock request intake without exposing identity values.

Reads one JSON object from stdin and writes one JSON object to stdout.
See SKILL.md for the schema and interpretation.
"""
import json
import re
import sys

ALLOWED_FIELDS = {"date_of_birth", "address", "email", "phone_number"}


def normalize(field, value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    if field == "phone_number":
        return re.sub(r"\D", "", value)
    if field == "date_of_birth":
        digits = re.sub(r"\D", "", value)
        return digits if len(digits) == 8 else value.casefold()
    # Formatting/case variation should not cause a false address/email mismatch.
    return re.sub(r"\s+", " ", value).casefold()


def invalid(message):
    return {"verification_status": "invalid_input", "permitted_next_stage": "correct_input", "message": message}


def main(payload):
    if not isinstance(payload, dict):
        return invalid("Input must be a JSON object.")
    fields = payload.get("identity_fields")
    if not isinstance(fields, dict):
        return invalid("identity_fields must be an object.")
    unknown = set(fields) - ALLOWED_FIELDS
    if unknown:
        return invalid("identity_fields contains unsupported field names.")

    for count_name in ("requested_cards", "pin_locked_cards_observed"):
        count = payload.get(count_name, 0)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return invalid(count_name + " must be a nonnegative integer.")

    matched, conflicting, unavailable = [], [], []
    for name, pair in fields.items():
        if not isinstance(pair, dict):
            return invalid("Each identity field must contain provided and profile values.")
        supplied = normalize(name, pair.get("provided"))
        profile = normalize(name, pair.get("profile"))
        if supplied is None or profile is None:
            unavailable.append(name)
        elif supplied == profile:
            matched.append(name)
        else:
            conflicting.append(name)

    result = {
        "matching_fields": sorted(matched),
        "conflicting_fields": sorted(conflicting),
        "unavailable_fields": sorted(unavailable),
        "requested_cards": payload.get("requested_cards", 0),
        "pin_locked_cards_observed": payload.get("pin_locked_cards_observed", 0),
    }
    if len(matched) >= 2:
        result.update({
            "verification_status": "verified",
            "permitted_next_stage": "log_verification_then_investigate_all_locked_cards",
            "multi_card_investigation_required": payload.get("pin_locked_cards_observed", 0) > 1,
        })
    elif conflicting:
        result.update({
            "verification_status": "failed",
            "permitted_next_stage": "transfer_to_human",
            "transfer_reason": "account_ownership_dispute",
            "transfer_summary": "Customer requested PIN-lock assistance, but identity verification could not be completed; no account or card action was taken.",
            "multi_card_investigation_required": False,
        })
    else:
        result.update({
            "verification_status": "insufficient",
            "permitted_next_stage": "obtain_additional_identity_field",
            "multi_card_investigation_required": False,
        })
    return result


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), sort_keys=True))
    except json.JSONDecodeError:
        print(json.dumps(invalid("stdin must contain valid JSON."), sort_keys=True))
    except Exception:
        print(json.dumps(invalid("Unable to assess the supplied intake data."), sort_keys=True))
