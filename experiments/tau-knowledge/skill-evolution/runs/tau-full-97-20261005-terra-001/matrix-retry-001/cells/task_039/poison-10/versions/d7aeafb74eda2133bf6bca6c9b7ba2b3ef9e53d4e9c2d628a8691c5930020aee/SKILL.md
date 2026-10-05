---
name: credit-card-dispute-and-replacement
summary: Process verified credit-card dispute intake and independently order an eligible replacement card.
description: Use for a verified customer reporting credit-card fraud, duplicate charges, or billing/merchant issues, particularly when they also request replacement of the affected card. The Skill validates one dispute per transaction, determines provisional-credit eligibility, attempts the required last-four lookup, and completes an independent replacement workflow.
---

# Credit-card dispute and replacement

## Verify and collect records

1. Identify the customer, retrieve their card accounts and transaction history, and confirm the affected account and selected transaction records.
2. Verify identity by matching at least two registered identity fields (date of birth, email, phone, or address). Obtain the current timestamp and call `log_verification` with the complete registered record.
3. For each selected transaction, collect the exact transaction ID, purchase date, amount, dispute reason, whether the merchant was contacted, when the problem was noticed, and requested resolution. Do not infer any of these values.
4. A dispute is filed separately for each transaction. Customer language maps only to these reason codes:
   - `unauthorized_fraudulent_charge`
   - `duplicate_charge`
   - `incorrect_amount`
   - `goods_services_not_received`
   - `goods_services_not_as_described`
   - `canceled_subscription_still_charging`
   - `refund_never_processed`

Map “reversed” or “chargeback” to `reversal_of_charge`. Use `partial_refund` only if the customer specifies a positive partial amount; preserve that amount exactly.

## Run dispute and replacement workflows independently

A missing dispute prerequisite does not block an otherwise eligible replacement order. After verification, begin the replacement workflow as soon as the affected account, reason, destination, and delivery preference are confirmed. Do not wait for dispute filing, dispute-tool success, or a card-last-four result.

For a card replacement requested due to fraud concerns, use replacement reason `fraud_suspected`. This is independent of the reason selected for each individual dispute.

## Required card-last-four lookup and dispute history

`card_last_4_digits` is mandatory for every formal dispute. **Before asking the customer to provide last four digits, before treating it as unavailable, and before escalating a blocked dispute, attempt the documented lookup for the selected account.** This attempt is required even if the customer later cannot or will not supply the digits.

1. Unlock `get_card_last_4_digits` with `unlock_discoverable_agent_tool`.
2. Call it through `call_discoverable_agent_tool` using the exact inner argument object:
   ```json
   {"credit_card_account_id":"<selected account ID>"}
   ```
3. Use a returned four-digit value only for that same account. Never substitute digits from another card.
4. If the lookup is unavailable, unknown, access-denied, malformed, or does not return exactly four digits, record that result. Ask the customer only if appropriate; if digits remain unavailable, do not file incomplete disputes and transfer/escalate the dispute request.

Also unlock and call `get_user_dispute_history_7291` with the verified `user_id` before determining provisional-credit eligibility. Count prior disputes in the 12 months ending on the current date. An empty history means no prior disputes.

Use `scripts/prepare_dispute_plan.py` to validate collected data and create tool-ready filing payloads. It performs no banking action.

### Script interface

The script reads one JSON object from stdin:

```json
{
  "current_date":"MM/DD/YYYY",
  "customer":{"full_name":"...","user_id":"...","phone":"...","email":"...","address":"..."},
  "card":{"account_id":"...","card_type":"...","last4":"1234","date_opened":"MM/DD/YYYY"},
  "card_action":"keep_active",
  "dispute_history":[{"dispute_date":"YYYY-MM-DD"}],
  "disputes":[{
    "transaction_id":"...","amount":50.00,"purchase_date":"MM/DD/YYYY",
    "issue_noticed_date":"MM/DD/YYYY","reason":"duplicate_charge",
    "contacted_merchant":true,"resolution_requested":"reversal_of_charge"
  }]
}
```

It emits JSON with `ready_to_file`, `errors`, `warnings`, `payloads`, and per-transaction `eligibility`. File disputes only when `ready_to_file` is true. Each `payloads` member is the exact inner argument object for `file_credit_card_transaction_dispute_4829`.

## Provisional-credit rules

Determine eligibility per transaction. All conditions must hold:

- account is open at least 60 days;
- reason is fraud, duplicate, or goods/services not received, with the latter purchased more than 30 days ago;
- amount is at least $25 and within tier limit;
- no more than two prior disputes in the past 12 months; and
- for a non-fraud dispute, the customer contacted the merchant.

Limits are $2,500 entry, $5,000 mid, $10,000 premium, $15,000 elite, and $25,000 invitation. An unrecognized tier is an error, not a basis to guess. Ineligibility affects only `eligible_for_provisional_credit`; it does not prevent a complete dispute filing. Explain that provisional credit is temporary and may be reversed after investigation.

## File complete disputes

When all required values, including the last four digits, are available:

1. Set `card_action` to `cancel_and_reissue` if the customer requested replacement of that affected card; otherwise use `keep_active`.
2. Unlock `file_credit_card_transaction_dispute_4829`.
3. Call it once per script payload through `call_discoverable_agent_tool`, JSON-serializing that single payload in `arguments`.
4. Do not claim success until each result succeeds. Preserve successful filings if a later filing fails; do not duplicate them.

If the last-four lookup failed and the customer cannot provide digits, transfer the blocked dispute intake to a human agent. The handoff summary must identify the verified user and affected account, state that the documented lookup was attempted and unavailable, and retain **every** selected transaction ID, merchant/date/amount, reason, merchant-contact fact, noticed date, requested resolution, and any partial-refund amount. Use the applicable complex billing/dispute transfer reason. Do not fabricate a last-four value or submit a partial payload.

## Replacement workflow

After identity verification and confirmation of the affected card, address, reason, and delivery preference:

1. Confirm one replacement reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
2. Unlock and call `get_pending_replacement_orders_5765` with:
   ```json
   {"credit_card_account_id":"<selected account ID>"}
   ```
3. If an order is pending, processing, or shipped, do not create another. Explain that it must be delivered or cancelled first.
4. Observe replacement limits: two per 60 days for entry tier, three for mid tier, and four for premium and above. If known records or the order tool reports a limit block, do not retry; explain the manual-review path.
5. If no pending order or restriction blocks the request, unlock `order_replacement_credit_card_7291` and inspect its unlocked schema before constructing arguments. Supply the selected account ID, `reason`, confirmed `shipping_address`, and all fields that schema requires.

For suspected fraud or theft, recommend expedited delivery. Premium-and-above cards, including Gold Rewards, receive expedited delivery at no charge and it arrives in 2–3 business days; standard delivery is free and takes 7–10 business days.

**Schema compatibility:** use the actual unlocked replacement schema. If it exposes `expedited_shipping`, send `"expedited_shipping": true` for an expedited request. Use `shipping_speed: "expedited"` only if that field is actually exposed. Do not add unsupported fields merely because a knowledge article uses a different spelling. Provide fee acknowledgement only when the unlocked schema requires it; premium expedited shipping has a $0 fee.

After a successful order result, state that the old card is cancelled for security, the replacement has a new card number and CVV, the account number remains unchanged, delivery follows the selected timeframe, and email notices are sent when ordered and shipped. If disputes remain blocked, escalate only the dispute issue; do not imply that the completed replacement is blocked.
