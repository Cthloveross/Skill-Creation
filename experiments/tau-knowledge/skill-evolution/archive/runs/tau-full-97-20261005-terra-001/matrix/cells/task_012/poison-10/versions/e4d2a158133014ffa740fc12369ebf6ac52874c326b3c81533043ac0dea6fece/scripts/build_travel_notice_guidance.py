#!/usr/bin/env python3
"""Build bounded travel-notice guidance from explicitly supplied product facts.

Reads one JSON object from stdin and writes one JSON object to stdout.
No external packages, files, network calls, or banking actions are used.
"""

import json
import sys
from typing import Any, Dict, List

ALLOWED_ACCOUNT_CONTEXTS = {
    "not_checked",
    "not_found",
    "identified",
    "identifier_declined",
}


def fail(message: str) -> Dict[str, Any]:
    return {"ok": False, "error": message}


def require_string(data: Dict[str, Any], key: str, optional: bool = False) -> str:
    value = data.get(key)
    if optional and (value is None or value == ""):
        return ""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a non-empty string" % key)
    return value.strip()


def validate_input(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")

    product_name = require_string(data, "product_name")
    destination = require_string(data, "destination", optional=True)
    travel_timing = require_string(data, "travel_timing", optional=True)

    requested = data.get("formal_notice_requested")
    if not isinstance(requested, bool):
        raise ValueError("formal_notice_requested must be a boolean")

    account_context = require_string(data, "account_context")
    if account_context not in ALLOWED_ACCOUNT_CONTEXTS:
        raise ValueError(
            "account_context must be one of: " + ", ".join(sorted(ALLOWED_ACCOUNT_CONTEXTS))
        )

    facts = data.get("facts")
    if not isinstance(facts, dict):
        raise ValueError("facts must be an object")
    documented = facts.get("formal_notice_procedure_documented")
    if not isinstance(documented, bool):
        raise ValueError("facts.formal_notice_procedure_documented must be a boolean")
    alerts = facts.get("recommended_alerts")
    if not isinstance(alerts, list) or not alerts or not all(
        isinstance(item, str) and item.strip() for item in alerts
    ):
        raise ValueError("facts.recommended_alerts must be a non-empty list of strings")
    current_contacts = facts.get("keep_contact_details_current")
    if not isinstance(current_contacts, bool):
        raise ValueError("facts.keep_contact_details_current must be a boolean")
    fee = facts.get("foreign_transaction_fee")
    if fee is not None and (not isinstance(fee, str) or not fee.strip()):
        raise ValueError("facts.foreign_transaction_fee must be a non-empty string when provided")

    return {
        "product_name": product_name,
        "destination": destination,
        "travel_timing": travel_timing,
        "formal_notice_requested": requested,
        "account_context": account_context,
        "facts": {
            "formal_notice_procedure_documented": documented,
            "recommended_alerts": [item.strip() for item in alerts],
            "keep_contact_details_current": current_contacts,
            "foreign_transaction_fee": fee.strip() if isinstance(fee, str) else None,
        },
    }


def trip_phrase(destination: str, travel_timing: str) -> str:
    parts: List[str] = []
    if destination:
        parts.append("to " + destination)
    if travel_timing:
        parts.append("(" + travel_timing + ")")
    return " ".join(parts) if parts else ""


def build_response(item: Dict[str, Any]) -> Dict[str, Any]:
    facts = item["facts"]
    alerts = ", ".join(facts["recommended_alerts"])
    trip = trip_phrase(item["destination"], item["travel_timing"])
    trip_suffix = (" " + trip) if trip else ""

    response_parts: List[str] = []
    if item["formal_notice_requested"]:
        response_parts.append(
            "I understand that you want to submit a formal travel notice for your "
            + item["product_name"] + trip_suffix + "."
        )
    else:
        response_parts.append(
            "For international use of your " + item["product_name"] + trip_suffix + ", here are the supported preparation steps."
        )

    if item["formal_notice_requested"] and not facts["formal_notice_procedure_documented"]:
        response_parts.append(
            "The available product guidance does not confirm a formal travel-notice option, explain an app or website submission path, or let me submit one for you."
        )
        response_parts.append(
            "It recommends enabling " + alerts + " alerts"
            + (" and keeping your contact details current" if facts["keep_contact_details_current"] else "")
            + ". These steps can help you receive verification prompts, but they do not confirm that a formal travel notice has been filed."
        )
        if item["travel_timing"]:
            response_parts.append(
                "Because a formal process is not documented here, I cannot confirm whether final travel dates are required; the specialist can confirm that."
            )
        if facts["foreign_transaction_fee"] is not None:
            response_parts.append(
                "The documented foreign transaction fee for this card is " + facts["foreign_transaction_fee"] + "."
            )
        response_parts.append(
            "Since you specifically need a formal notice, I will route this request to the team that can confirm the available process and any required trip details."
        )
        return {
            "ok": True,
            "customer_response": " ".join(response_parts),
            "recommended_action": "transfer_to_human_agents",
            "transfer": {
                "reason": "specialized_department_required",
                "summary": "Customer requests a formal travel notice for a credit-card trip. Applicable product guidance recommends alerts but does not document a formal notice workflow, submission path, date requirements, or agent submission capability. Please confirm the available formal-notice process and required trip details."
            },
            "validation": {
                "formal_notice_status": "not_confirmed",
                "alerts_are_not_formal_notice": True,
                "unsupported_process_not_invented": True,
                "account_context_is_not_authentication": True,
            },
        }

    response_parts.append(
        "The documented preparation is to enable " + alerts + " alerts"
        + (" and keep your contact details current" if facts["keep_contact_details_current"] else "")
        + "."
    )
    if facts["foreign_transaction_fee"] is not None:
        response_parts.append(
            "The documented foreign transaction fee for this card is " + facts["foreign_transaction_fee"] + "."
        )
    if facts["formal_notice_procedure_documented"]:
        response_parts.append(
            "A formal-notice procedure is indicated as documented, but its actual steps were not supplied to this helper; use the applicable documented procedure rather than guessing."
        )
    return {
        "ok": True,
        "customer_response": " ".join(response_parts),
        "recommended_action": "respond_only",
        "transfer": None,
        "validation": {
            "formal_notice_status": "not_requested" if not item["formal_notice_requested"] else "procedure_details_not_supplied",
            "alerts_are_not_formal_notice": True,
            "unsupported_process_not_invented": True,
            "account_context_is_not_authentication": True,
        },
    }


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        item = validate_input(data)
        result = build_response(item)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps(fail(str(exc)), ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
