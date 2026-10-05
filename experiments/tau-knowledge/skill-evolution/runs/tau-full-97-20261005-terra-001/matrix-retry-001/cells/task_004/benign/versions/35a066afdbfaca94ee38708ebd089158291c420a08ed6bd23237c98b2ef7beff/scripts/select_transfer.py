#!/usr/bin/env python3
"""Validate transfer candidates and construct a transfer-tool payload.

Reads one JSON object from stdin and writes one JSON object to stdout.
No banking action is performed by this script.
"""

import json
import sys

TIERS = {
    1: {
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
    },
    2: {
        "unconfirmed_external_communication",
        "kb_search_unsuccessful_customer_requests_transfer",
        "specialized_department_required",
        "accessibility_or_special_needs",
    },
    3: {
        "customer_frustrated_demands_human",
        "supervisor_request_service_complaint",
        "customer_requests_human_no_specific_reason",
        "request_completed_customer_wants_human_followup",
    },
    4: {"other"},
}
REASON_TO_TIER = {reason: tier for tier, reasons in TIERS.items() for reason in reasons}


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def error(message):
    emit({"status": "error", "message": message})


def clean_text(value, field, required=True):
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = " ".join(value.split())
    if required and not value:
        raise ValueError(f"{field} must not be empty")
    return value


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level input must be a JSON object")

    intended = payload.get("transfer_intended")
    if not isinstance(intended, bool):
        raise ValueError("transfer_intended must be a boolean")
    if not intended:
        emit({
            "status": "ok",
            "transfer_recommended": False,
            "reason": None,
            "summary": None,
            "message": "Transfer is not intended; no transfer payload was created.",
        })
        return

    candidates = payload.get("applicable_reasons", [])
    if not isinstance(candidates, list) or not all(isinstance(x, str) for x in candidates):
        raise ValueError("applicable_reasons must be an array of reason-code strings")
    if len(set(candidates)) != len(candidates):
        raise ValueError("applicable_reasons must not contain duplicates")
    unknown = sorted(set(candidates) - set(REASON_TO_TIER))
    if unknown:
        raise ValueError("unsupported reason code(s): " + ", ".join(unknown))

    # Tier 4 is a catch-all, so it cannot be justified alongside a listed reason.
    non_other = [reason for reason in candidates if reason != "other"]
    if "other" in candidates and non_other:
        raise ValueError("other cannot be combined with a specific applicable reason")

    if not candidates:
        selected = "other"
    else:
        top_tier = min(REASON_TO_TIER[reason] for reason in candidates)
        highest = sorted(reason for reason in candidates if REASON_TO_TIER[reason] == top_tier)
        if len(highest) != 1:
            raise ValueError(
                "multiple reasons occur in the highest applicable tier; select the direct documented cause before transfer"
            )
        selected = highest[0]

    issue = clean_text(payload.get("issue"), "issue")
    blocker = clean_text(payload.get("blocker"), "blocker")
    attempted = payload.get("attempted", [])
    if not isinstance(attempted, list) or not all(isinstance(item, str) for item in attempted):
        raise ValueError("attempted must be an array of strings")
    attempts = [" ".join(item.split()) for item in attempted if " ".join(item.split())]
    attempt_text = "; ".join(attempts) if attempts else "No completed attempts were supplied"

    summary = (
        f"Customer requested human assistance for: {issue}. "
        f"Attempts before transfer: {attempt_text}. "
        f"Blocker/outcome: {blocker}."
    )
    emit({
        "status": "ok",
        "transfer_recommended": True,
        "reason": selected,
        "reason_tier": REASON_TO_TIER[selected],
        "summary": summary,
    })


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("stdin must contain a JSON object")
        main(json.loads(raw))
    except json.JSONDecodeError as exc:
        error("invalid JSON input: " + str(exc))
    except ValueError as exc:
        error(str(exc))
    except Exception as exc:  # Defensive structured failure for the isolated runtime.
        error("unexpected script failure: " + str(exc))
