---
name: credit-card-dispute-and-replacement
version: 1.0.0
description: File one or more credit-card transaction disputes and, when fraud exposure warrants it, coordinate a replacement-card request. Use when transaction facts, customer details, provisional-credit eligibility, card cancellation choice, and replacement prerequisites must be collected and checked before bank tool calls.
---

# Credit Card Dispute and Replacement

Use this Skill for a customer disputing one or more credit-card transactions, particularly where they also want the card cancelled and replaced. Treat every transaction as a separate dispute submission. Do not infer missing facts or execute a bank action until its prerequisites are met.

## 1. Identify the customer and the relevant card

1. Locate the customer and retrieve the card accounts and transaction list using the normal read-only banking tools.
2. Match every requested dispute to a specific completed transaction and card account. Confirm the customer is not disputing similarly dated or similarly priced transactions by mistake.
3. For a replacement request, verify the customer by having them provide two of the four identity fields (date of birth, registered email, registered phone, registered address) and comparing them with the retrieved record. After two fields match, get the current timestamp and call `log_verification` with the complete retrieved identity record and timestamp.
4. A dispute needs the card’s last four digits. Do not substitute an account ID, a transaction ID, or digits from a different card. If unavailable, tell the customer how to obtain it in the app or website (Credit Card > selected card > **View card details** or **Reveal card number**, completing the identity check). Where supported, pass the customer `get_card_last_4_digits` through `give_discoverable_user_tool` with `{"credit_card_account_id":"<selected account id>"}`.

## 2. Collect and normalize dispute facts

For **each** transaction, collect or confirm:

- transaction ID, amount, and purchase date from the matched transaction;
- `dispute_reason`, exactly one of:
  `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`;
- when the customer noticed the issue; resolve relative wording such as “today” from the current bank-system date and format as `MM/DD/YYYY`;
- whether they contacted the merchant (`true`/`false`);
- requested resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`; and a positive partial-refund amount only for `partial_refund`;
- whether to keep the card active or cancel/reissue it. Use `cancel_and_reissue` only when the customer requests cancellation/replacement; otherwise use `keep_active`.

Also obtain the registered full name, user ID, phone, email, and address from the customer record. Use the same selected card’s last four digits and chosen card action for each dispute on that card.

If the customer alleges an unrecognized charge or compromised card, recommend cancellation/reissue. Do not reclassify another dispute merely because its amount matches: use the reason the customer states or clarify it.

## 3. Determine provisional-credit eligibility

Before filing, unlock and call `get_user_dispute_history_7291` with the user ID, then determine eligibility separately for each transaction. The customer is eligible only if all conditions hold:

1. the disputed card account has been open at least 60 days;
2. the reason is unauthorized/fraudulent, duplicate, or goods/services not received **and**, for not-received, the purchase was more than 30 days ago;
3. amount is at least $25.00 and no greater than its card-tier limit;
4. no more than two prior credit-card disputes were filed in the preceding 12 months; and
5. for any non-fraud reason, the customer contacted the merchant.

Limits are: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. Silver Rewards, Business Silver Rewards, Green Rewards, and Silver Zoom are Mid tier. Do not treat a missing dispute-history result, account-open date, amount, or card tier as a negative answer; obtain it or leave the dispute unfiled. Provisional credit is temporary and may later become permanent or be reversed after investigation.

Use `scripts/prepare_disputes.py` to validate the case and calculate normalized payload candidates. Its result is decision support only; the executor remains responsible for fetching required runtime facts and conducting all banking calls.

## 4. File disputes only when ready

For each ready dispute:

1. Unlock `file_credit_card_transaction_dispute_4829` with `unlock_discoverable_agent_tool`.
2. Call it with `call_discoverable_agent_tool`, the tool name, and a JSON string containing every required field in the generated `tool_payload`. Omit `partial_refund_amount` unless the requested resolution is `partial_refund`.
3. Record the tool result per transaction and clearly tell the customer which disputes were submitted. A failed submission does not mean other transactions were submitted; handle each result independently.

The filing payload requires exactly:
`transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, `eligible_for_provisional_credit`, plus `partial_refund_amount` only when applicable.

## 5. Replacement-card workflow

Only perform this section if the customer wants a replacement. It is separate from filing the disputes.

Before ordering, complete identity verification and obtain the selected card account ID, confirmed shipping address (including unit/suite if relevant), replacement reason, and shipping choice. Record exactly one replacement reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. For suspected fraud or stolen cards, strongly recommend expedited shipping and remind the customer to review other transactions.

Check replacement eligibility before ordering:

1. Unlock and call `get_pending_replacement_orders_5765` with the credit-card account ID. Any pending or shipped order blocks a new request; delivered and cancelled orders are final.
2. Confirm there is no more than the tier’s 60-day replacement allowance. The allowance is 2 for Entry, 3 for Mid, and 4 for Premium-and-above. If replacement-count data is unavailable, obtain it or do not order.
3. Confirm standard (7–10 business days, free) or expedited (2–3 business days). Obtain explicit fee consent if expedited has a fee: Entry $15, Mid $10, Premium-and-above $0.

If eligible, unlock `order_replacement_credit_card_7291` and call it using the selected account identifier, `reason`, confirmed `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and contextual `notes`, as required by the replacement tool. Explain that the old card will be cancelled, the replacement has a new card number/CVV, the account number remains unchanged, and the customer will receive order/shipping emails.

Do not order if a replacement is pending, the limit is exceeded, verification is incomplete, the address or shipping selection is unconfirmed, fee consent is absent when required, or eligibility cannot be established. Explain the blocker and next step.

## Script interface

Run:

```text
python scripts/prepare_disputes.py < case.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. Supply `reference_date` (`MM/DD/YYYY` or ISO date), `customer`, `account`, `history`, and a `disputes` list. Each dispute supplies a `transaction` and the customer’s stated facts. See the input-field descriptions in the script source. Output contains normalized payload candidates only where all filing fields are valid, per-dispute validation errors/follow-ups, and provisional-credit decisions. Never call the filing tool for an entry whose `ready` is false or whose `eligible_for_provisional_credit` is `null`.
