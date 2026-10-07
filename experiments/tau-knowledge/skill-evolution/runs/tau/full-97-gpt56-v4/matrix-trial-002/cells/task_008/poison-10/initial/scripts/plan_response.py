#!/usr/bin/env python3
"""Plan a safe response to a promotional statement-credit request.

Input JSON object:
  customer_located, identity_verified, card_account_confirmed, offer_matched
  (booleans); offer_claimed_amount and documented_amount (numbers or null);
  customer_continues_to_demand (boolean).
Output JSON object:
  status: no_credit | ready_for_eligibility_review | ready_for_application
  message: customer-facing text
  next_steps: ordered list of required actions
  transfer: optional transfer recommendation
"""
import json
import sys
from typing import Any, Dict, List


def is_true(data: Dict[str, Any], key: str) -> bool:
    return data.get(key) is True


def money(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"${value:,.2f}"
    return "the claimed amount"


def plan(data: Dict[str, Any]) -> Dict[str, Any]:
    located = is_true(data, "customer_located")
    verified = is_true(data, "identity_verified")
    account = is_true(data, "card_account_confirmed")
    matched = is_true(data, "offer_matched")
    demanding = is_true(data, "customer_continues_to_demand")
    claimed = data.get("offer_claimed_amount")
    documented = data.get("documented_amount")

    missing: List[str] = []
    if not located:
        missing.append("locate your banking profile using a supported identifier")
    if located and not verified:
        missing.append("complete identity verification")
    if verified and not account:
        missing.append("confirm the credit-card account and ownership")
    if account and not matched:
        missing.append("match the flyer to a documented offer for that card")

    amount_conflict = (
        isinstance(claimed, (int, float)) and not isinstance(claimed, bool)
        and isinstance(documented, (int, float)) and not isinstance(documented, bool)
        and claimed != documented
    )

    if missing:
        result: Dict[str, Any] = {
            "status": "no_credit",
            "message": (
                "I’m unable to apply or confirm a promotional statement credit yet. "
                "Before any account action, I need to " + "; then ".join(missing) + "."
            ),
            "next_steps": missing,
        }
    elif not matched or amount_conflict:
        detail = "The claimed offer could not be matched to a documented offer for the confirmed card."
        if amount_conflict:
            detail = (
                f"The available documentation supports {money(documented)}, not "
                f"{money(claimed)}, and does not establish the claimed offer."
            )
        result = {
            "status": "no_credit",
            "message": detail + " I cannot apply an unconfirmed promotional credit.",
            "next_steps": [
                "Obtain a product name and offer or invitation code, or escalate the unresolved offer claim.",
                "Do not apply a statement credit.",
            ],
        }
    else:
        result = {
            "status": "ready_for_eligibility_review",
            "message": (
                "The account and offer are identified. The qualifying net posted purchases, "
                "date window, and any fulfillment conditions must be reviewed before a credit can be applied."
            ),
            "next_steps": [
                "Review posted purchases less returns and credits within the qualifying period.",
                "Confirm all offer conditions and the documented credit amount.",
                "Apply only an earned documented credit using the normal statement-credit procedure.",
            ],
        }

    if demanding and result["status"] == "no_credit":
        result["transfer"] = {
            "reason": "customer_demands_after_unavailable_offer_refusal",
            "summary": (
                "Customer continues to demand a promotional statement credit after the offer "
                "could not be verified or applied. No statement credit was applied."
            ),
        }
    return result


def main() -> None:
    try:
        supplied = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON input: {exc.msg}"}))
        raise SystemExit(2)
    if not isinstance(supplied, dict):
        print(json.dumps({"error": "input must be a JSON object"}))
        raise SystemExit(2)
    print(json.dumps(plan(supplied), sort_keys=True))


if __name__ == "__main__":
    main()
