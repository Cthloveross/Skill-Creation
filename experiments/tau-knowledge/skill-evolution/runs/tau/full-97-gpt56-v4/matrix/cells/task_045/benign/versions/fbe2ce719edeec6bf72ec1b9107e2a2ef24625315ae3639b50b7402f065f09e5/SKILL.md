---
name: credit-card-account-closure
version: 1.0.0
description: Safely handle a customer's request to close a Rho-Bank credit card account, including identity verification, eligibility gating, required internal checks, retention sequencing, optional payoff assistance, and closure communication.
---

# Credit Card Account Closure

Use this Skill whenever a customer asks to close a credit card account or asks about eligibility for closure. A closure is a consequential bank action: verify identity, identify the exact account, and never submit closure until every required eligibility condition has been confirmed.

## Required eligibility

An account can be closed only if all of the following are true:

1. Outstanding balance is exactly `$0.00`.
2. There are no active or pending credit-card disputes.
3. The account has been open at least 60 days.
4. There are no pending replacement-card orders. A returned replacement order blocks closure unless **every** order is clearly `delivered` or `cancelled`.

Do not treat account age or an old account-opening date as a substitute for the other live checks. Pending disputes and replacement orders must be checked as part of the closure review; check replacement orders immediately before a closure attempt.

## Runtime workflow

### 1. Verify identity before account-specific action

1. Obtain enough information to locate the customer, such as their name, email, or user ID, and use the applicable read-only user lookup tool.
2. Ask the customer to confirm at least two of these four identity fields: date of birth, email, phone number, and address. Do not supply the answers in the question.
3. Compare the supplied values with the customer record. If two fields match, get the current timestamp with `get_current_time` and call `log_verification` with the complete record fields and timestamp required by that tool.
4. If verification fails or remains incomplete, do not disclose account details, make account changes, or proceed with closure. Ask for another eligible verification field or use the appropriate support path if resolution is not possible.

A name or account identifier alone locates a record but is not successful identity verification.

### 2. Identify the requested account precisely

Call `get_credit_card_accounts_by_user` using the verified `user_id`. Match the customer’s requested card type to exactly one account and use its account-level ID, not a card number or a transaction identifier.

If zero or multiple accounts match, ask a clarifying question. Do not choose an account based only on another account’s balance or transaction history.

### 3. Gate on eligibility before retention

Review the target account’s balance and opening date. If a known condition already makes closure ineligible (especially a nonzero balance), clearly tell the customer what needs to be resolved and **do not** begin retention, log a closure reason, apply a retention benefit, downgrade the account, or call the closure tool.

For a nonzero balance:

- Explain that the requested account must be paid to `$0.00` before it can be closed.
- Do not take funds from another account without the customer explicitly choosing that option and authorizing the payment amount.
- If the customer asks to pay from a Rho-Bank checking account, first ensure identity verification, identify the checking account, confirm sufficient available funds and the current card balance, and obtain explicit authorization for the exact amount. Unlock `pay_credit_card_from_checking_9182`, then call it with exactly `user_id`, `checking_account_id`, `credit_card_account_id`, and positive `amount`. The amount cannot exceed either balance.
- After a payment, re-check the credit-card balance before considering closure. Any tool failure or ambiguous result means do not retry blindly or claim it was paid.

If the account is too new, explain the 60-day requirement. If a dispute is active/pending, explain that it must first be fully resolved. If a replacement order is pending, explain it must be delivered or cancelled. Do not offer retention while any closure eligibility requirement is unmet.

### 4. Complete live checks only when closure can proceed

Once the account is otherwise eligible and the customer still seeks closure:

1. Unlock and call `get_user_dispute_history_7291` with the verified `user_id`. Treat statuses such as `open` or `under_review`, and any active/pending status, as blocking. If account association cannot be determined from the response, do not assume the target account is clear; clarify or escalate.
2. Unlock and call `get_pending_replacement_orders_5765` with the exact `credit_card_account_id` immediately before closure. An empty result passes. If any returned order is not clearly `delivered` or `cancelled`, closure is blocked.
3. Reconfirm balance is `$0.00` and account age is at least 60 days. If any check is unavailable, malformed, or ambiguous, do not close; explain that the check could not be completed and follow the supported escalation path as appropriate.

### 5. Retention protocol, only after eligibility passes

After every closure condition passes, unlock and call `get_closure_reason_history_8293` for the target `credit_card_account_id`.

- If a record exists within the past year, skip retention offers and proceed to the customer’s closure decision.
- If no recent record exists, ask the customer’s reason if it is not already clear, map it to exactly one allowed value, and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
  - Allowed values: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, `other`.
- Address the stated concern, then make at most one appropriate retention offer if the customer still wants to close. Do not pressure the customer.

For an annual-fee concern, an account holder with at least two years’ tenure may be offered a one-year fee waiver. Only after acceptance, call `apply_credit_card_account_flag_6147` using `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from the current date formatted `MM/DD/YYYY`. A shorter-tenured customer may instead choose a no-annual-fee downgrade.

A downgrade is not a closure and must never be performed merely because it seems helpful. It requires the customer’s request/confirmation, identity verification, and acknowledgement of benefit changes. For a business card, the only listed no-annual-fee target is `Business Bronze Rewards Card`; call `downgrade_credit_card_3847` with the verified user and target-account IDs only after that confirmation.

If the customer declines the offer, or retention is skipped due to prior attempts, accept the decision without further pressure.

### 6. Submit the closure

Immediately before submission, ensure the verified user, exact account, and all four eligibility checks remain valid. Unlock and call `close_credit_card_account_7834` using the exact `credit_card_account_id` and authenticated `user_id` required by the closure tool. Do not state that the account is closed unless the tool returns a successful, unambiguous confirmation. Do not repeat a closure request with an unknown result.

### 7. Final customer communication

After confirmed closure, state that a confirmation email and final statement will arrive within several business days. Remind the customer that:

- remaining rewards may be redeemed for 45 days after the closure request, then are forfeited; and
- a full annual-fee refund may apply if the closure occurs within 37 days of the fee posting.

When explaining rewards on a cash-back card, stored “points” equal cash back at `$0.01` per point for statement-credit or Rho-Bank-checking-credit redemption. Calculate the displayed value as `points × 0.01` and label it as cash-back value; do not imply that rewards will be forfeited before closure is requested.

## Response style and safety

Be specific about the blocking condition and the next customer-controlled step. Avoid claiming that unperformed checks passed. Do not expose unrelated account information. Tools are used only through their declared normal banking interfaces; recommendations in this Skill do not themselves execute a payment, downgrade, retention action, or closure.

## Example tool sequence (abstract)

A typical successful path is:

`user lookup → customer confirms two identity fields → get_current_time → log_verification → get_credit_card_accounts_by_user → eligibility review → get_user_dispute_history_7291 → get_pending_replacement_orders_5765 → get_closure_reason_history_8293 → (optional reason logging/retention) → close_credit_card_account_7834`.

The sequence stops at the first unmet or uncertain prerequisite. For example, a nonzero balance produces an explanation and, only if the customer expressly requests and authorizes it, an optional checking-to-card payment workflow; it does not produce a closure or retention offer.
