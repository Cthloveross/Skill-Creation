#!/usr/bin/env python3
"""Assess what can safely be stated for an international-card readiness reply.

Input JSON object (all fields optional booleans):
  card_is_activated, destination_known, dates_known, customer_can_check_app
Output JSON object with supported recommendations and documented limitations.
"""
import json
import sys


def bool_or_unknown(value):
    return value if isinstance(value, bool) else None


def main():
    try:
        supplied = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "Input must be one valid JSON object.", "detail": str(exc)}))
        return
    if not isinstance(supplied, dict):
        print(json.dumps({"error": "Input must be a JSON object."}))
        return

    activated = bool_or_unknown(supplied.get("card_is_activated"))
    destination_known = bool_or_unknown(supplied.get("destination_known"))
    dates_known = bool_or_unknown(supplied.get("dates_known"))
    app_check = bool_or_unknown(supplied.get("customer_can_check_app"))

    result = {
        "travel_notice_workflow_documented": False,
        "may_claim_travel_notice_channel": False,
        "may_claim_travel_notice_lead_time": False,
        "may_claim_travel_notice_required": False,
        "documented_preparation": [
            "Enable transaction and international-use alerts if available in the account.",
            "Keep contact details current for fraud-verification prompts.",
            "Watch for and respond promptly to unusual-activity verification alerts.",
        ],
        "documented_product_facts": {
            "foreign_transaction_fee_percent": 0,
            "real_time_fraud_monitoring": True,
            "risky_transaction_can_prompt_verification": True,
        },
        "context": {
            "card_is_activated": activated,
            "destination_known": destination_known,
            "dates_known": dates_known,
            "customer_can_check_app": app_check,
        },
        "response_notes": [],
    }
    if activated is True:
        result["response_notes"].append("The cardholder reports the card is active; do not infer a travel-notice workflow from this.")
    if dates_known is False:
        result["response_notes"].append("Dates are not finalized, but no documented rule says dates are needed or specifies advance notice.")
    if app_check is False:
        result["response_notes"].append("Do not direct the customer to check the app again or claim an alternative form or channel.")
    if destination_known is True:
        result["response_notes"].append("A known destination does not establish that a travel notice can or must be submitted.")

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
