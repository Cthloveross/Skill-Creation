#!/usr/bin/env python3
"""Validate normalized prerequisites for debit protection and credit replacement.

Input JSON schema:
{
  "user_id": str,
  "identity_verified": bool,
  "requested_debit_action": "freeze" | "unfreeze" | "close",
  "requested_card_ids": [str],
  "debit_cards": [{"card_id": str, "user_id": str, "account_id": str,
                   "status": str, "date_issued": optional str}],
  "accounts": [{"account_id": str, "account_type": str, "status": str}],
  "credit_replacement": {
    "requested": bool, "card_in_wallet": bool, "eligibility_confirmed": bool,
    "account_id": str, "reason": str, "shipping_address": str,
    "shipping_speed": "standard" | "expedited",
    "fee_acknowledged": bool
  }
}

Output JSON contains a `debit` result for every requested card and a `credit_replacement`
result. `ready` only means supplied structured prerequisites are complete; the executor must
still obtain explicit consent, use live lookup results, and execute the proper banking tool.
"""
import json
import sys

REPLACEMENT_REASONS = {
    "fraud_suspected", "lost", "stolen", "damaged", "expired", "other"
}


def text(value):
    return value if isinstance(value, str) else ""


def main(payload):
    user_id = text(payload.get("user_id"))
    verified = payload.get("identity_verified") is True
    action = text(payload.get("requested_debit_action")).lower()
    cards = payload.get("debit_cards") if isinstance(payload.get("debit_cards"), list) else []
    accounts = payload.get("accounts") if isinstance(payload.get("accounts"), list) else []
    requested = payload.get("requested_card_ids")
    requested = requested if isinstance(requested, list) else []
    by_card_id = {text(c.get("card_id")): c for c in cards if isinstance(c, dict) and text(c.get("card_id"))}
    by_account_id = {text(a.get("account_id")): a for a in accounts if isinstance(a, dict)}

    debit_results = []
    if action not in {"freeze", "unfreeze", "close"}:
        debit_results.append({"status": "blocked", "reasons": ["requested_debit_action must be freeze, unfreeze, or close"]})
    elif not requested:
        debit_results.append({"status": "blocked", "reasons": ["no requested_card_ids supplied"]})
    else:
        required_status = {"freeze": "ACTIVE", "unfreeze": "FROZEN"}.get(action)
        for card_id in requested:
            card = by_card_id.get(text(card_id))
            reasons = []
            if not verified:
                reasons.append("identity is not verified")
            if not user_id:
                reasons.append("verified user_id is missing")
            if card is None:
                reasons.append("card was not found in supplied debit-card lookup data")
            else:
                if text(card.get("user_id")) != user_id:
                    reasons.append("card ownership does not match verified user")
                status = text(card.get("status")).upper()
                if required_status and status != required_status:
                    reasons.append("card status must be %s for %s" % (required_status, action))
                if action == "close" and status not in {"ACTIVE", "PENDING"}:
                    reasons.append("card status must be ACTIVE or PENDING for closure")
                if action == "unfreeze":
                    account = by_account_id.get(text(card.get("account_id")))
                    if account is None:
                        reasons.append("linked account was not found in supplied account lookup data")
                    elif text(account.get("status")).upper() != "OPEN":
                        reasons.append("linked checking account must be OPEN for unfreezing")
            debit_results.append({
                "card_id": text(card_id),
                "action": action,
                "status": "blocked" if reasons else "ready",
                "reasons": reasons,
            })

    credit = payload.get("credit_replacement")
    credit = credit if isinstance(credit, dict) else {}
    credit_result = {"status": "not_requested", "reasons": []}
    if credit.get("requested") is True:
        reasons = []
        if not verified:
            reasons.append("identity is not verified")
        if credit.get("card_in_wallet") is not True:
            reasons.append("credit card in wallet has not been confirmed")
        if credit.get("eligibility_confirmed") is not True:
            reasons.append("replacement eligibility has not been confirmed")
        if not text(credit.get("account_id")):
            reasons.append("credit-card account identifier is missing")
        if text(credit.get("reason")) not in REPLACEMENT_REASONS:
            reasons.append("replacement reason is missing or unsupported")
        if not text(credit.get("shipping_address")):
            reasons.append("confirmed shipping address is missing")
        speed = text(credit.get("shipping_speed")).lower()
        if speed not in {"standard", "expedited"}:
            reasons.append("shipping speed must be standard or expedited")
        if speed == "expedited" and credit.get("fee_acknowledged") is not True:
            reasons.append("expedited fee acknowledgement is required")
        credit_result = {"status": "blocked" if reasons else "ready", "reasons": reasons}

    return {"debit": debit_results, "credit_replacement": credit_result}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}))
        sys.exit(2)
