---
name: credit-card-closure-with-payoff-and-retention
description: Handle a verified customer's request to close a Rho-Bank credit card, including an authorized payoff from a Rho-Bank checking account, mandatory eligibility checks, retention workflow, and final closure. Use when a customer asks to close a card or needs to pay a card balance before closure.
---

# Credit Card Closure, Payoff, and Retention

Follow this workflow in order. Treat a closure as an irreversible action: never close a card merely because it was named in a prior lookup, and never use a checking account until identity, account ownership, balance, amount, and authorization are confirmed.

## 1. Identify the customer and card

1. Obtain a customer identifier or enough information to look up the customer using the declared normal banking lookup tools.
2. Retrieve that customer's credit-card accounts and select the account matching the card the customer requested. Confirm the selected account belongs to the authenticated customer.
3. Obtain the current time for the verification audit.
4. Complete standard identity verification before any payoff, downgrade, fee waiver, or closure:
   - Match **two of these four fields** the customer provides against the profile: date of birth, email, phone number, address.
   - A name identifies a record but does not replace one of these two fields.
   - After two fields match, call `log_verification` with the complete profile values and the current timestamp.
   - If two fields cannot be verified, stop and request another verification field. Do not disclose account details or take an action.

## 2. Resolve a balance, if one exists

Closure requires a current outstanding balance of exactly $0.00.

1. Retrieve the current card balance. Do not rely on an earlier balance after any payment.
2. If the balance is positive, explain that it must be paid before closure. A checking-funded payoff requires the customer's explicit authorization of the amount and funding source.
3. Locate the customer's Rho-Bank checking account using a declared, supported checking-account lookup when available. Verify it belongs to the customer, is a checking account, and has sufficient available funds.
   - If there is more than one eligible checking account, ask the customer which one to debit.
   - If no supported lookup is available, or no eligible account exists, request the account ID or direct the customer to an alternative payoff method. Never invent an account-lookup tool name or guess an account ID.
4. Unlock `pay_credit_card_from_checking_9182`, then call it with exactly `user_id`, `checking_account_id`, `credit_card_account_id`, and positive `amount`. The amount must not exceed either the available checking balance or the card's outstanding balance.
5. Read the payment response and re-retrieve or otherwise confirm the card's current balance is $0.00. If the payment fails, is incomplete, or leaves a balance, do not continue to closure.

## 3. Confirm closure eligibility immediately before retention or closure

Confirm every requirement using current records; do not treat a customer assertion as a system check where a relevant status check is available.

- **Balance:** exactly $0.00, with no unresolved pending transaction that could post.
- **Disputes:** no active or pending transaction dispute. If one exists or its status cannot be confirmed, do not close.
- **Age:** calculate from the account-open date; the account must be at least 60 days old.
- **Replacement cards:** immediately before proceeding, unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty list is clear. If any order is not clearly `delivered` or `cancelled` (such as pending or shipped), closure is blocked until it reaches a final state or is cancelled.

When a condition fails, clearly say which condition remains unresolved and what must happen next. Do not make a retention offer or call the closure tool while closure is ineligible.

## 4. Follow the retention protocol for eligible accounts

1. Unlock and call `get_closure_reason_history_8293` with the selected `credit_card_account_id`.
2. If the account has a closure-reason record within the past year, skip all retention offers and proceed to the final-closure section after reconfirming the customer's intent.
3. Otherwise, obtain the customer's reason, map it only to one allowed value, and unlock/call `log_credit_card_closure_reason_4521` with **only**:
   - `credit_card_account_id`
   - `user_id`
   - `closure_reason`

   Allowed reasons are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.

4. Address the stated reason without pressure:
   - **annual_fee:** customers with at least two years of tenure may be offered a one-year waiver. If they accept, unlock/call `apply_credit_card_account_flag_6147` using `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format. Customers below two years may instead choose a same-category no-fee downgrade.
   - **not_using_card:** remind them of relevant benefits and optionally suggest a recurring subscription.
   - **found_better_card:** ask which features matter; only offer a Rho-Bank alternative if a supported product record establishes a comparable option.
   - **unhappy_with_rewards:** discuss available enrollment or reward-maximization options only when supported by the available account/product information.
   - **negative_experience:** apologize, gather details, and escalate if warranted.
5. If the customer still wishes to close, make one tier-appropriate offer: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium or above: 5,000 points or $50 statement credit. Determine tier from supported account/product information; do not guess a tier.
6. Ask for and honor the customer's decision. If they accept an alternative, perform only the explicitly authorized alternative. For a business-card downgrade, unlock/call `downgrade_credit_card_3847` with `target_card_type` `Business Bronze Rewards Card`; for a personal card use `Bronze Rewards Card`. Explain that history, account number, and credit line are preserved, while benefits change.

## 5. Close only after the customer declines retention or prior history requires direct closure

1. Reconfirm the customer wants the selected account closed and verify all eligibility conditions remain satisfied, especially the current balance and replacement-order check.
2. Unlock `close_credit_card_account_7834` and call it with `credit_card_account_id` and `user_id` for the verified customer and selected card only.
3. Report the tool result accurately. Do not claim closure, a refund, or a confirmation email unless the tool response confirms it.

## 6. Required post-closure communication

After a successful closure, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Remaining rewards may be redeemed for 45 days after the closure request; unredeemed rewards are forfeited afterward. For cards whose rewards are recorded as cash-back points, state the value only if the applicable product policy supports it (1 point = $0.01 for the documented cash-back cards).
- A full annual-fee refund may apply only if closure occurs within 37 days of the annual-fee posting. Do not promise a refund without the fee-posting date and confirmation.
- Closing a card can affect available credit, utilization, and potentially credit score.

## Failure handling

- Do not retry a payment, closure, waiver, downgrade, or other state-changing operation after an `UNKNOWN` result; investigate or escalate instead.
- If a named discoverable tool cannot be unlocked or returns an ambiguous response, do not substitute a guessed tool, parameter, account ID, status, or result.
- Use only the documented arguments for specialized tools. Tool recommendations or this workflow do not themselves execute banking actions.
