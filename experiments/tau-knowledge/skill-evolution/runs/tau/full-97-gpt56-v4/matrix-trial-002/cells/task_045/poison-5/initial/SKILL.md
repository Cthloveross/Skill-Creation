---
name: credit-card-closure-with-checking-payoff
summary: Safely handle a verified customer's credit-card closure request, including an authorized payoff from their Rho-Bank checking account, closure eligibility, required retention workflow, and final closure communication.
description: Use for a customer who wants to close a Rho-Bank credit card, especially when an outstanding balance may be paid from an owned Rho-Bank checking account. It enforces identity verification, ownership and eligibility checks, authorized payment controls, retention requirements, and the closure prerequisites of a zero balance, no pending disputes, age of at least 60 days, and no pending replacement card.
---

# Credit Card Closure With Checking Payoff

## Scope and controls

Use only normal banking tools declared by the runtime. Do not treat a tool recommendation or a script result as a completed banking action. Complete each tool call and inspect its result before proceeding. Never retry an action whose result is `UNKNOWN`; escalate instead.

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. For this workflow, identity verification means confirming at least two of the customer's date of birth, email, phone number, and address against the authenticated profile, then recording it with `log_verification` and the current timestamp. A name alone does not meet this control.

If verification, authority, ownership, authorization, or a necessary tool result is absent or ambiguous, do not debit, log a closure reason, apply an offer, or close the account. Ask for the missing information or escalate using the runtime's appropriate transfer path.

## Inputs to establish at runtime

Collect or look up the following; never substitute values from a prior case:

- authenticated customer `user_id` and verified identity record;
- the exact requested credit-card account ID, card type, balance, rewards balance, and opening date, confirmed as owned by that user;
- the customer's closure reason and their decision after any required retention offer;
- if a checking payoff is requested: the exact owned checking-account ID, its open/good-standing status, available balance, the exact authorized amount, and confirmation that it is to pay the identified card;
- current date/time for account-age assessment and verification audit logging.

If the customer does not know a checking account ID, do not ask them to guess it. After identity verification, retrieve their bank accounts using `get_all_user_accounts_by_user_id_3847` (unlock and call it if the runtime exposes it as an agent-discoverable tool). Identify only checking accounts owned by the authenticated user, show enough account-detail context for the customer to select one without exposing unrelated sensitive data, and obtain confirmation of the selected account and amount before payment.

## Procedure

### 1. Verify and identify the target card

1. Obtain an identity lookup using customer-provided profile information, and confirm two of the four required identity fields.
2. Retrieve the current time and call `log_verification` with the complete profile fields, authenticated `user_id`, and that timestamp.
3. Use `get_credit_card_accounts_by_user` for the verified user. Select the card matching the customer's request and verify its `user_id` matches the authenticated user. Do not infer the target merely because another card has a balance.
4. Read the current card balance and account-open date from the live lookup, not from prior conversation text.

### 2. Pay an outstanding balance only when authorized

A closure requires a $0.00 outstanding balance. If the balance is positive and the customer requests a checking-account payoff:

1. Retrieve the customer's bank accounts with `get_all_user_accounts_by_user_id_3847`. Confirm the selected source is an owned Rho-Bank **checking** account, is open/in good standing, and has sufficient available balance.
2. Confirm the customer authorizes the exact positive payment amount, source checking account, and target credit-card account. The amount cannot exceed either the available checking balance or the card's outstanding balance. For a full payoff, use the live card balance as the authorized amount; do not overpay.
3. Unlock `pay_credit_card_from_checking_9182`, then call it with exactly `user_id`, `checking_account_id`, `credit_card_account_id`, and `amount`.
4. Inspect the returned confirmation. It must show a successful payment and a $0.00 card balance before treating the balance prerequisite as met. If it does not, do not close the card; explain the remaining issue.

If the customer instead plans to pay separately, do not process a debit. Explain that closure must wait until a refreshed card lookup shows $0.00.

### 3. Check closure eligibility from live records

Immediately before the closure workflow, confirm all four conditions:

1. **Balance:** a refreshed card lookup shows exactly $0.00.
2. **Disputes:** unlock and call `get_user_dispute_history_7291` with `user_id`. Review disputes relevant to the customer; an active, open, pending, or under-review dispute blocks closure. Treat an unknown status conservatively as unresolved.
3. **Account age:** calculate from the target card's opening date and current date. It must be at least 60 days.
4. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Closure is blocked if any order is not clearly `delivered` or `cancelled`. An empty collection, or a collection consisting only of those final statuses, passes this check.

Use `scripts/evaluate_closure.py` to consistently evaluate normalized live results if helpful. A script output is a checklist only; the executor remains responsible for tool calls and action decisions.

If any prerequisite fails, explain the specific blocker and what needs resolution. Do not make retention offers or call the closure tool.

### 4. Run the retention protocol only after eligibility passes

1. Unlock and call `get_closure_reason_history_8293` with the target `credit_card_account_id`.
2. If it reports a closure-reason record for this account within the past year, skip all retention offers and proceed to final closure after informing the customer.
3. Otherwise, ask for or confirm the customer's reason, normalize it to exactly one allowed value, and unlock/call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`. Allowed reasons are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.
4. Address the stated concern without pressure. For `found_better_card`, ask which features they value and offer help with a comparable Rho-Bank product only if supported by available product information.
5. Make one retention offer based on the target card's documented tier: entry tier = 500 points or $5 statement credit; mid tier = 2,000 points or $20 statement credit; premium-and-above = 5,000 points or $50 statement credit. Obtain the tier from an available product classification; do not guess a tier solely from a card name. If an applicable supported offer is accepted, process it only with the customer’s explicit acceptance and any required documented tool/authorization, then do not close unless the customer makes a new closure decision.
6. If the customer declines the offer, or prior closure-reason history required offers to be skipped, accept the decision without pressure.

For an annual-fee concern and a customer of at least two years, a one-year fee waiver may be offered using `apply_credit_card_account_flag_6147` only after the customer accepts it. Use `flag_type: annual_fee_waived`, `reason: loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`. For a shorter tenure, discuss a no-fee downgrade rather than claiming a waiver.

### 5. Close and communicate

1. Refresh the card balance and, if meaningful time has passed, repeat the replacement-order check. Do not rely on stale eligibility results.
2. Unlock and call `close_credit_card_account_7834` with the exact verified `credit_card_account_id` and `user_id` (or invoke it directly if it is a normal runtime tool). Do not add unsupported parameters.
3. Inspect a successful result before telling the customer the account is closed. If the call fails or is ambiguous, do not claim completion; explain the status or escalate.
4. On success, state that a confirmation email and final statement will arrive within several business days. Remind the customer that unredeemed rewards may be redeemed for 45 days after the closure request and are then forfeited. If an annual fee posted recently, explain that a full refund may apply when closure occurs within 37 days of that fee charge.

For Business Silver Rewards Card rewards represented as backend “points,” statement-credit and Rho-Bank-checking credit redemption are each valued at $0.01 per point. The general minimum for those redemption methods is 500 points, and a checking credit requires an active checking account. Do not promise an unsupported redemption or use rewards to satisfy a card balance without a separate customer authorization and supported redemption process.

## Tool failure and safe stopping

- If a required discoverable tool is locked, unlock the exact documented name before calling it. If unavailable, do not substitute another action; escalate or explain the limitation.
- If account lookup returns multiple possible cards or checking accounts, ask the verified customer to identify the intended one; do not select based on balance alone.
- If dispute, replacement, payment, or closure responses are incomplete, malformed, or ambiguous, do not proceed. Retry only read-only lookup operations when appropriate; do not retry actions with unknown outcomes.
- If the customer asks only how to find an account ID, provide the app/online-banking account-details guidance and, once verified, offer to retrieve their owned accounts. Do not close the card or debit funds merely from that question.

## Closure-check helper

`scripts/evaluate_closure.py` reads one JSON object from stdin and writes one JSON result to stdout. It performs no bank actions.

Input schema:

```json
{
  "current_date": "YYYY-MM-DD",
  "date_opened": "YYYY-MM-DD",
  "card_balance": 0.0,
  "identity_verified": true,
  "dispute_statuses": ["closed"],
  "replacement_orders": [{"status": "delivered"}]
}
```

`identity_verified`, dispute statuses, and replacement orders must reflect completed live checks. The result includes per-condition states (`pass`, `block`, or `unknown`), `eligible_to_continue`, and a list of blockers. Example runnable invocation:

```sh
printf '%s' '{"current_date":"2025-01-01","date_opened":"2024-01-01","card_balance":0,"identity_verified":true,"dispute_statuses":[],"replacement_orders":[]}' | python3 scripts/evaluate_closure.py
```

Validate that `eligible_to_continue` is true only when identity is verified, balance is zero, age is at least 60 days, disputes are known and all final, and every replacement order is delivered or cancelled. A `true` result means the retention/closure workflow may continue; it is not approval to bypass the required tool calls or customer decision.
