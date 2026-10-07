---
name: credit-card-fraud-replacement-and-cli
version: 1.0.0
description: Process a verified cardholder's fraudulent-transaction dispute, requested replacement card, and credit-limit-increase request using the documented banking tools. Use when these requests occur together or separately and preserve the required ordering, eligibility checks, and customer communications.
---

# Credit-card fraud, replacement, and CLI workflow

Use the normal banking lookup tools and the documented discoverable agent tools. Never infer account identifiers, transaction identifiers, card tier, identity fields, dates, prior-history results, or eligibility from a customer's assertion alone. Do not repeat a state-changing operation after it returns `UNKNOWN`.

## 1. Verify identity and identify the records

1. Obtain a stable lookup value (full name or email) and retrieve the user record. Retrieve the user's credit-card accounts and transactions.
2. Ask for identity fields as needed. Compare at least **two of date of birth, email, phone number, and address** with the retrieved user record. A name alone is not one of the two verification fields.
3. After two fields match, call `get_current_time`, then call `log_verification` with every required field from the retrieved record, the user ID, and that timestamp. Do not log verification if any supplied verification field conflicts with the record; resolve the mismatch first.
4. Select the customer's intended card account and match the disputed transaction by account, merchant, amount, and transaction date. Confirm any ambiguity with the customer before proceeding.
5. Normalize customer-supplied dates to the required `MM/DD/YYYY` format before a dispute filing. Gather any missing dispute fields: when the issue was noticed, whether the merchant was contacted, and the requested resolution. Gather and confirm replacement address, one valid replacement reason, and shipping choice.

For a suspected unauthorized charge, use `unauthorized_fraudulent_charge` as the dispute reason only when the customer's account and transaction context supports that characterization. Record `contacted_merchant: false` if the customer says they did not contact the merchant; merchant contact is not required for this fraud reason.

## 2. Determine provisional-credit eligibility before filing the dispute

The filing tool requires a boolean determination, so make it from evidence rather than promising an outcome.

1. Unlock and call `get_user_dispute_history_7291` with the verified user ID. Review every dispute filed in the 12 months preceding the current date; the customer must not have filed more than two.
2. Determine account age from the card account opening date and current date. It must be at least 60 days.
3. Determine the transaction amount and the card's provisional-credit maximum. Use the documented card-tier limits: entry $2,500, mid $5,000, premium $10,000, elite $15,000, invitation $25,000. Do not guess a tier for an unfamiliar product; obtain the applicable tier from the account/product information.
4. Set `eligible_for_provisional_credit` to true only when all apply:
   - account age is at least 60 days;
   - the amount is at least $25 and no greater than the tier cap;
   - no more than two prior disputes were filed in the prior 12 months;
   - the reason is `unauthorized_fraudulent_charge` or `duplicate_charge`, or is `goods_services_not_received` for a purchase more than 30 days old; and
   - for every non-fraud reason, the customer contacted the merchant first.

Set it false if any condition fails. If a required fact cannot be obtained or is ambiguous, do not represent the customer as eligible; obtain the fact or set false when filing is otherwise appropriate.

## 3. Replacement eligibility and order

A replacement order and a dispute card action must be coordinated to avoid leaving the card active or producing duplicate orders.

1. Before ordering, unlock and call `get_pending_replacement_orders_5765` with the credit-card account ID. Treat any order other than clearly `delivered` or `cancelled` as pending.
2. Do not place a new replacement if a nonfinal order exists. Explain that it must be delivered or cancelled first. Also check the documented 60-day replacement limit when the available records or order workflow can establish it: entry up to 2, mid up to 3, premium and above up to 4. Do not bypass an eligibility failure.
3. Confirm the address, a single reason from `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`, and shipping speed. Standard is free and 7–10 business days. Expedited is 2–3 business days and costs $15 entry, $10 mid, and is complimentary for premium and above. When a fee applies, obtain explicit customer consent and pass it as the expedited-fee acknowledgement.
4. For a fraud-suspected or stolen card, strongly recommend expedited shipping and remind the customer to review recent transactions. If the customer chooses an eligible option, unlock and call `order_replacement_credit_card_7291` with the account/card identifier, reason, confirmed address, speed, fee acknowledgement where needed, and relevant notes. Never call it before eligibility is checked.
5. When the order succeeds, explain that the old card is cancelled for new purchases, the replacement has a new number and CVV while the account number remains the same, and order and shipment emails will be sent.

If the dispute will be filed after a successful replacement order, use `cancel_and_reissue` for that dispute's `card_action`. This expresses that the compromised card is being cancelled and replaced. If no separate replacement can be ordered but the dispute itself will cancel and reissue the card, use the same action and clearly tell the customer which path is being used. Otherwise use `keep_active` only if the customer wants to retain the current card.

## 4. File the fraud dispute

After identity verification and the provisional-credit assessment, unlock `file_credit_card_transaction_dispute_4829` and call it with all required arguments:

- `transaction_id` from the matched transaction;
- `card_action` (`cancel_and_reissue` when the customer wants a replacement, otherwise `keep_active`);
- the account's `card_last_4_digits`;
- `full_name`, `user_id`, registered `phone`, `email`, and registered `address` from the verified record;
- `contacted_merchant` as a boolean;
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY`;
- one allowed `dispute_reason`;
- one allowed `resolution_requested`;
- `partial_refund_amount` only for `partial_refund`;
- the computed `eligible_for_provisional_credit` boolean.

For an unauthorized transaction, do not make merchant contact a precondition. Tell the customer that provisional credit, if eligible, is temporary while the investigation is ongoing and may later become permanent or be reversed based on the outcome. Confirm only the actual filing result returned by the tool.

## 5. Handle the CLI request in its mandated order

A concurrent or newly placed replacement can make the CLI ineligible. Still follow the CLI policy exactly; do not approve a CLI merely because the customer requests it.

### Requested-amount gate (before any CLI submission)

1. Determine the card tier and current credit limit from the selected account.
2. Calculate the maximum increase: 25% of current limit for entry-tier, 50% for mid-tier, and 50% for premium-tier cards. Treat the requested increase as the increase amount, not the desired new total. Use precise currency arithmetic and do not round above the allowed amount.
3. If the requested increase exceeds that maximum, do **not** submit a CLI request. Tell the customer the maximum permitted increase and ask whether they want to adjust to an amount at or below it. Do not call an approval or denial tool for this unsubmitted request.

### If the customer confirms a valid amount

1. First unlock and call `submit_credit_limit_increase_request_7392` with the account ID, user ID, and confirmed integer dollar increase. Submission must precede the eligibility review.
2. Check every criterion before the decision:
   - Account age: entry 120 days, mid 90, premium 60.
   - Cooldown: unlock and call `get_credit_limit_increase_history_4829`; apply the tier's 120/90/60-day cooldown only after the most recent **approved** CLI submission. Denied requests do not start this cooldown.
   - Pending disputes: inspect available dispute records and treat active/open/under-review disputes as pending.
   - Pending replacement: unlock and call `get_pending_replacement_orders_5765`; any nonfinal order blocks the CLI.
   - Good standing: confirm no past-due balance and that the account is current.
   - Utilization: calculate `current_balance / credit_limit * 100`; it must be strictly below 70% entry, 80% mid, or 90% premium. Equality fails.
   - Payment history: unlock and call `get_payment_history_6183` with 6 months for entry or 3 months for mid/premium; confirm all required consecutive months are on time.
3. If all checks pass, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit` equal to current limit plus the confirmed increase.
4. If any check fails, unlock and call `deny_credit_limit_increase_5848` with the account ID, user ID, and the most specific permitted reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other` only when none applies. Preserve the actual failure rather than substituting a more convenient reason.

## 6. Close the interaction

Summarize each completed action separately: dispute result and provisional-credit status, replacement order and delivery window (if ordered), and CLI result or the amount adjustment/deferral needed. For fraud or stolen-card cases, remind the customer to review recent transactions and dispute any additional unauthorized charges. Do not claim an order, dispute, approval, denial, email, cancellation, or delivery result unless the corresponding tool reported it successfully.

## Failure handling

- If a lookup returns no matching user, account, or transaction, stop before any state-changing tool call and request a corrected identifier or more details.
- If verification fails, do not access or alter the account; ask for a different verification field or use the appropriate support path.
- If a discoverable tool is not unlocked, unlock the exact documented tool before calling it.
- If a tool rejects an input or returns an ordinary eligibility failure, explain the returned result and do not retry unchanged inputs.
- If a state-changing call returns `UNKNOWN`, do not repeat it; preserve the context and escalate or follow the supported recovery process.
