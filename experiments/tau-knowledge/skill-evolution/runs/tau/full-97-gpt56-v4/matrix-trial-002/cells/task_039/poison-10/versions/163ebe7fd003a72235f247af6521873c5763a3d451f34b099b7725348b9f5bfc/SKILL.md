---
name: credit-card-dispute-and-fraud-replacement
description: Safely files one or more credit-card transaction disputes, determines provisional-credit eligibility, and handles a requested fraud-related replacement card. Use when a verified customer identifies specific credit-card transactions to dispute, especially when unauthorized activity may require cancelling and reissuing the card.
---

# Credit-card disputes and fraud replacements

Use this Skill only after the customer identifies the particular transactions and desired remedies. A dispute is filed **per transaction**. Do not infer a transaction, a dispute reason, merchant-contact status, requested resolution, a partial-refund amount, card action, or an issue-noticed date.

## Required operational sequence

1. **Identify and verify the customer before any account-changing action.**
   - Locate the customer/account using the normal read-only banking tools.
   - Ask the customer to confirm at least two of DOB, registered email, phone number, and home address. Compare their supplied values to the retrieved record; do not treat values merely displayed by an internal lookup as customer confirmation.
   - On success, get the current time and call `log_verification` with the complete retrieved identity record and timestamp. If verification cannot be completed, do not unlock or call a dispute or replacement tool.

2. **Collect and validate each dispute.** For every requested transaction, confirm it belongs to the verified customer and record:
   - `transaction_id`, transaction/purchase date, amount, and the card account used;
   - one exact reason code: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`;
   - the date the issue was noticed, in `MM/DD/YYYY`;
   - whether the customer contacted the merchant (`true`/`false`); ask this for every dispute, including fraud (fraud may be `false`);
   - requested resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`. Require a positive numeric `partial_refund_amount` only for `partial_refund`; omit it otherwise.

   Use the documented transaction-history lookup if transaction data is not already available. Ask follow-up questions for ambiguous selections rather than filing a generic dispute.

3. **Retrieve supporting account information.**
   - Look up the relevant credit-card account and card tier. Retrieve the last four digits using the documented `get_card_last_4_digits(credit_card_account_id)` discovered tool; do not ask for a full card number.
   - Retrieve the customer’s dispute history using `get_user_dispute_history_7291(user_id)` before deciding provisional credit. Count filed disputes in the prior 12 months from the returned records. If the history response is partial, malformed, or unavailable, do not claim eligibility; resolve/retry/escalate according to the normal workflow.
   - For agent-discoverable tools, unlock the named tool with `unlock_discoverable_agent_tool` before calling it through `call_discoverable_agent_tool`, when the runtime requires it. Never repeat a call that reports an unknown outcome.

4. **Determine provisional-credit eligibility separately for each transaction.** Use `scripts/dispute_policy.py` or apply the same rules:
   - the account has been open at least 60 days;
   - reason is fraud, duplicate, or goods/services not received (the latter only when purchase was more than 30 days ago);
   - amount is at least $25 and at or below the applicable tier limit (Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000);
   - customer has filed no more than two disputes in the prior 12 months;
   - every non-fraud dispute was first taken to the merchant.

   A reason outside the qualifying list is ineligible even if every other condition is met. `eligible_for_provisional_credit` must be a boolean, not a promise that credit has posted.

5. **Handle requested replacement before filing a cancellation/reissue scenario.** If the customer wants the compromised card replaced:
   - confirm the replacement reason (`fraud_suspected` for suspected unauthorized charges), the shipping address (including unit/suite), and standard versus expedited delivery;
   - tell the customer the applicable delivery estimate and fee, and obtain fee acknowledgement when a fee applies. Standard is free and 7–10 business days. Expedited is 2–3 business days; entry tier is $15, mid tier is $10, and premium and above are complimentary;
   - check replacement eligibility, including `get_pending_replacement_orders_5765(credit_card_account_id)` and replacement-count restrictions (entry 2, mid 3, premium-and-above 4 in 60 days). A pending/non-final replacement blocks a new request;
   - only when eligible and all required confirmation is present, unlock and call `order_replacement_credit_card_7291` with account identifier, reason, confirmed address, speed, applicable fee acknowledgement, and useful notes. Place only one order for the affected card. Explain that the old card is cancelled, a different card number/CVV is created, and recurring payments tied to the account number continue.

   If a customer elects cancellation/reissue, use `cancel_and_reissue` as `card_action` for disputes on that card; otherwise use `keep_active`. Do not order a replacement just because a dispute is fraud-related unless the customer requests it or normal policy requires it.

6. **File each complete dispute.** Unlock `file_credit_card_transaction_dispute_4829`, then invoke it once per transaction through `call_discoverable_agent_tool`. Its arguments JSON must contain:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active | cancel_and_reissue",
  "card_last_4_digits": "4-digit string",
  "full_name": "registered full name",
  "user_id": "registered user ID",
  "phone": "registered phone",
  "email": "registered email",
  "address": "registered address",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "one exact allowed reason",
  "resolution_requested": "full_refund | partial_refund | reversal_of_charge",
  "eligible_for_provisional_credit": false
}
```

Add `partial_refund_amount` only for a partial refund. Use cardholder contact fields from the verified customer record, and dates/amount-linked facts from the matched transaction. Check the tool result for each submission. If one filing fails, report that specific status and continue only with distinct, complete submissions that have not already succeeded; do not duplicate a submitted dispute.

7. **Close clearly.** State which disputes were submitted or could not be submitted, the replacement result (if requested), delivery window, and that provisional credit is temporary when eligible. Do not state that a refund, dispute outcome, or provisional credit is guaranteed.

## Helper script

`scripts/dispute_policy.py` consumes one JSON object on stdin and emits a JSON decision on stdout. It performs only deterministic eligibility and input checks; it never accesses bank data or performs actions.

Input schema:

```json
{
  "account_open_date": "MM/DD/YYYY",
  "as_of_date": "MM/DD/YYYY",
  "purchase_date": "MM/DD/YYYY",
  "amount": 0.0,
  "card_tier": "premium",
  "prior_disputes_12_months": 0,
  "contacted_merchant": true,
  "dispute_reason": "duplicate_charge"
}
```

`card_tier` accepts `entry`, `mid`, `premium`, `elite`, or `invitation` (case-insensitive). Example runtime call:

```sh
printf '%s' '{"account_open_date":"01/01/2024","as_of_date":"04/01/2024","purchase_date":"02/01/2024","amount":100,"card_tier":"premium","prior_disputes_12_months":0,"contacted_merchant":true,"dispute_reason":"duplicate_charge"}' | python3 scripts/dispute_policy.py
```

A valid result has `eligible` plus a `failed_conditions` list. Before a tool call, validate that each completed dispute has a four-digit last-four value, valid dates, exact enum values, and the conditional partial-refund field.
