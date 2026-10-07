---
name: credit-card-account-closure
version: 1.1.0
description: Process a verified customer's credit-card closure request safely, including live eligibility checks, closure-history review, reason logging, tailored retention, account closure, and required post-closure disclosures. Use whenever an authenticated customer asks to close a credit card account.
---

# Credit Card Account Closure

Use live system data and the active conversation. Do not accept a customer's statement about balance, disputes, replacement cards, account age, or prior activity as a substitute for the required checks. Do not close an account unless it belongs to the authenticated customer and every prerequisite is confirmed.

## Identify and verify the customer

1. Identify the requested credit-card account and obtain its `credit_card_account_id` and canonical `user_id`. If more than one account could match, ask the customer which account they mean.
2. Obtain the current time using `get_current_time`.
3. Use the customer profile to verify two of the following customer-confirmed fields: date of birth, email, phone number, or address.
4. After two fields match, call `log_verification` with all required fields: `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`.
5. If verification fails or fewer than two fields are confirmed, do not disclose account details or perform closure actions. Request another verification field or follow the normal escalation process.

## Confirm closure eligibility before retention or closure

Look up the customer's credit-card accounts to confirm the requested account, ownership, opening date, and current balance. The account must meet **all** conditions below before any retention offer or closure action:

1. The balance is exactly `$0.00`.
2. The account has been open at least 60 days.
3. Unlock and call `get_user_dispute_history_7291` with exactly `user_id`. Any active, pending, open, under-review, or otherwise unclear non-final dispute blocks closure. Closed or resolved disputes do not block closure.
4. Unlock and call `get_pending_replacement_orders_5765` with exactly `credit_card_account_id`. An empty result passes. Any pending, shipped, awaiting-receipt, awaiting-activation, or other non-final order blocks closure. All returned orders must be clearly delivered or cancelled before proceeding.

If a condition fails or a tool result is missing, malformed, partial, or ambiguous, explain the applicable prerequisite and do not make a retention offer or invoke closure. Retry an unclear check where appropriate, otherwise escalate.

## Retention workflow after eligibility passes

1. Unlock and call `get_closure_reason_history_8293` with exactly `credit_card_account_id`.
2. If the account has a closure-reason record within the past year, skip reason logging and retention. Thank the customer and proceed directly to closure.
3. If there is no such record, establish the reason and normalize it to exactly one permitted value:
   - `annual_fee`
   - `not_using_card`
   - `found_better_card`
   - `unhappy_with_rewards`
   - `simplifying_finances`
   - `negative_experience`
   - `other`
4. Unlock and call `log_credit_card_closure_reason_4521` using **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
5. Address the logged concern before making a retention offer:
   - **`found_better_card`:** Ask which specific ongoing rewards, benefits, or features attracted the customer to the competing card. If Rho-Bank has a comparable or better product based on those identified features, offer to help the customer apply for it instead of closing the current account. Do not claim a comparable product exists unless supported by available product information. If the customer still wishes to close, continue to the one retention offer.
   - **`annual_fee`:** For tenure of at least two years, offer a one-year annual-fee waiver. If accepted, unlock and call `apply_credit_card_account_flag_6147` with `credit_card_account_id`, `user_id`, `flag_type` `annual_fee_waived`, `expiration_date` exactly one year from today in `MM/DD/YYYY`, and `reason` `loyalty_benefit`. For shorter tenure, offer a permanent no-annual-fee downgrade that preserves account history.
   - **`not_using_card`:** Remind the customer of relevant benefits and suggest a recurring subscription if appropriate.
   - **`unhappy_with_rewards`:** Review bonus-category enrollment and discuss ways to maximize rewards based on spending patterns.
   - **`negative_experience`:** Apologize, gather relevant details, and escalate to a supervisor when warranted. A modest goodwill credit may be considered for a service complaint.
6. If the customer still wants closure, make exactly one tier-appropriate retention offer. Do not pressure the customer or repeat an offer already declined in the conversation.

### Retention tiers

- Entry tier: **500 bonus points or a $5 statement credit**.
- Mid tier: **2,000 bonus points or a $20 statement credit**.
- Premium and above: **5,000 bonus points or a $50 statement credit**.

**Gold Rewards Card is premium-tier.** Therefore, for a Gold Rewards Card, the only compliant standard retention choice is **5,000 bonus points or a $50 statement credit**. Do not use the mid-tier 2,000-point/$20 offer for Gold. Gold rewards stored as points represent cash back at $0.01 per point; when useful, 5,000 points may be described as worth $50 cash back.

If the customer declines the offer, or retention was correctly skipped due to a recent closure-history record, thank them and proceed without pressure. If the customer accepts a retention or alternative-product solution, do not close the account unless they later make a new closure request.

## Close the account

Only after identity is logged, every eligibility check passes, and the retention workflow is completed or properly skipped:

1. Unlock `close_credit_card_account_7834`.
2. Call it with exactly `credit_card_account_id` and `user_id`.
3. Do not substitute a card identifier for an account identifier, and do not use identifiers belonging to another customer.
4. Report only the actual result. If the closure tool fails or is unclear, do not say the account is closed; retry only when appropriate or escalate with the failure context.

## Communication after successful closure

Tell the customer that a confirmation email and final statement will arrive within several business days. State that unredeemed rewards can be redeemed for **45 days after the closure request** and are forfeited after that period. If an annual fee posted recently, state that a full refund may apply only if closure occurs within 37 days of the fee charge; do not promise a refund without confirming eligibility.

## Optional deterministic state evaluation

`scripts/evaluate_closure_state.py` checks normalized workflow facts only; it never calls tools and never authorizes account closure. Invoke it with `python scripts/evaluate_closure_state.py < closure_state.json`.

The script reads one JSON object from stdin and emits one JSON object. Required fields are `current_date`, `identity_logged`, and `account`; `account` contains `account_id`, `date_of_account_open`, `current_balance`, and, when retention is needed, `card_type`. `disputes` and `replacement_orders` are `null` until checked or lists of objects with `status`. `recent_closure_record` is `true`, `false`, or `null`. When history is false, provide permitted `closure_reason`, `reason_logged`, and `retention` fields: `concern_addressed`, `tier`, `offered`, and `declined`.

For `found_better_card`, set `concern_addressed` true only after asking which features attracted the customer and handling any supported comparable-product option. Set `tier` to `premium` for Gold Rewards Card. Immediately before the real closure tool call, validate that `ready_to_close` is true and `blockers` is empty.
