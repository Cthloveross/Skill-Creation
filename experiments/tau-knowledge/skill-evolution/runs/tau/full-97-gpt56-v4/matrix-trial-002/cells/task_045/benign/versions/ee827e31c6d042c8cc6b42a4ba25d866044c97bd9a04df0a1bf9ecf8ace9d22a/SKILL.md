---
name: credit-card-closure-with-retention
version: 1.8.0
description: Handle a verified customer's request to close a credit card, including payment of an outstanding balance from checking when authorized, mandatory closure eligibility checks, retention-reason handling, and compliant closure communication. Use for credit-card account closure requests; do not use it to close checking accounts or to act without verified identity and account ownership.
---

# Credit Card Closure With Retention

Use this workflow for a customer who asks to close a credit-card account. It is deliberately stateful: perform tool calls against the current account state, and do not treat an earlier lookup as proof that a mutable condition (balance, disputes, or replacement-card status) is still clear.

## Safety and authorization rules

- Identify the requested card from an account lookup and ensure it belongs to the authenticated customer. If several accounts could match, ask the customer to select one; never select an account merely because it has a similar name.
- Complete standard identity verification before disclosing account-specific balances, rewards, status, eligibility, or making changes. The runtime's verification standard is confirmation of **two of four** fields: date of birth, email, phone number, and address. Customer-provided values must match a user record. A record lookup, a name, or an account number alone is not customer confirmation.
- After two fields match, get the current timestamp and call `log_verification` with the canonical name, user ID, address, email, phone number, date of birth, and timestamp. Do not log verification before two fields have been confirmed.
- Never close an account, pay a balance, apply an offer, or downgrade without the corresponding customer authorization. A general request to close is not authorization to debit an unspecified checking account.
- Do not invent account IDs, status values, card benefits, comparable cards, checking balances, or tool results. If an operation is unavailable or a response is ambiguous, explain what is needed and stop or escalate rather than guessing.
- Unlock each named specialized tool with `unlock_discoverable_agent_tool` before using it through `call_discoverable_agent_tool`. Pass only documented arguments, especially for reason logging.

## Workflow

### 1. Resolve and verify

1. Obtain a customer locator, look up the user, and look up that user's credit-card accounts with `get_credit_card_accounts_by_user`.
2. Match the requested card type/account to an account owned by that user. Record the `user_id` and `credit_card_account_id` for later calls.
3. Ask for enough identity information to reach two confirmed fields. Do not disclose the selected account's balance or other account details while collecting these fields. Do not read the values back unnecessarily. Once verified, call `get_current_time` and then `log_verification` using the canonical complete record and its current timestamp. Do not rely on a timestamp from an earlier turn.

### 2. Handle a nonzero balance before retention or closure

A closure requires a $0.00 outstanding balance. If the account has a balance:

1. Tell the customer the current balance must be paid before closure. Do not begin retention activity while any closure eligibility requirement is unmet: do not log a closure reason, ask follow-up questions about a competing card, address a closure concern, make an offer, or propose a downgrade.
2. Obtain the exact `checking_account_id` from a checking-account lookup only when the current runtime explicitly supplies that lookup; otherwise ask the customer for the identifier. Ask whether that identified account has at least the exact payment amount available. If a supplied lookup can confirm funds, use its actual result rather than a customer estimate. If multiple checking accounts are returned, ask the customer which account to debit. Then state the exact payment amount and obtain authorization to debit that identified account.
3. If the account identifier is unavailable, or a supported check cannot establish sufficient available funds, do not call the payment tool. Explain that the direct payment cannot be processed. Do not invent an alternative payment channel or tell the customer to use an undocumented method. Ask them to return after the account's displayed balance is actually $0.00. A customer statement that the account "should" have enough is not sufficient confirmation.
4. Unlock `pay_credit_card_from_checking_9182`, then call it with exactly `user_id`, `checking_account_id`, `credit_card_account_id`, and a positive `amount` no greater than both the confirmed checking balance and current card balance.
5. Re-fetch the credit-card account after a successful payment and require a displayed $0.00 balance before proceeding. If payment fails or is unknown, do not retry blindly and do not attempt closure.

### 3. Check every closure requirement

Once the balance is zero, perform and document all checks. The required conditions are:

1. **No active or pending disputes.** Unlock and call `get_user_dispute_history_7291` with `user_id`. Review records for disputes associated with the requested card. Any open, under-review, active, or pending dispute blocks closure. If association or status cannot be determined, treat eligibility as unresolved rather than clear.
2. **No pending replacement cards.** Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty order collection is clear. If any returned order is not clearly `delivered` or `cancelled`, closure is blocked. This check should be repeated immediately before initiating closure if time or other state-changing work has intervened.
3. **Account age of at least 60 days.** Determine age from the account's `date_of_account_open` and the current date. If either date is unavailable or ambiguous, treat eligibility as unresolved rather than estimating.
4. **$0.00 outstanding balance.** Confirm from a fresh account result, including after any payment.

If any condition fails, explain the specific blocker (for example, the balance must be paid, dispute resolved, account reach 60 days, or replacement be delivered/cancelled). Do not make retention offers and do not attempt closure.

### 4. Check retention history, reason, and offer

Only after all closure requirements are met:

1. Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id`.
2. If the account has a closure-reason record within the past year, skip all retention offers. Tell the customer that you will honor the closure request, then continue to Step 5 after confirming they still want closure.
3. Otherwise, understand the reason and log it. Ask for clarification if needed, map it to exactly one permitted value, then unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`. Permitted values are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.
4. Address the concern before making the final retention offer:
   - For `found_better_card`, ask which features of the other card are a better fit. Offer help applying for a Rho-Bank card only when a supported comparable or better option is actually available; do not claim one without support.
   - For annual-fee concerns, a customer of at least two years may receive a one-year fee waiver using `apply_credit_card_account_flag_6147` only if they accept it. Use `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`. For less than two years, offer a same-category no-fee downgrade if appropriate: business cards may downgrade to `Business Bronze Rewards Card`; personal cards to `Bronze Rewards Card`. Confirm benefit changes and consent before calling `downgrade_credit_card_3847` with `credit_card_account_id`, `user_id`, and `target_card_type`.
   - For other listed reasons, follow the applicable concern response: explain unused-card benefits, check bonus-category enrollment for reward dissatisfaction, or apologize/gather details and escalate a warranted service complaint.
5. If the customer still wants to close, make **one** retention offer based on the authoritatively established tier: entry 500 points or $5 statement credit; mid 2,000 points or $20 statement credit; premium-and-above 5,000 points or $50 statement credit. Do not infer a tier solely from an unverified name. If the customer declines, do not pressure them.

### 5. Process closure and communicate result

Before the irreversible call, confirm the customer still wants the specific account closed, recheck replacement-card status immediately if needed, and verify the balance remains zero.

1. Unlock `close_credit_card_account_7834`.
2. Call it with exactly `credit_card_account_id` and `user_id`.
3. Report success only if the tool confirms success. If it fails or is ambiguous, do not retry automatically; preserve the response and explain the next step.
4. On successful closure, state that a confirmation email and final statement will arrive within several business days. Explain that unredeemed rewards can be redeemed for 45 days after the closure request and are forfeited afterward. If relevant, explain that an annual fee posted within the prior 37 days may qualify for a full refund.

For cash-back cards, database reward "points" represent cash back at $0.01 per point. Use the helper only for arithmetic; do not imply that rewards have been redeemed unless a supported redemption is completed.

## Dialogue checkpoints

Use short, state-appropriate customer messages rather than treating a request to close as permission to perform every later action. In particular:

- After all eligibility conditions are clear, a customer who mentioned a competing card has supplied a possible `found_better_card` reason, but still must be asked which features matter before concern handling. Do not ask that follow-up, log the reason, or claim a Rho-Bank alternative exists while an eligibility blocker remains.
- If the customer gives more than one reason, select the single permitted logging value that best represents the stated primary reason; ask which is primary if this cannot be determined.
- A stated desire to pay a disclosed balance authorizes neither a debit from an unidentified checking account nor payment above the current balance. The direct-payment prerequisites still apply.
- If the customer cannot complete a required payment or eligibility condition now, clearly state the blocking condition and invite them to return after it is resolved. Do not suggest a particular payment method unless that method is explicitly documented and available in the current runtime. Do not log a closure reason, make a retention offer, or attempt a closure while that blocker remains.
