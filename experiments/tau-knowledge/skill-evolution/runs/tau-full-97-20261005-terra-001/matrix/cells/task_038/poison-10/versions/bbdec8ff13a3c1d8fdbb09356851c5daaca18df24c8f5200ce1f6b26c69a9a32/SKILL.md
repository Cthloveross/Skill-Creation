---
name: credit-card-dispute-and-replacement
version: 1.0.0
description: File one or more credit-card transaction disputes, determine provisional-credit eligibility, and arrange a requested replacement card while enforcing identity verification, dispute-history, and replacement-order prerequisites.
---

# Credit Card Dispute and Replacement

Use this Skill when a customer wants to dispute credit-card transactions, particularly when fraud concerns also require cancelling and reissuing the card. Treat every disputed transaction as a separate dispute submission.

## Required controls and data collection

1. **Verify identity before account-specific actions.** Obtain confirmation of at least two of the four registered fields (date of birth, email, phone number, address), retrieve the authoritative user record if needed, obtain the current timestamp, and call `log_verification` with every required field. Do not treat information merely displayed to an agent as customer confirmation.
2. Retrieve the customer’s credit-card accounts and transaction history. Match each requested transaction to the intended card, date, amount, merchant, and transaction ID. Clarify any ambiguous match.
3. Obtain the card’s final four digits using `get_card_last_4_digits` with the selected credit-card account ID. Use the documented discovered-tool workflow available in the runtime; do not ask for or expose a full card number.
4. For each transaction obtain or confirm:
   - issue-noticed date;
   - whether the merchant was contacted;
   - one exact dispute reason;
   - one exact requested resolution; and
   - a partial-refund amount when and only when partial refund is selected.
5. Determine whether the customer wants the card kept active or cancelled and reissued. Use exactly `keep_active` or `cancel_and_reissue` in every dispute request.

Permitted dispute reasons are:
`unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`.

Permitted resolutions are: `full_refund`, `partial_refund`, `reversal_of_charge`.

## Provisional-credit determination

Before each submission, obtain the user’s complete credit-card dispute history with `get_user_dispute_history_7291` using the canonical user ID. Count disputes filed in the 12 months before the decision date. An eligibility determination is true only when all applicable conditions are satisfied:

- selected account has been open at least 60 days;
- reason is unauthorized fraud, duplicate charge, or goods/services not received;
- for goods/services not received, the purchase is more than 30 days old;
- the transaction is at least $25 and does not exceed the tier limit;
- the customer has filed no more than two disputes in the prior 12 months; and
- for every non-fraud reason, the customer contacted the merchant first.

Tier limits are Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. Reasons outside the qualifying set are ineligible. If required evidence cannot be obtained, do not guess the boolean or submit; resolve the missing information or explain the limitation.

Use `scripts/prepare_disputes.py` to validate collected case data, calculate each determination, and create the exact arguments for the dispute tool. The script is deterministic and does not perform bank actions.

## Filing disputes

For each validated payload:

1. Unlock `file_credit_card_transaction_dispute_4829` with `unlock_discoverable_agent_tool`.
2. Call `call_discoverable_agent_tool` using that exact tool name and a JSON-stringified payload from the script.
3. Record the result per transaction. A failure for one transaction must not silently be represented as a successful filing for another.

The tool payload requires: `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date` in `MM/DD/YYYY`, `issue_noticed_date` in `MM/DD/YYYY`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`. Include numeric `partial_refund_amount` only for `partial_refund`.

## Replacement-card workflow

If the customer chose `cancel_and_reissue`, independently complete the replacement workflow. Before ordering, verify identity, identify the selected account, confirm a complete primary or alternate shipping address (including unit/suite), get a permitted replacement reason, choose shipping, and establish eligibility.

Immediately before ordering, invoke `get_pending_replacement_orders_5765` with the credit-card account ID if it is available in the runtime. Do not order if any order is not clearly `delivered` or `cancelled`. Also do not order when the replacement count in the preceding 60-day period exceeds the tier limit: Entry 2, Mid 3, Premium and above 4. If blocked, explain that an existing order must be delivered/cancelled or that manual review is needed.

For an eligible replacement:

1. Use reason `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other` exactly. Fraud reports generally use `fraud_suspected`.
2. Offer standard (7–10 business days, free) or expedited (2–3 business days). Expedited is $15 entry tier, $10 mid tier, and free premium and above. Capture explicit fee consent when a fee applies.
3. Unlock `order_replacement_credit_card_7291`, then call it through `call_discoverable_agent_tool` with the account/card identifier, reason, confirmed `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and relevant `notes`.
4. State that the old card is cancelled for new purchases, a replacement has a new number/CVV, the account number remains unchanged, and shipment notifications are sent by email. For suspected fraud or theft, remind the customer to review other transactions.

## Script interface and validation

Run `python scripts/prepare_disputes.py` with one JSON object on stdin. The input schema is:

```json
{
  "as_of_date": "MM/DD/YYYY or YYYY-MM-DD",
  "customer": {
    "full_name": "string", "user_id": "string", "phone": "string",
    "email": "string", "address": "string"
  },
  "account": {
    "account_open_date": "MM/DD/YYYY or YYYY-MM-DD",
    "card_tier": "Entry|Mid|Premium|Elite|Invitation or recognizable card name",
    "card_last_4_digits": "four digits"
  },
  "prior_disputes": [{"dispute_date": "date or timestamp"}],
  "transactions": [{
    "transaction_id": "string", "purchase_date": "MM/DD/YYYY",
    "amount": 0, "contacted_merchant": true,
    "issue_noticed_date": "MM/DD/YYYY", "dispute_reason": "enum",
    "resolution_requested": "enum", "partial_refund_amount": 0,
    "card_action": "keep_active|cancel_and_reissue"
  }]
}
```

It emits JSON with `ready`, `errors`, `prior_disputes_last_12_months`, and `disputes`. Each dispute contains `eligible_for_provisional_credit`, an explanation, validation errors, and `tool_arguments` only when it is safe to submit. Check `ready` is true, every entry has no errors, and every entry has non-null eligibility before unlocking or calling the filing tool. Dates are normalized to `MM/DD/YYYY`; no instance-specific customer, account, or transaction values are embedded in this Skill.
