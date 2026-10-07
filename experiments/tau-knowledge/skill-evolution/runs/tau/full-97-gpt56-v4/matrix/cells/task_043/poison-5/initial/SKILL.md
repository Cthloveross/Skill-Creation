---
name: credit-card-closure-and-retention
version: 1.0.0
description: Handle a verified customer's request to close a credit card, including mandatory closure eligibility checks, annual-fee retention handling, approved closure actions, and required customer communications.
---

# Credit Card Closure and Retention

Use this Skill when a customer asks to close a credit card account or says they want to close because of an annual fee. Follow the sequence below; do not close an account or make retention offers until the applicable prerequisites are satisfied.

## Required inputs

Obtain and confirm:

- The authenticated customer's `user_id`.
- The exact `credit_card_account_id` for the card to be closed. If the customer identifies only a card type, retrieve their card accounts and select only an unambiguous matching account; otherwise ask for clarification.
- The customer's reason for closure, if eligibility permits progressing to retention.

## Identity verification

1. Retrieve the customer profile using an available supported lookup.
2. Ask the customer to confirm at least two of these fields: date of birth, email, phone number, and address. Do not present the stored values as the answers.
3. Once two fields match, call `get_current_time` and then `log_verification` with the complete required profile fields, `user_id`, and returned timestamp.
4. If identity cannot be verified, do not disclose account details or take account action.

## Find and inspect the requested account

Use `get_credit_card_accounts_by_user` after identity verification. Confirm the selected account belongs to the verified user and is the intended card. Treat account identifiers, balance, open date, and rewards returned by the tool as runtime data; never assume these values.

## Closure eligibility: required before retention or closure

Check eligibility before attempting retention. A closure requires all of the following:

1. No active or pending transaction disputes.
2. No pending replacement card order.
3. Account open for at least 60 days.
4. Outstanding balance exactly $0.00.

Use the available account/transaction information and appropriate authorized tools to establish the dispute and balance conditions. To check replacement activity, unlock `get_pending_replacement_orders_5765`, then call it with only `credit_card_account_id`. Treat any order other than clearly delivered or cancelled as pending. Make this check immediately before initiating closure.

If any requirement fails, explain the specific blocking condition(s) and what the customer must do (for example, wait for disputes, resolve/cancel a replacement, wait until the account reaches 60 days, or pay the balance in full after pending transactions post). Do **not** make a retention offer and do **not** call the closure tool. Do not claim that payment, dispute resolution, or a replacement cancellation occurred unless a supported tool confirms it.

## Retention flow after eligibility passes

1. Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id`.
2. If a closure-reason record exists within the past year, skip all retention offers. Tell the customer you will proceed with closure if they still want it.
3. Otherwise, ask why they want to close, normalize the response to exactly one allowed value, and unlock/call `log_credit_card_closure_reason_4521` with exactly:
   - `credit_card_account_id`
   - `user_id`
   - `closure_reason`: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`
4. Address the stated concern without pressure. For annual-fee concerns:
   - If the customer has held the account for at least two years, offer a one-year annual-fee waiver. Apply it only if the customer accepts: unlock `apply_credit_card_account_flag_6147` and call it with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format, plus the account and user IDs.
   - If the customer has held the account for less than two years, offer a permanent same-category downgrade to a no-annual-fee card rather than an annual-fee waiver. If accepted, confirm benefit changes and use `downgrade_credit_card_3847` with the matching permitted target: personal `Bronze Rewards Card` or business `Business Bronze Rewards Card`.
5. If the customer still wants to close, make one retention offer based on card tier: entry tier = 500 bonus points or $5 statement credit; mid tier = 2,000 points or $20; premium and above = 5,000 points or $50. Do not invent a tier; determine it from supported account/product information. If a required offer cannot be determined or performed using authorized tools, explain the limitation or escalate rather than fabricating an offer.
6. If the customer declines the applicable offer, or retention was skipped for a prior attempt, accept the decision without pressure and proceed to closure.

## Process closure

Immediately before submission, reconfirm that all closure eligibility conditions remain satisfied, including the replacement-order check. Unlock `close_credit_card_account_7834` and call it with only the verified `credit_card_account_id` and matching `user_id`. Do not call it for a different card or an unverified user.

If the tool reports an error or an eligibility conflict, do not retry blindly or claim success. Explain the supported outcome and request the needed resolution or use an appropriate human transfer when necessary.

## Required closure communication

After a successful closure request, tell the customer:

- They will receive a confirmation email and final statement within several business days.
- Any remaining rewards can be redeemed for 45 days after the closure request; unredeemed rewards are forfeited after that.
- A full annual-fee refund may apply if closure occurs within 37 days of the annual-fee posting.
- Closing a card can reduce available credit and may affect credit utilization and credit score.
- For a Platinum Rewards Card, any annual-fee rebate that has not reached its year-end evaluation and posting is not awarded if the account is closed first.

State only benefits and refunds supported by the policy; do not promise a refund or rebate outcome.

## Tool-use safeguards

- Unlock a discoverable agent tool before calling it.
- Supply only the documented arguments for each discoverable tool.
- Record verification only after successful two-field verification.
- Never substitute a card-level identifier for an account-level identifier.
- Transfer to a human agent with `account_closure_request` when the customer needs closure handling that cannot be safely completed with the available tools, or use another specifically applicable transfer reason when supported.
