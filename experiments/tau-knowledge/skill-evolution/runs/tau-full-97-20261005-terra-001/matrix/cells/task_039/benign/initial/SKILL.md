---
name: credit-card-dispute-and-replacement
version: 1.0.0
description: File one or more formal credit-card transaction disputes, determine provisional-credit eligibility, and process a requested fraud-related card replacement using the documented Rho-Bank discoverable tools. Use when transaction, account, and customer data can be verified at runtime.
---

# Credit Card Dispute and Replacement

Use this Skill for each identified credit-card transaction; a multi-charge request requires one dispute filing per transaction. Never guess transaction IDs, card digits, customer contacts, account age, dispute count, or replacement eligibility.

## Required intake and verification

1. Identify the customer and the specific credit-card account that owns every disputed transaction. Match each requested merchant/date/amount to exactly one transaction record. Stop for clarification if a match is absent or ambiguous.
2. Before any write action, complete standard identity verification by having the customer confirm at least two of date of birth, registered email, registered phone, and registered address. Data displayed by a lookup is not itself customer confirmation.
3. After two fields are confirmed, call `get_current_time`, then call `log_verification` with all fields required by that tool, using the account record values and the verification timestamp. Do not submit a replacement order until this is complete.
4. Obtain and retain the registered full name, user ID, phone, email, and address from the verified customer record. These exact registered values are required in every dispute payload.
5. For each transaction, collect and normalize:
   - `dispute_reason` to one of: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`.
   - `resolution_requested` to `full_refund`, `partial_refund`, or `reversal_of_charge`.
   - `partial_refund_amount` as a positive number only for `partial_refund`; omit it otherwise.
   - whether the merchant was contacted. This must be a boolean, not prose. Fraud does not require merchant contact; non-fraud does for provisional-credit eligibility.
   - the purchase date and issue-noticed date in `MM/DD/YYYY` format.
   - whether the customer wants the card kept active or cancelled/reissued. Apply the same selected action to all disputes for that card: `keep_active` or `cancel_and_reissue`.

## Required lookups and calculations

Before filing, obtain the inputs that cannot safely be inferred:

1. Confirm the account opening date and card tier from the selected credit-card account. Retrieve the original card's last four digits using `get_card_last_4_digits(credit_card_account_id)` before a replacement changes the card number. If this is an agent-discoverable tool in the runtime, unlock it before calling it.
2. Retrieve dispute history with `get_user_dispute_history_7291(user_id)`. If the runtime exposes it as a discoverable agent tool, unlock it first. Count disputes filed in the 12 months before the filing date; do not treat the currently requested batch as pre-existing history.
3. Determine provisional-credit eligibility independently for every transaction. Call `scripts/dispute_support.py` with `operation: "eligibility"` or apply the same rules manually. Eligibility is true only when all apply:
   - account has been open at least 60 days;
   - reason is fraud, duplicate, or goods/services-not-received;
   - for goods/services-not-received, the purchase is more than 30 days before the filing date;
   - disputed transaction amount is at least 25.00 and no higher than the card tier limit;
   - no more than two disputes were filed in the preceding 12 months;
   - for any non-fraud eligible reason, the customer contacted the merchant.

Tier maxima: entry 2500; mid 5000; premium 10000; elite 15000; invitation 25000. The helper recognizes documented card names. If the tier is unknown, do not represent eligibility as true; obtain the tier or escalate.

## Replacement workflow when requested

If the customer requests a replacement, use `cancel_and_reissue` in each related dispute payload. Process only one replacement order for that card.

1. Confirm a replacement reason from the allowed replacement values. For fraud-related replacement use `fraud_suspected` only when supported by the customer's report.
2. Confirm the shipping address and the selected shipping speed. State the timeframe and obtain fee acknowledgement when a fee applies. Premium and higher tiers have complimentary expedited shipping; standard is free.
3. Check for a pending replacement with `get_pending_replacement_orders_5765(credit_card_account_id)` (unlock first if discoverable). Do not submit another order if any order is pending or shipped; wait for delivery/cancellation.
4. Confirm replacement eligibility, including the applicable 60-day tier replacement limit, from available replacement records. If the available runtime cannot establish the count or eligibility, do not unlock or call the order tool; explain that a manual review is needed.
5. Unlock `order_replacement_credit_card_7291`, then call it once with the account/card identifier, confirmed reason, confirmed address, `standard` or `expedited` speed, fee acknowledgement when applicable, and relevant notes. For fraud or stolen cards, recommend expedited shipping.
6. Tell the customer that the old card is cancelled, the replacement has a new number/CVV, the account number stays the same, and give the selected delivery window. Do not expose full card numbers.

A replacement order can change card details, so preserve the old card last four digits before the order. A successful replacement order does not replace the need to file each requested dispute.

## Filing each dispute

After all prerequisites and calculations are complete, validate every payload locally with `scripts/dispute_support.py` using `operation: "validate_payload"`. Correct all reported errors before filing.

Unlock `file_credit_card_transaction_dispute_4829` once. Then call `call_discoverable_agent_tool` once per transaction with `agent_tool_name: "file_credit_card_transaction_dispute_4829"` and an `arguments` JSON string containing:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active or cancel_and_reissue",
  "card_last_4_digits": "four digit string",
  "full_name": "registered full name",
  "user_id": "canonical user ID",
  "phone": "registered phone",
  "email": "registered email",
  "address": "registered address",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "allowed reason code",
  "resolution_requested": "full_refund, partial_refund, or reversal_of_charge",
  "partial_refund_amount": 0.0,
  "eligible_for_provisional_credit": false
}
```

Omit `partial_refund_amount` unless the resolution is `partial_refund`. Preserve the tool response for every transaction and clearly distinguish successfully filed disputes from failed submissions. Do not claim a provisional credit was posted: eligibility only determines the boolean supplied to the filing tool.

## Failure handling

- Do not file if identity is unverified, transaction matching is ambiguous, a required field is absent, dates are invalid, or a reason/resolution is unsupported. Ask the customer for the missing information.
- If a lookup is empty, malformed, denied, or partial, retry only when appropriate; otherwise use the documented escalation/support process rather than inventing values.
- If a replacement is blocked by a pending order, replacement limit, or unconfirmed eligibility, explain the restriction while continuing with independently complete dispute processing when appropriate.
- If the dispute tool fails for one transaction, do not assume the others failed or succeeded. Report its returned status and handle each remaining transaction independently.

## Helper script

Run with JSON on stdin, for example:

```json
{"operation":"eligibility","account_open_date":"06/15/2024","filing_date":"11/14/2025","purchase_date":"10/01/2025","reason":"duplicate_charge","amount":100.0,"card_type":"Gold Rewards Card","previous_disputes_12_months":0,"contacted_merchant":true}
```

The script emits JSON. `eligibility` returns `eligible_for_provisional_credit`, a resolved tier/limit, and explicit failed conditions. `validate_payload` accepts a prospective filing payload and emits `{ "valid": boolean, "errors": [...] }`. It does not call bank tools or submit any action.
