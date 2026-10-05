---
name: credit-card-fraud-replacement-and-cli
summary: Handle a verified cardholder's fraud dispute, replacement-card request, and credit-limit-increase request while enforcing identity, tier, eligibility, tool-order, and payload requirements.
---

# Credit-card fraud, replacement, and CLI workflow

Use this Skill for a credit-card customer reporting fraud who may also request a replacement card and/or a credit-limit increase (CLI). These are separate workflows. Use live runtime records and customer answers; do not infer missing facts, histories, tool outcomes, or eligibility.

## Required runtime facts

Collect or retrieve, as applicable:

- Verified customer record: full name, user ID, date of birth, registered email, phone, and address.
- Card account: account ID, card type, open date, status, balance, credit limit, past-due balance, and last four digits.
- Disputed transaction: transaction ID, amount, transaction date, merchant, and matching account/card.
- Dispute details: date first noticed, merchant-contact answer, reason, and requested resolution.
- Replacement details: reason, confirmed shipping address, shipping speed, fee consent when applicable, pending-order status, and replacement-count eligibility.
- CLI requested *increase amount* and live CLI eligibility facts.

## 1. Verify identity before sensitive action

1. Look up the claimed customer and compare customer-provided values with the registered record.
2. Require matches on at least two of: date of birth, registered email, registered phone number, and registered address.
3. After that check succeeds, get the current time and call `log_verification` with `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified` from the verified record.
4. Do not file a dispute, order a replacement, submit a CLI, approve, or deny until verification is logged. If fewer than two fields match, collect another permitted field or use normal escalation.

## 2. Card-tier classification

Classify the actual card product before applying tier rules. In particular, **Gold Rewards Card is Premium tier**. Therefore it uses Premium CLI rules: 50% maximum increase per request, 60-day account-age and approved-request cooldown requirements, utilization strictly below 90%, and three consecutive on-time payment months. Gold Rewards Card is also Premium for provisional-credit and replacement-shipping rules.

Use `scripts/assess_case.py` for deterministic tier classification or calculations, but retain responsibility for live lookups and bank-tool calls.

## 3. Fraud dispute workflow

Confirm that the selected transaction belongs to the verified customer's selected account. Gather every filing value before acting.

1. Set `card_action` to `cancel_and_reissue` if the customer wants the compromised card replaced; otherwise use `keep_active`.
2. Determine provisional-credit eligibility before filing. Retrieve prior disputes with `get_user_dispute_history_7291` and count disputes filed in the prior 12 months. Eligibility requires all of:
   - account open at least 60 days;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` (the last only if purchase was over 30 days ago);
   - amount is at least $25 and no more than the tier cap: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000;
   - no more than two prior disputes in the last 12 months; and
   - for a non-fraud dispute, the customer contacted the merchant.
3. Unlock `file_credit_card_transaction_dispute_4829`, then invoke it through `call_discoverable_agent_tool`. Pass a JSON-string payload with: `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`.
4. Dates must be `MM/DD/YYYY`. Reason must be one of `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`. Resolution must be `full_refund`, `partial_refund`, or `reversal_of_charge`; include numeric `partial_refund_amount` only for `partial_refund`.
5. If eligible, explain that provisional credit is temporary pending investigation, not a final result.

## 4. Replacement-card workflow

Before unlocking the replacement tool, ensure identity is logged, the account is correct, the address is confirmed, the replacement reason is exactly one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`, and the shipping selection is known.

1. Call `get_pending_replacement_orders_5765` with the credit-card account ID. Any order not clearly `delivered` or `cancelled` prevents another order.
2. Confirm the replacement-count limit for the preceding 60 days from an authorized source: Entry 2, Mid 3, Premium and above 4. If that fact cannot be obtained, do not claim eligibility or submit an order; obtain the required record or escalate.
3. Standard delivery is free and takes 7–10 business days. Expedited delivery takes 2–3 business days and costs Entry $15, Mid $10, and Premium or above $0. Obtain acknowledgement only where a fee applies. Strongly recommend expedited delivery for fraud or theft.
4. If eligible, unlock `order_replacement_credit_card_7291` and invoke it through `call_discoverable_agent_tool`, using the account-identifier parameter exposed by the unlocked tool plus `reason`, `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and `notes`.
5. Do not place a second order merely because the dispute has `card_action: cancel_and_reissue`. After a successful order, explain that the old card is cancelled, the replacement has a new number/CVV, and give the selected delivery window and fraud-monitoring reminder.

## 5. CLI workflow: mandatory order

Process a CLI independently and in this exact order.

### A. Pre-submission amount gate

First classify the card tier and calculate the maximum increase from the current limit:

- Entry: 25%
- Mid: 50%
- Premium: 50%

The requested increase must be a positive integer number of dollars. **Do not submit or deny a request that exceeds this limit.** State the calculated maximum and ask the customer to confirm a revised in-limit amount.

For a Gold Rewards Card, explicitly treat it as Premium. Thus, for example, a current $5,000 limit permits at most a **$2,500** increase. If a customer asks for a $4,000 increase, clearly say that $4,000 exceeds the $2,500 maximum and ask whether they want to adjust the request to $2,500 instead. Do not submit or approve the original $4,000 request.

### B. Submit only after an in-limit amount is confirmed

Call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and `requested_increase_amount`. Submission occurs before eligibility checks.

### C. Complete every post-submission eligibility check

Check and record all of the following:

- account age: Entry 120 days, Mid 90, Premium 60;
- cooldown since the most recent **approved** CLI: Entry 120, Mid 90, Premium 60, using `get_credit_limit_increase_history_4829`; denied requests do not start cooldown;
- no active disputes;
- no pending replacement order, using `get_pending_replacement_orders_5765`;
- no past-due balance;
- utilization strictly below Entry 70%, Mid 80%, or Premium 90%; and
- on-time payment history using `get_payment_history_6183`: Entry 6 months, Mid/Premium 3 months.

If all checks pass, call `approve_credit_limit_increase_5847` with account ID, user ID, and `new_credit_limit` equal to current limit plus requested increase. If a post-submission check fails, call `deny_credit_limit_increase_5848` with the documented applicable reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`.

A current dispute or pending replacement blocks approval. Explain known blockers without fabricating a future eligibility date.

## Helper script

`scripts/assess_case.py` is a read-only validator and calculator. It accepts a JSON object on stdin with optional `identity`, `dispute`, `replacement`, and `cli` objects and emits JSON assessments on stdout. Dates may be ISO `YYYY-MM-DD`, `MM/DD/YYYY`, or timestamps beginning with an ISO date. It never calls banking tools or submits an action.

Example:

```sh
python3 scripts/assess_case.py <<'JSON'
{"cli":{"tier":"Gold Rewards Card","current_credit_limit":"5000","requested_increase_amount":4000}}
JSON
```

Treat `missing`, `errors`, or an unknown result as a stop signal for the affected action. The executor must still obtain live history, check tool results, make required banking-tool calls, and communicate the result.
