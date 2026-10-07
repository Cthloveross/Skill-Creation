#!/usr/bin/env python3
"""Create a factual human-transfer recommendation from supplied case facts.

Input JSON:
{
  "issues": {
    "fraud_or_unauthorized": bool,
    "security_concern": bool,
    "lost_or_stolen_card": bool,
    "account_closure_request": bool,
    "complex_billing_dispute": bool,
    "legal_or_regulatory_matter": bool,
    "account_ownership_dispute": bool,
    "technical_system_error": bool,
    "specialized_department_required": bool,
    "accessibility_or_special_needs": bool,
    "customer_frustrated": bool,
    "supervisor_service_complaint": bool,
    "human_requested": bool
  },
  "requested_actions": ["..."],
  "verification_state": "verified|partially_verified|not_verified|unknown",
  "reported_disputes": ["..."],
  "actions_completed": ["..."]
}

Output JSON contains a transfer reason, a concise factual summary, and warnings.
"""
import json
import sys


def truth(d, key):
    return bool(d.get(key, False))


def choose_reason(i):
    # Ordered from the documented highest applicable tier to lowest.
    if any(truth(i, k) for k in ("fraud_or_unauthorized", "security_concern", "lost_or_stolen_card")):
        return "fraud_or_security_concern"
    if truth(i, "account_closure_request"):
        return "account_closure_request"
    if truth(i, "legal_or_regulatory_matter"):
        return "legal_or_regulatory_matter"
    if truth(i, "account_ownership_dispute"):
        return "account_ownership_dispute"
    if truth(i, "complex_billing_dispute"):
        return "complex_billing_dispute"
    if truth(i, "technical_system_error"):
        return "technical_system_error"
    if truth(i, "specialized_department_required"):
        return "specialized_department_required"
    if truth(i, "accessibility_or_special_needs"):
        return "accessibility_or_special_needs"
    if truth(i, "supervisor_service_complaint"):
        return "supervisor_request_service_complaint"
    if truth(i, "customer_frustrated") and truth(i, "human_requested"):
        return "customer_frustrated_demands_human"
    if truth(i, "human_requested"):
        return "customer_requests_human_no_specific_reason"
    return "other"


def string_list(value, label, warnings):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
        warnings.append(label + " must be an array of nonempty strings; it was omitted.")
        return []
    return [x.strip() for x in value]


def main(data):
    warnings = []
    issues = data.get("issues", {})
    if not isinstance(issues, dict):
        issues = {}
        warnings.append("issues must be an object; no issue flags were accepted.")
    requested = string_list(data.get("requested_actions"), "requested_actions", warnings)
    disputes = string_list(data.get("reported_disputes"), "reported_disputes", warnings)
    completed = string_list(data.get("actions_completed"), "actions_completed", warnings)
    verification = data.get("verification_state", "unknown")
    if verification not in {"verified", "partially_verified", "not_verified", "unknown"}:
        warnings.append("verification_state was not recognized and was recorded as unknown.")
        verification = "unknown"

    reason = choose_reason(issues)
    parts = ["Customer requests human assistance."] if truth(issues, "human_requested") else []
    if disputes:
        parts.append("Reported dispute issue(s): " + "; ".join(disputes) + ".")
    if truth(issues, "lost_or_stolen_card"):
        parts.append("Customer reports a lost or stolen debit card; security and replacement/closure assistance may be needed.")
    if truth(issues, "fraud_or_unauthorized"):
        parts.append("Customer reports unauthorized activity or suspected fraud.")
    if requested:
        parts.append("Requested actions: " + "; ".join(requested) + ".")
    parts.append("Verification state: " + verification + ".")
    if completed:
        parts.append("Completed before transfer: " + "; ".join(completed) + ".")
    else:
        parts.append("No banking action is represented as completed by this handoff.")
    parts.append("Specialist should confirm transaction, account, card, eligibility, and dispute-documentation details before any action.")
    if reason == "other":
        warnings.append("No documented reason flag was supplied; add a detailed case explanation before transfer.")
    return {"reason": reason, "summary": " ".join(parts), "warnings": warnings}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(raw), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"reason": "other", "summary": "Unable to build handoff summary.", "warnings": [str(exc)]}, separators=(",", ":")))
