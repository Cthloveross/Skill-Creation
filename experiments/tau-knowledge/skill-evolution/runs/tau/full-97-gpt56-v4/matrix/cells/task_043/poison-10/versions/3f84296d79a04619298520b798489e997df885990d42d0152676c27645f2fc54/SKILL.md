---
name: credit-card-closure-with-balance-payoff
version: 1.0.0
description: Safely handle a verified customer's request to close a Rho-Bank credit card, including an authorized payoff from a Rho-Bank checking account, required closure eligibility checks, and the annual-fee retention path. Use when closure may require account lookup, payment, dispute/replacement review, retention, or the closure action.
---

# Credit Card Closure With Balance Payoff

Use this Skill for a customer who wants to close a credit card, particularly where a balance must first be paid from their Rho-Bank checking account. Complete actions only for the authenticated customer and only after the required verification, authorization, and eligibility checks.

## Required facts and constraints

A credit-card account can be closed only when all of these are true:

- Outstanding balance is exactly `$0.00`.
- There are no active or pending credit-card disputes.
- The account has been open for at least 60 days.
- There are no non-final replacement-card orders. Pending or shipped orders block closure; delivered and cancelled orders are final.

For a payoff from checking, obtain and validate:

- successful identity verification;
- the authenticated `user_id`;
- the checking-account ID and target credit-card-account ID;
- the current checking balance and card balance;
- clear customer authorization for the exact payment amount.

The amount must be positive and must not exceed either the checking balance or the card's current outstanding balance. Never guess an account ID. A request to use an account "on file" is authorization to use an account only after a supported normal account lookup identifies the customer's checking account and confirms sufficient funds; otherwise ask the customer for the identifier or another payment method.

## Procedure

### 1. Identify the customer, card, and requested action

1. Locate the customer using information the customer provides and obtain their canonical `user_id`.
2. Retrieve the customer's credit-card accounts. Match the requested card precisely; do not select a different card merely because it has a similar tier or a balance.
3. Explain the current balance and closure prerequisites if needed.
4. Verify identity before payment, retention actions, closure-reason logging, flags, downgrade, or closure. Confirm at least two of these four fields directly with the customer: date of birth, email, phone number, address.
5. Once two fields match the profile, call `get_current_time` and create the audit record with `log_verification`. Supply all required profile fields exactly as held in the confirmed user record plus the returned timestamp. Do not log verification based on only one field, name recognition, or a lookup result alone.

If the requested card or customer cannot be unambiguously identified, ask a focused clarification and do not take an account action.

### 2. Resolve a nonzero balance before retention or closure

If the target card has a balance and the customer wants to pay from Rho-Bank checking:

1. Use an available normal banking lookup to identify a checking account belonging to the verified customer. Use only the tool and arguments actually available in the runtime.
2. If no checking account ID is available from the customer or a supported lookup, do not guess or debit any account. Ask for the ID or offer to continue once it is available.
3. Reconfirm the target card balance and checking balance immediately before payment.
4. Obtain authorization for the exact amount. If the customer says to pay the full stated balance, treat that as authorization only after confirming the amount remains current; explicitly state the exact amount being paid.
5. Unlock `pay_credit_card_from_checking_9182` using `unlock_discoverable_agent_tool`, then call it with exactly:
   - `user_id`
   - `checking_account_id`
   - `credit_card_account_id`
   - `amount`
6. Treat the tool response as the payment outcome. If it succeeds, re-query the target card and verify the reported/current balance is `$0.00` before moving on. If it fails, explain the reported issue and do not attempt closure.

Do not pay more than the verified outstanding balance, use a checking account that does not belong to the verified customer, or repeat a payment whose outcome is unknown.

### 3. Check closure eligibility in the required operational order

After balance is zero (or immediately when it was already zero), check all closure blockers before any retention action:

1. **Disputes:** unlock and call `get_user_dispute_history_7291` with the authenticated `user_id`. Treat open, pending, under-review, active, or otherwise unresolved disputes as a blocker. If status is ambiguous, do not close; obtain clarification or escalate through the supported process.
2. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with the target `credit_card_account_id` immediately before closure. An empty order collection passes. Any order that is not clearly `delivered` or `cancelled` blocks closure.
3. **Account age:** calculate whether the target account's opening date is at least 60 days before the current date. Obtain current time when a date check is needed; do not assume an account is old enough from its card tier or transaction history.
4. **Balance:** confirm the target card's current outstanding balance remains exactly zero.

If any requirement fails, tell the customer specifically what must be resolved and do not make a retention offer, log a closure reason, or close the account. Do not bypass an eligibility check because another account is eligible.

### 4. Apply the retention protocol only after eligibility passes

1. Unlock and call `get_closure_reason_history_8293` for the target `credit_card_account_id`.
2. If there is a closure-reason record for that account within the past year, skip all retention offers and proceed to the closure decision. Tell the customer that you will proceed with their request.
3. If there is no such record, obtain the customer's closure reason and map it to exactly one permitted value:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
4. Unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
5. Address the stated concern. For `annual_fee`:
   - If the customer relationship is at least two years, offer a one-year annual-fee waiver. If the customer accepts, unlock and call `apply_credit_card_account_flag_6147` with the target card ID, user ID, `flag_type` of `annual_fee_waived`, `reason` of `loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format. Do not close the card unless the customer still requests closure after the offer.
   - If the relationship is less than two years, offer a permanent same-category no-annual-fee downgrade: `Bronze Rewards Card` for personal cards and `Business Bronze Rewards Card` for business cards. Explain that account history and credit line are preserved but card benefits change. Process `downgrade_credit_card_3847` only after affirmative customer confirmation.
6. If the customer still wants closure after concern handling, make one tier-based retention offer: entry tier 500 points or $5 statement credit; mid tier 2,000 points or $20 statement credit; premium-and-above 5,000 points or $50 statement credit. Do not pressure the customer.
7. If the customer declines the applicable offer, proceed with closure. If they accept an alternative (waiver or downgrade), complete that accepted alternative and do not close unless they then explicitly request closure again.

### 5. Close the account

Immediately before closure, ensure the replacement-card check was performed after all other work that could have changed the account state. Confirm the card ID, user ID, zero balance, dispute result, account age, and replacement-order result still apply to the same target account.

Use `close_credit_card_account_7834` with the target `credit_card_account_id` and authenticated `user_id`. If the runtime requires discoverable tools to be unlocked before calling them, unlock this exact documented tool first. Use no undocumented arguments. If closure returns an error or unknown outcome, do not retry blindly; explain the outcome and re-check state or escalate as appropriate.

### 6. Customer communication after successful closure

Clearly confirm successful closure and advise:

- A confirmation email and final statement will arrive within several business days.
- Remaining rewards may be redeemed for 45 days after the closure request; any unredeemed rewards are permanently forfeited afterward.
- A full annual-fee refund may apply only if closure occurs within 37 days of the fee posting. State this condition rather than promising a refund unless the fee-posting date has been verified.
- Closing a card can reduce available credit and may affect credit utilization and credit score, particularly for high-limit or older accounts.

## Failure handling

- If identity verification is incomplete, request the missing second identity field and stop before any account action.
- If account lookup returns multiple possible target cards, ask the customer to distinguish them.
- If a required check tool is unavailable, denied, malformed, or returns an ambiguous result, do not assume eligibility; communicate the limitation and use the supported escalation path when necessary.
- Never substitute another card or checking account, fabricate an ID, or report an account as closed or paid without a successful tool response.
- Never repeat a payment, closure, waiver, downgrade, or other state-changing operation after an `UNKNOWN` result.
