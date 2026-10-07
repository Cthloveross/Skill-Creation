---
name: credit-card-dispute-and-cli-processing
description: Process a credit-card transaction dispute and/or credit-limit-increase (CLI) request using the documented banking tools. Use for requests requiring mandatory dispute data, provisional-credit assessment, and the ordered CLI submission, verification, and decision workflow.
---

# Credit Card Dispute and CLI Processing

Handle each requested service independently. A missing prerequisite for a dispute does not prevent a separately authorized CLI request, and a pending CLI review does not authorize filing an incomplete dispute. Do not fabricate customer fields, card details, eligibility results, or tool outcomes.

## 1. Identify, verify, and collect records

1. Determine the customer and relevant credit-card account from the information the customer provides. Use the available user/account/transaction lookup tools to identify the account and confirm the cited transaction belongs to it.
2. Before performing a state-changing action, verify identity by having the customer provide and match at least two of date of birth, email, phone number, and address. After successful verification, obtain the current timestamp and call `log_verification` with the complete retrieved identity record and timestamp. Do not treat information merely retrieved from a database as customer confirmation.
3. Keep the account ID, user ID, current limit, balance, account status, past-due amount, card type, transaction ID, and relevant dates available for the applicable workflow.
4. Treat a customer request stated as an approximate desired total (for example, “about” a limit) as ambiguous. Explain the calculated increase and obtain confirmation of one exact dollar increase before submitting a CLI request.

## 2. Dispute workflow

### Required collection and validation

A formal dispute can only be filed after every required tool argument is known and verified:

- `transaction_id`
- `card_action`: `keep_active` or `cancel_and_reissue`
- `card_last_4_digits`
- `full_name`, `user_id`, `phone`, `email`, and `address`
- `contacted_merchant` (boolean)
- `purchase_date` and `issue_noticed_date`, both `MM/DD/YYYY`
- `dispute_reason`, one of the documented enum values
- `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`
- `partial_refund_amount` only when the resolution is `partial_refund`
- `eligible_for_provisional_credit` (boolean)

Confirm the transaction date and amount against transaction history rather than relying only on a merchant name. Ask the customer to choose an allowed reason and resolution if their wording is ambiguous. For a non-fraud dispute, explicitly obtain whether they attempted merchant contact.

### Missing card last four digits

Do not file a dispute without `card_last_4_digits`, even if the account ID and transaction are known. The documented way to retrieve it is `get_card_last_4_digits(credit_card_account_id: str)`. Provide that user-discoverable tool through `give_discoverable_user_tool` with the relevant account ID, and ask the customer to return with the result. Do not substitute an account ID, guess the digits, or claim that a lookup result contained the digits when it did not.

### Provisional-credit assessment

Determine the boolean before filing; it is not a promise that a credit has posted. Retrieve the user’s dispute history using `get_user_dispute_history_7291(user_id)` rather than relying solely on a customer recollection when the tool is available. The customer is eligible only if **all** conditions hold:

1. The card account has been open at least 60 days.
2. The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` where the purchase was more than 30 days ago.
3. The disputed amount is at least $25.00 and no more than the card tier’s limit: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000.
4. The user has filed no more than two disputes in the prior 12 months.
5. For every non-fraud reason, the customer contacted the merchant first.

Use the runtime’s current date for day-based comparisons. If an input, tool result, or date is unavailable or ambiguous, do not assert eligibility; collect the missing information or defer filing.

### Filing

Once identity is verified and every field is complete, unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool` with a JSON string containing all required fields. Use `keep_active` unless the customer requests cancellation/reissue. Report that the dispute was filed and state the provisional-credit determination accurately; explain that any provisional credit is temporary while the investigation proceeds.

## 3. CLI workflow

### Tier rules

Classify the card tier from its card type using the documented tier assignment. Apply these limits:

| Tier | Minimum age | Cooldown after approved request | Utilization must be below | On-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry | 120 days | 120 days | 70% | 6 | 25% of current limit |
| Mid | 90 days | 90 days | 80% | 3 | 50% of current limit |
| Premium | 60 days | 60 days | 90% | 3 | 50% of current limit |

Calculate utilization as `current_balance / current_credit_limit * 100`. Equality with the utilization threshold fails. A customer whose requested total is known has requested an increase equal to `requested_total - current_limit`; reject non-positive increases as needing clarification.

### Exact required order

Follow this order exactly:

1. **Validate amount before submitting.** Compute the tier maximum from the current limit. If the exact requested increase exceeds it, do not submit. Tell the customer the maximum permitted increase and ask whether they want to proceed with that exact amount. If the request is exact and within the cap, continue.
2. **Submit first.** Unlock and call `submit_credit_limit_increase_request_7392` using `credit_card_account_id`, `user_id`, and the exact integer `requested_increase_amount`. Eligibility checks must occur after this submission.
3. **Check every eligibility criterion.** Record evidence for all of the following even when one fails:
   - account age from the account open date and current date;
   - cooldown using `get_credit_limit_increase_history_4829(credit_card_account_id)`. A cooldown applies only following the most recent **approved** request; denied requests do not trigger it. Count full days from the submission date;
   - no active/pending disputes, using the available account/dispute records or the relevant documented runtime capability;
   - no pending replacement order: call `get_pending_replacement_orders_5765(credit_card_account_id)` and regard any non-final order (such as pending or shipped) as blocking; delivered/cancelled orders are final;
   - good standing: account is current and has no past-due balance;
   - utilization strictly below the tier threshold;
   - payment history: call `get_payment_history_6183` with the account ID and the tier-required number of months, then verify the required consecutive months are on time.
4. **Record the decision.** If every criterion passes, unlock and call `approve_credit_limit_increase_5847` with `new_credit_limit = current_credit_limit + requested_increase_amount`. Otherwise unlock and call `deny_credit_limit_increase_5848` using the documented enum that corresponds to the failure: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, or `requested_amount_exceeds_limit`. Use `other` only when no listed code accurately describes the documented failure.
5. **Communicate clearly.** For approval, state the resulting total credit limit. For denial, state the relevant reason and a supported next step or reapplication timing where determinable. Do not disclose internal checks unnecessarily.

## 4. Tool-use safeguards and completion

- Unlock a discoverable agent tool before calling it. Pass a JSON string with exactly the required fields to `call_discoverable_agent_tool`.
- Never make a bank state-changing call merely because a calculation recommends it; the executor must make each normal banking tool call as the workflow requires.
- Do not repeat a state-changing action after an `UNKNOWN` result. Explain that status and escalate or seek a safe resolution instead.
- If a tool error prevents a required verification or decision, do not infer a passing result. Preserve the already completed work, tell the customer what remains, and use an appropriate supported escalation only if needed.
- Finish with a concise status for each service: filed/deferred for the dispute and submitted/approved/denied/deferred for the CLI, plus the one concrete next action needed from the customer when applicable.

## Runtime inputs and outputs

This Skill consumes the live customer conversation, current time, account/transaction lookup results, and results from the documented banking tools. Its outputs are the required tool actions and a customer-facing status message. It has no local scripts because eligibility depends on live banking records and state-changing actions must use the declared banking tools rather than a script.