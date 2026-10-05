---
name: credit-card-dispute-and-replacement
version: 1.0.0
description: Process one or more credit-card transaction disputes, determine provisional-credit eligibility, and coordinate a fraud-related replacement card when requested. Use when the customer identifies specific posted credit-card transactions and provides the required dispute facts.
---

# Credit Card Dispute and Replacement

Use this Skill to gather, validate, and submit a separate formal dispute for each selected credit-card transaction. It also covers the related replacement-card workflow when the customer wants a compromised card cancelled and reissued.

## Required facts and boundaries

A dispute submission requires all of the following for **each** transaction:

- `transaction_id`
- `card_action`: exactly `keep_active` or `cancel_and_reissue`
- the affected card's `card_last_4_digits`
- registered customer `full_name`, `user_id`, `phone`, `email`, and home `address`
- `contacted_merchant` boolean
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY`
- one permitted `dispute_reason`
- one permitted `resolution_requested`
- `partial_refund_amount` only for `partial_refund`
- a determined `eligible_for_provisional_credit` boolean

Do not guess a missing field or use a phone number/email as a substitute for the required card last four digits. Do not include a replacement shipping address in the dispute's `address` field; that field remains the customer's registered home address.

The valid reason codes are:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

The valid resolution codes are `full_refund`, `partial_refund`, and `reversal_of_charge`.

## Workflow

1. **Verify identity before replacement activity.** Ask the customer to confirm at least two of date of birth, email, phone number, and registered address; do not disclose the values first. After successful confirmation, call `get_current_time`, then call `log_verification` with all required profile fields and that timestamp. Use the authenticated customer/user ID for all subsequent work.

2. **Find and confirm the affected card and transactions.** Retrieve the customer's card accounts and transaction history, then match every requested merchant/date/amount to a unique posted transaction on the correct card. Never infer a transaction ID from similar charges. Confirm the selected card's account ID and tier.

3. **Obtain the last four digits.** If unavailable, give the customer the documented discoverable user tool `get_card_last_4_digits` with `{"credit_card_account_id":"<affected account id>"}` using `give_discoverable_user_tool`. Have the customer execute it and report/use the returned last four digits. A customer may use their app or website instead. Do not submit the dispute until the exact four digits are available.

4. **Capture facts separately for every transaction.** Ask for the reason, date noticed, merchant-contact result, and resolution for each transaction. Map the customer's selection to exactly one reason code. If a description genuinely supports two codes, ask which code the customer wants used rather than inventing one. For partial refunds, collect a positive numeric dollar amount.

5. **Retrieve prior dispute history.** Use `get_user_dispute_history_7291` with the verified `user_id` (unlock it first if the runtime exposes it as an agent-discoverable tool). Count disputes filed in the preceding 12 months. If the response is incomplete, malformed, or unavailable, provisional-credit eligibility is unknown; do not submit because its required boolean cannot be determined. Retry or escalate according to internal process.

6. **Determine provisional credit per transaction.** A transaction is eligible only when every applicable check is true:
   - the card account has been open at least 60 days;
   - the reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
   - for `goods_services_not_received`, the purchase is more than 30 days before the current date;
   - the amount is at least $25.00 and no more than the tier maximum;
   - the customer has filed no more than two disputes in the preceding 12 months; and
   - for any non-fraud reason, the customer contacted the merchant first.

   Tier maxima: entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000. Reasons outside the listed set are ineligible. Set `eligible_for_provisional_credit` to `false` for a known failed criterion, not for missing data.

   Run `scripts/validate_dispute_case.py` to validate the collected information and calculate these determinations. The script only creates call-ready payloads when all dispute fields and eligibility inputs are present.

7. **Handle a requested fraud replacement.** When the customer wants the affected card replaced, use `card_action: "cancel_and_reissue"` on every dispute for that card; otherwise use `keep_active`. Before ordering a separate replacement card:
   - confirm replacement eligibility, including the tier's 60-day replacement limit;
   - check for pending replacement orders with `get_pending_replacement_orders_5765` using the card account ID (unlock first if required by the runtime); do not order if any order is pending or shipped;
   - obtain and confirm the shipping address, including unit/suite, and shipping speed;
   - for a fraud-suspected or stolen card, use replacement reason `fraud_suspected` and recommend expedited shipping;
   - explain standard delivery is free and takes 7–10 business days. Expedited delivery takes 2–3 business days and costs $15 for entry tier, $10 for mid tier, and $0 for premium and above. Record consent if a fee applies.

   If eligibility or replacement-limit information cannot be confirmed, do not unlock or call the ordering tool. Explain the blocker or route for manual review. If eligible, unlock `order_replacement_credit_card_7291` and call it with the account identifier, exact reason, confirmed shipping address, speed, required fee acknowledgement, and concise notes. A replacement cancels the old card for new purchases and uses a new number/CVV.

8. **Submit each dispute.** Only after the validator returns no blocking errors, unlock `file_credit_card_transaction_dispute_4829` once. Call `call_discoverable_agent_tool` once per transaction with:
   - `agent_tool_name`: `file_credit_card_transaction_dispute_4829`
   - `arguments`: the JSON-serialized payload returned by the validator.

   Preserve the same card action and customer/card details for all selected transactions on the same card, but preserve transaction-specific dates, reason, merchant-contact response, resolution, and eligibility. Do not add `partial_refund_amount` for resolutions other than `partial_refund`.

9. **Communicate outcome.** State which disputes and replacement order were successfully submitted based only on actual tool responses. For a replacement, communicate the selected delivery window, email notifications, cancellation of the old card, and the need to update saved card details after the new card arrives. Provisional credit is temporary and may be reversed if the investigation is unsuccessful.

## Validator interface

Run `scripts/validate_dispute_case.py` with JSON on stdin. It emits JSON on stdout.

Input schema:

```json
{
  "current_date": "MM/DD/YYYY",
  "identity_verified": true,
  "customer": {
    "full_name": "string",
    "user_id": "string",
    "phone": "string",
    "email": "string",
    "address": "registered home address"
  },
  "card": {
    "last4": "1234",
    "tier": "Silver Rewards Card",
    "opened_date": "MM/DD/YYYY"
  },
  "prior_disputes": [{"dispute_date": "MM/DD/YYYY"}],
  "card_action": "keep_active",
  "disputes": [{
    "transaction_id": "string",
    "purchase_date": "MM/DD/YYYY",
    "amount": 100.0,
    "issue_noticed_date": "MM/DD/YYYY",
    "contacted_merchant": true,
    "dispute_reason": "duplicate_charge",
    "resolution_requested": "full_refund"
  }]
}
```

For a partial refund, add `partial_refund_amount` to that dispute. `prior_disputes` must contain all known prior dispute dates, including records that are closed. The script returns `errors`, `provisional_credit`, and `dispute_payloads`. Submit only if `ready_to_submit` is true. It never calls banking tools or places orders.

Example runnable call:

```sh
python3 scripts/validate_dispute_case.py <<'JSON'
{"current_date":"MM/DD/YYYY","identity_verified":true,"customer":{"full_name":"...","user_id":"...","phone":"...","email":"...","address":"..."},"card":{"last4":"1234","tier":"Mid Tier","opened_date":"MM/DD/YYYY"},"prior_disputes":[],"card_action":"keep_active","disputes":[]}
JSON
```

An empty dispute list is intentionally not call-ready. Review returned errors, collect the missing facts, rerun, and then use the returned payloads exactly.
