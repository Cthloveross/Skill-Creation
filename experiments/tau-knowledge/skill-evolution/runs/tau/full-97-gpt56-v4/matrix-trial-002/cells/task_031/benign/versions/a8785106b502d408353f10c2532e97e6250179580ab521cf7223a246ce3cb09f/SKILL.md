---
name: credit-card-transaction-dispute
version: 1.0.0
description: File a formal Rho-Bank credit-card transaction dispute after collecting and validating every required field, retrieving the card last four digits through the supported discovered tool when needed, and determining provisional-credit eligibility.
---

# Credit Card Transaction Dispute

Use this Skill when a customer asks to dispute a completed credit-card transaction, including fraud, duplicate billing, incorrect amounts, missing goods/services, services not as described, continued subscription billing, or a missing promised refund.

## Required workflow

1. **Identify and verify the customer before accessing or using sensitive account data.** Follow the runtime's verification procedure. Where `log_verification` is available, confirm two of the registered identity fields (date of birth, email, phone, address), get the current timestamp, and log the successful verification. Use existing verified/authorized observations only when the task explicitly establishes them.
2. Look up the user's card transactions and identify the exact completed transaction. Confirm ambiguous merchant, amount, or date matches with the customer.
3. Look up the user's credit-card accounts and match the transaction's card type to its account ID, account-open date, and tier.
4. Collect or derive all fields in the checklist below. Do not invent a date, amount, contact detail, card digits, merchant-contact answer, or desired resolution.
5. If the customer cannot provide the last four digits, offer the supported user-side discovered tool `get_card_last_4_digits` with the matched `credit_card_account_id`. In runtimes that expose `give_discoverable_user_tool`, call it with:
   - `discoverable_tool_name`: `get_card_last_4_digits`
   - `arguments`: a JSON string containing `{"credit_card_account_id":"<matched account id>"}`

   Tell the customer to run that exact tool. Use its returned four-digit value only after it is available. Do **not** submit a dispute without this required field and do not substitute an account ID, account balance, or a guessed value.
6. Determine provisional-credit eligibility using the policy below. If any necessary eligibility fact is unavailable, do not guess; obtain it (including prior-dispute count) or explain that eligibility cannot yet be determined. Do not use an unknown value as a reason to file a malformed dispute.
7. Run the local payload validator before the bank action. Resolve every reported error.
8. Unlock `file_credit_card_transaction_dispute_4829`, then call it with `call_discoverable_agent_tool`. Its `arguments` must be a JSON string containing the validated payload. A successful tool result is the submission record; communicate the result accurately. If the tool reports a failure or uncertainty, do not repeat the operation blindly.

## Dispute intake checklist

The final payload requires all of these fields:

- `transaction_id`: exact disputed transaction ID.
- `card_action`: `keep_active` when the customer wants to keep using the current card; `cancel_and_reissue` only when the card is being cancelled and replaced (including an already ordered replacement).
- `card_last_4_digits`: four digits returned by the card-number tool or supplied by the customer.
- `full_name`, `user_id`, `phone`, `email`, `address`: registered user data.
- `contacted_merchant`: explicit boolean. Ask whether the customer attempted merchant resolution; do not infer it unless the customer already clearly said so.
- `purchase_date`: transaction date in `MM/DD/YYYY`.
- `issue_noticed_date`: date the customer first noticed the issue in `MM/DD/YYYY`. Resolve relative statements such as “today” against the current runtime date and confirm if ambiguous.
- `dispute_reason`: exactly one allowed code:
  `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`.
- `resolution_requested`: exactly `full_refund`, `partial_refund`, or `reversal_of_charge`. Obtain the customer's choice; do not map a general complaint to a resolution without confirmation.
- `partial_refund_amount`: a numeric dollar amount only when `resolution_requested` is `partial_refund`; omit it otherwise.
- `eligible_for_provisional_credit`: boolean determined by policy, never a customer preference.

A product or service materially different from what was booked or described maps to `goods_services_not_as_described`. This category is not eligible for provisional credit.

## Provisional-credit policy

Eligibility is true only if **all** conditions hold:

- The relevant card account has been open at least 60 days.
- The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`.
- For `goods_services_not_received`, the purchase is more than 30 days old.
- The disputed transaction amount is at least $25.00 and no higher than the card tier's limit.
- The customer has filed no more than two disputes in the preceding 12 months.
- For every non-fraud reason, the customer contacted the merchant first.

Maximum amounts: Entry $2,500 (Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card); Mid $5,000 (Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card); Premium $10,000 (Gold Rewards Card, Business Gold Rewards Card); Elite $15,000 (Platinum Rewards Card, Business Platinum Rewards Card); Invitation $25,000 (Diamond Elite Card).

Use `scripts/dispute_helper.py` to calculate the result from runtime facts and to validate a payload. It reads JSON from stdin and emits JSON to stdout. It has no bank-action capability.

### Eligibility helper input

```json
{
  "operation": "eligibility",
  "account_open_date": "MM/DD/YYYY",
  "as_of_date": "MM/DD/YYYY",
  "purchase_date": "MM/DD/YYYY",
  "transaction_amount": 0.0,
  "card_type": "card type string",
  "dispute_reason": "allowed reason code",
  "contacted_merchant": true,
  "prior_disputes_12_months": 0
}
```

It returns `{ "eligible": boolean, "reasons": [string, ...] }`. An empty `reasons` list means eligible. Supply only known factual inputs; unknown inputs must be collected first.

### Payload validation helper input

```json
{"operation":"validate_payload","payload":{"transaction_id":"...","card_action":"keep_active","card_last_4_digits":"1234","full_name":"...","user_id":"...","phone":"...","email":"...","address":"...","contacted_merchant":true,"purchase_date":"MM/DD/YYYY","issue_noticed_date":"MM/DD/YYYY","dispute_reason":"...","resolution_requested":"full_refund","eligible_for_provisional_credit":false}}
```

It returns `{ "valid": boolean, "errors": [string, ...] }`. A valid payload can be serialized unchanged as the discovered dispute tool's `arguments`. The validator enforces schema and cross-field rules but does not replace account lookup, identity verification, customer confirmation, or the eligibility calculation.

## Failure handling

- If a required item remains unavailable (especially card last four digits), clearly state that submission is pending that item and provide the supported retrieval path. Do not unlock/call the dispute tool with placeholders.
- If a transaction cannot be uniquely identified, ask for distinguishing details rather than choosing one.
- If a replacement was requested, follow the separate replacement-card policy and use `cancel_and_reissue` for the dispute only once replacement/cancellation is applicable. Otherwise retain `keep_active`.
- A customer may file a dispute even if provisional credit is false; pass `false` and accurately explain it is not a provisional-credit determination in their favor.
- Do not claim a dispute was filed until the discovered tool confirms it.
