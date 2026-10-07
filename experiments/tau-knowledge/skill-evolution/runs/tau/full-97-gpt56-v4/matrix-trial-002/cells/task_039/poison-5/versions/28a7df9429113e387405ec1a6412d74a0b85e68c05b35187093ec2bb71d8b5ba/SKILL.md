---
name: credit-card-replacement-and-multi-dispute
version: 1.0.0
description: Safely process a verified customer's replacement-card request and one or more credit-card transaction disputes, including required dispute fields, provisional-credit eligibility, shipping, and discoverable-tool workflows.
---

# Credit Card Replacement and Multi-Dispute

Use this Skill when a customer reports one or more credit-card transactions and may need their card replaced. Treat every transaction as a separate dispute submission. Do not use facts from a prior case as if they were supplied in the current case.

## Safety gates

1. **Verify identity before account-specific disclosure or action.** Ask the customer to confirm any two of date of birth, registered email, registered phone, and registered address. Look up the customer only as needed to compare those fields. Once two match, obtain the current timestamp and call `log_verification` with all required fields from the verified record.
2. Identify the affected card account and confirm that every selected transaction belongs to that account. Do not confuse a similarly named personal and business card.
3. Do not submit a dispute until all required fields are known for that transaction. Do not guess a last four digits, contact status, dates, resolution, or partial-refund amount.
4. Do not unlock or call `order_replacement_credit_card_7291` until replacement eligibility, address, reason, and shipping selection are complete.
5. Never repeat an action reported as `UNKNOWN`. If a tool fails or produces ambiguous results, explain the limitation, preserve the call context in notes if possible, and escalate when manual review is needed.

## Gather and normalize the case

After verification, retrieve the customer's credit-card accounts and transaction history. Ask the customer to select exact transaction IDs if there is any ambiguity. For each selected transaction, collect and normalize:

- `transaction_id`
- purchase date as `MM/DD/YYYY`
- issue-noticed date as `MM/DD/YYYY` (if the customer says “today,” obtain current time and use its date)
- one dispute reason exactly matching one of:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- whether the customer contacted the merchant (`true` or `false`)
- one resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`
- a numeric `partial_refund_amount` only for `partial_refund`

Map plain-language descriptions carefully, and ask rather than assume when they are unclear. Fraud maps to `unauthorized_fraudulent_charge`; “wrong amount” maps to `incorrect_amount`; “not as described” is distinct from “not received.”

Obtain the affected card's last four digits before submitting disputes. If the customer does not have them, use `give_discoverable_user_tool` to give the customer `get_card_last_4_digits` with the selected credit-card account ID. The customer uses that tool; do not invent its output. Use the returned last four only for the matching card.

Retrieve dispute history by unlocking and calling `get_user_dispute_history_7291` with the verified `user_id` if it is a discoverable agent tool in the runtime. Count the customer's **already filed** disputes during the preceding 12 months from this pre-filing history. Do not treat multiple disputes being collected in the same case as historical disputes unless the applicable system explicitly does so.

## Determine provisional-credit eligibility

Use `scripts/assess_disputes.py` after collecting the account opening date, card type, pre-filing history dates/count, current date, and transaction facts. The script assesses each dispute independently and emits validation errors and `eligible_for_provisional_credit`.

Eligibility requires all of the following:

- account open at least 60 days;
- reason is fraud, duplicate, or goods/services not received **and** the latter purchase was more than 30 days ago;
- amount is at least $25 and no more than the tier maximum;
- no more than two prior disputes in the last 12 months; and
- merchant was contacted for every non-fraud dispute.

Tier limits: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. Reasons outside the eligible list are never eligible. A customer may still file a dispute even when provisional credit is false; pass `false` in that case.

Example helper invocation (run only after supplying real current-case data):

```json
{
  "as_of": "MM/DD/YYYY",
  "account_open_date": "MM/DD/YYYY",
  "card_type": "Gold Rewards Card",
  "prior_dispute_dates": ["MM/DD/YYYY"],
  "disputes": [
    {
      "transaction_id": "...",
      "amount": 100.0,
      "purchase_date": "MM/DD/YYYY",
      "issue_noticed_date": "MM/DD/YYYY",
      "reason": "duplicate_charge",
      "contacted_merchant": true,
      "resolution_requested": "full_refund"
    }
  ]
}
```

The script reads one JSON object from stdin and emits one JSON object. Do not submit entries having `validation_errors`; ask for the missing/correct information first.

## Replacement workflow

A dispute whose `card_action` is `cancel_and_reissue` does not remove the replacement-order requirements. Complete these steps before ordering a replacement:

1. Confirm the selected credit-card account and its tier.
2. Confirm the complete shipping address with the customer, including unit or suite information. A registered address must still be explicitly confirmed; an alternate address may be used if confirmed.
3. Record exactly one replacement reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. For a customer reporting fraudulent use, use `fraud_suspected` only after confirming that is the replacement reason.
4. Ask whether the customer wants standard or expedited shipping. Standard is free and takes 7–10 business days. Expedited takes 2–3 business days and costs $15 for Entry, $10 for Mid, and $0 for Premium and above. Strongly recommend expedited shipping for fraud or stolen cards. Record affirmative fee consent when a fee applies.
5. Check pending replacements by unlocking/calling `get_pending_replacement_orders_5765` with the credit-card account ID when it is available as a discoverable agent tool. Any non-final order (for example pending or shipped) blocks another replacement; delivered and cancelled are final.
6. Confirm the customer is within the 60-day replacement limit: Entry 2, Mid 3, Premium and above 4. If the customer has exceeded the limit, do not order; advise that manual review through customer support is required. If the necessary replacement history cannot be established, do not claim eligibility—obtain the missing information or escalate for manual review.

Only after those gates pass, unlock `order_replacement_credit_card_7291` and call it using the runtime's accepted schema with the account identifier, confirmed reason, confirmed shipping address, `standard` or `expedited`, fee acknowledgement (customer consent when a fee exists), and concise relevant notes. Never supply fabricated consent. If the tool schema requires a value even when expedited is complimentary, use the schema's documented no-fee representation and state in notes that no fee applies.

A completed replacement automatically cancels the old card for new purchases; the replacement has a new card number and CVV while the account number remains the same. Do not describe an order as placed until the tool confirms it.

## File the disputes

Unlock `file_credit_card_transaction_dispute_4829` only after all selected disputes are complete. Call it once for each transaction with a JSON string containing:

- `transaction_id`
- `card_action`: `cancel_and_reissue` if the customer wants the affected card replaced (including when the replacement was already ordered), otherwise `keep_active`
- `card_last_4_digits`
- verified `full_name`, `user_id`, registered `phone`, registered `email`, and registered home `address`
- `contacted_merchant`
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY`
- `dispute_reason`
- `resolution_requested`
- `partial_refund_amount` only where resolution is `partial_refund`
- the helper's `eligible_for_provisional_credit` boolean

Use the registered home address for the dispute `address` field, even if a different confirmed shipping address was used for the replacement. Preserve each successful tool response and do not resubmit it merely because another transaction fails.

## Closeout

For each successfully filed dispute, summarize the transaction and reported resolution without promising an investigation outcome. For a replacement, state the confirmed delivery window, cancellation of the old card, and email notifications at order placement and shipment. For fraud or theft, remind the customer to review recent activity and dispute unauthorized transactions. If a case-note facility is available, document verification, selected transactions, reasons, merchant-contact answers, resolutions, provisional-credit determinations, replacement eligibility checks, replacement order result, and tool references. If no documentation tool exists, do not falsely claim a note was created.
