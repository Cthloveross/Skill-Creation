---
name: credit-card-dispute-and-replacement
version: 1.0.0
description: Process one or more credit-card transaction disputes and a related replacement-card request while enforcing identity verification, required dispute fields, provisional-credit rules, and replacement prerequisites. Use when a customer reports card charges and may need their card cancelled and reissued.
---

# Credit Card Dispute and Replacement

Use this Skill for a customer who wants to dispute credit-card transactions, especially where fraud prompts a replacement card. Treat each disputed transaction as a separate dispute submission. Do not submit a dispute or replacement order from partial data.

## Required workflow

1. **Verify identity first.** Obtain confirmation of at least two of the registered date of birth, email, phone number, and home address. Retrieve the customer record as needed, then call `get_current_time` and `log_verification` with the complete registered fields and timestamp. Do not treat information found in a lookup as a customer confirmation.

2. **Identify the account and affected transactions.** Retrieve the customer's accounts and transaction history. Match every selected transaction to the intended card account. Collect the dispute facts separately for every transaction:
   - `transaction_id`
   - purchase date in `MM/DD/YYYY`
   - one allowed reason code
   - whether the customer contacted the merchant
   - issue-noticed date in `MM/DD/YYYY`
   - requested resolution, and partial amount when applicable
   - whether the customer wants to retain the card (`keep_active`) or cancel/reissue it (`cancel_and_reissue`)

   Allowed dispute reasons are: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed`.

3. **Obtain the last four digits; never invent them.** Every dispute requires the last four digits. If the customer does not have them, pass the documented customer tool using:
   `give_discoverable_user_tool` with `discoverable_tool_name` `get_card_last_4_digits` and arguments JSON containing the selected `credit_card_account_id`. Ask the customer to use it and provide/confirm the returned four digits. Do not file disputes or place the replacement order until this is available.

4. **Retrieve prior disputes before determining provisional credit.** Use `get_user_dispute_history_7291` with the authenticated `user_id` (unlock it first only if the runtime requires an unlock for that discovered tool). Count disputes filed within the preceding 12 months. If the tool returns ambiguous, partial, or inaccessible data, do not claim a provisional-credit result; retry or escalate according to the available process.

5. **Determine provisional credit per transaction.** Use `scripts/validate_case.py` to make the deterministic eligibility decision. A transaction is eligible only when all conditions hold:
   - the account has been open at least 60 days;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` purchased more than 30 days ago;
   - amount is at least $25 and does not exceed the tier limit;
   - no more than two prior disputes were filed in the last 12 months; and
   - for every non-fraud reason, the customer contacted the merchant.

   Tier limits: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. Pass the resulting boolean for each dispute. Eligibility for a dispute itself is distinct from provisional-credit eligibility.

6. **If a replacement is requested, complete the replacement prerequisites.** Confirm the full shipping address, including unit/suite, the replacement reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), and shipping speed. Explain that standard takes 7–10 business days and is free. Expedited takes 2–3 business days and costs $15 for Entry, $10 for Mid, and $0 for Premium and above. Capture explicit fee consent whenever a fee applies. Strongly recommend expedited delivery for suspected fraud or theft, but honor a customer's standard-delivery choice.

   Before unlocking or calling the replacement-order tool, confirm replacement eligibility. Check `get_pending_replacement_orders_5765` using the credit-card account identifier when available; any non-final order blocks another order. Also determine the number of replacements in the preceding 60 days: Entry permits 2, Mid 3, Premium and above 4. If there is an existing pending replacement or the limit has been reached, do not order another card; explain that the customer must wait for delivery/cancellation or seek manual review. Do not unlock or call the order tool until eligible.

7. **Validate the assembled case.** Save the runtime facts into a JSON object following the script schema below and run:
   `python3 scripts/validate_case.py < case.json`
   (The executor supplies JSON through stdin.) Review `errors`, `warnings`, and `tool_payloads`. A `ready` status means required fields are structurally complete; it does not replace the required identity log, dispute-history retrieval, or replacement eligibility confirmation.

8. **Submit only after all gates pass.**
   - Unlock `file_credit_card_transaction_dispute_4829`, then call it once for each dispute using `call_discoverable_agent_tool`. Its `arguments` must be a JSON string matching that dispute's `tool_payloads.disputes` object.
   - Only after replacement eligibility is confirmed, unlock `order_replacement_credit_card_7291`, then call it with a JSON string containing the account identifier, reason, confirmed shipping address, `standard` or `expedited` speed, fee acknowledgement (customer consent if a fee applies), and relevant notes.
   - If replacement is requested as a result of card compromise, use `cancel_and_reissue` on every affected dispute and use `fraud_suspected` as the replacement reason when that reflects the customer's report. Do not recast a merchant/service dispute as fraud without the customer's facts.

9. **Communicate and document.** Explain that a replacement cancels the old card for new purchases, creates a new card number/CVV, and retains the account number. State the delivery window, email notifications, and—when fraud or theft is reported—the need to review and dispute unauthorized transactions. Record the verified identity, facts collected, history result, provisional-credit decision for each transaction, tool outcomes, replacement details, and any blocked/pending action in the customer record.

## Script input and output

`validate_case.py` reads one JSON object from stdin and emits one JSON object to stdout. Required top-level fields are `as_of_date` (`MM/DD/YYYY`), `identity_verified` (boolean), `user` (with `user_id`, `full_name`, `phone`, `email`, `address`), `account` (with `account_id`, `card_type`, `opened_date`), `prior_disputes_past_12_months` (integer), `card_last_4_digits`, `disputes` (array), and `replacement` (object).

Each dispute requires `transaction_id`, `amount`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `contacted_merchant`, `resolution_requested`, and `card_action`. A partial refund additionally requires `partial_refund_amount`. The replacement object requires `requested`; if true it also requires `reason`, `shipping_address`, `shipping_speed`, `eligible_confirmed`, `no_pending_replacement`, and `replacements_past_60_days`; expedited paid tiers require `expedited_fee_acknowledgement: true`.

The output contains `status` (`ready`, `blocked`, or `needs_review`), validation messages, a `provisional_credit` decision for each dispute, and safe-to-use argument objects under `tool_payloads` only when all fields for that action are present. Never treat missing or unknown information as a favorable eligibility result.
