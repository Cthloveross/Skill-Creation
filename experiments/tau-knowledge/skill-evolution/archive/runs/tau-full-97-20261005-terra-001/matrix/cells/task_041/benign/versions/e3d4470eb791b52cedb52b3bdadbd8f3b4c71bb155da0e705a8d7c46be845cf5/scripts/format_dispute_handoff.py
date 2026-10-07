#!/usr/bin/env python3
"""Create a complete, non-filing human-handoff summary for blocked card disputes.

Input is a JSON object:
{
  "customer_name": "string",
  "user_id": "string (optional)",
  "issue_noticed_date": "MM/DD/YYYY",
  "resolution_requested": "full_refund|partial_refund|reversal_of_charge",
  "card_action": "keep_active|cancel_and_reissue",
  "last_four_status": "unavailable|customer_not_provided|retrieved",
  "dispute_history_retrieved": true,
  "transactions": [{
    "transaction_id": "string", "merchant": "string", "card_type": "string",
    "amount": "string or number", "purchase_date": "MM/DD/YYYY",
    "contacted_merchant": true, "dispute_reason": "supported reason code"
  }]
}

It emits {"ready": bool, "errors": [...], "summary": string}. It does not call
banking tools and never receives or prints card last-four digits.
"""
import json
import sys

REASONS = {
    "unauthorized_fraudulent_charge": "unauthorized",
    "duplicate_charge": "duplicate",
    "incorrect_amount": "incorrect amount",
    "goods_services_not_received": "goods/services not received",
    "goods_services_not_as_described": "not as described",
    "canceled_subscription_still_charging": "after cancellation",
    "refund_never_processed": "refund never processed",
}
RESOLUTIONS = {"full_refund": "full refund", "partial_refund": "partial refund", "reversal_of_charge": "reversal of charge"}
ACTIONS = {"keep_active": "keep all cards active", "cancel_and_reissue": "cancel and reissue affected cards"}
STATUSES = {"unavailable", "customer_not_provided", "retrieved"}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def main(data):
    errors = []
    if not isinstance(data, dict):
        return {"ready": False, "errors": ["input must be a JSON object"], "summary": ""}
    if not nonempty(data.get("customer_name")):
        errors.append("customer_name is required")
    if not nonempty(data.get("issue_noticed_date")):
        errors.append("issue_noticed_date is required")
    if data.get("resolution_requested") not in RESOLUTIONS:
        errors.append("resolution_requested is unsupported")
    if data.get("card_action") not in ACTIONS:
        errors.append("card_action is unsupported")
    if data.get("last_four_status") not in STATUSES:
        errors.append("last_four_status must state retrieved, unavailable, or customer_not_provided")
    if not isinstance(data.get("dispute_history_retrieved"), bool):
        errors.append("dispute_history_retrieved must be a boolean")
    transactions = data.get("transactions")
    if not isinstance(transactions, list) or not transactions:
        errors.append("transactions must be a nonempty list")
        transactions = []

    records = []
    seen_ids = set()
    for number, transaction in enumerate(transactions, 1):
        if not isinstance(transaction, dict):
            errors.append("transactions[%d] must be an object" % (number - 1))
            continue
        required = ("transaction_id", "merchant", "card_type", "amount", "purchase_date")
        missing = [field for field in required if not nonempty(str(transaction.get(field, "")).strip())]
        if missing:
            errors.append("transactions[%d] missing %s" % (number - 1, ", ".join(missing)))
            continue
        transaction_id = transaction["transaction_id"].strip()
        if transaction_id in seen_ids:
            errors.append("duplicate transaction_id: %s" % transaction_id)
        seen_ids.add(transaction_id)
        reason = transaction.get("dispute_reason")
        if reason not in REASONS:
            errors.append("transactions[%d] has unsupported dispute_reason" % (number - 1))
            continue
        contacted = transaction.get("contacted_merchant")
        if not isinstance(contacted, bool):
            errors.append("transactions[%d].contacted_merchant must be boolean" % (number - 1))
            continue
        contact_text = "contacted merchant" if contacted else "did not contact merchant"
        records.append(
            "%d. ID %s | %s | %s | %s on %s | %s; %s (%s)." % (
                number, transaction_id, transaction["merchant"].strip(), transaction["card_type"].strip(),
                str(transaction["amount"]).strip(), transaction["purchase_date"].strip(),
                REASONS[reason], reason, contact_text
            )
        )

    if errors:
        return {"ready": False, "errors": errors, "summary": ""}

    count = len(records)
    history_text = "Dispute history was retrieved before transfer." if data["dispute_history_retrieved"] else "Dispute history was not retrieved; human agent must retrieve it before any provisional-credit decision."
    if data["last_four_status"] == "retrieved":
        blocker = "No card last four digits are included in this handoff; the human agent must use the authorized card-specific record when continuing."
    else:
        blocker = "Required last four digits could not be retrieved through the authorized account-ID lookup and were not supplied by the customer; they cannot be used or inferred from another card, prior dispute, or record. No formal filings were submitted while required last four digits were missing."
    user_text = (" User ID: %s." % data["user_id"].strip()) if nonempty(data.get("user_id")) else ""
    summary = (
        "%s%s requests continuation of %d posted transactions. Issue noticed date: %s. "
        "Requested resolution: %s. Card preference: %s. %s %s Continuation records: %s"
        % (data["customer_name"].strip(), user_text, count, data["issue_noticed_date"].strip(),
           RESOLUTIONS[data["resolution_requested"]], ACTIONS[data["card_action"]],
           history_text, blocker, " ".join(records))
    )
    return {"ready": True, "errors": [], "summary": summary}


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        result = {"ready": False, "errors": ["invalid JSON: %s" % exc.msg], "summary": ""}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
