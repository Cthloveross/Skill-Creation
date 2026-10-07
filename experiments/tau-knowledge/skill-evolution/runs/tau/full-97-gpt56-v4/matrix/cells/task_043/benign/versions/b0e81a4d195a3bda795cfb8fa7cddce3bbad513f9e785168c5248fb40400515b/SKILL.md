---
name: credit-card-account-closure
summary: Safely handle a verified customer's request to close a credit-card account, including mandatory eligibility checks, retention boundaries, and closure communication.
description: Use for credit-card closure requests when the agent must identify the requested account, verify identity, determine whether closure is allowed, optionally follow the retention protocol, and use the normal banking closure tool only when all prerequisites are confirmed.
---

# Credit Card Account Closure

## Scope and safety boundary

Use this Skill for a request to close a credit-card account. Never close an account unless identity has been verified and **all** closure requirements are confirmed for the specific account:

- outstanding balance is exactly $0.00;
- there are no active or pending transaction disputes;
- the account has been open at least 60 days; and
- there is no pending replacement-card order (all replacement orders, if any, must be delivered or cancelled).

A customer name or account lookup alone is not identity verification. Confirm two of the four identity fields (date of birth, email, phone number, and address) against the customer record, then log the verification with the current timestamp before taking an account-changing action.

Do not treat an unknown eligibility condition as passing. Do not make retention offers when any eligibility condition fails or remains unconfirmed.

## Runtime workflow

1. **Identify and verify the customer.**
   - Locate the customer using an identifier supplied by the customer and retrieve the customer profile using the available normal lookup tool.
   - Ask for enough identity information to confirm two of date of birth, email, phone number, and address. Do not disclose profile values in the question.
   - Obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete profile fields and timestamp only after two fields match.

2. **Identify the intended card account.**
   - Use `get_credit_card_accounts_by_user` for the verified `user_id`.
   - Match the account to the card the customer named; if more than one could match, ask the customer to disambiguate. Do not substitute a different account.
   - Record the `credit_card_account_id`, `user_id`, opening date, balance, tier, and rewards balance for later steps.

3. **Check closure eligibility before discussing retention.**
   Check in this order and stop at the first blocker. Clearly tell the customer what must be resolved.
   - Pending disputes: use an available authorized account/dispute source. If no supported source can establish the result, say the dispute status must be confirmed and do not proceed.
   - Replacement order: unlock `get_pending_replacement_orders_5765`, then call it with only `credit_card_account_id`. An empty orders collection passes. Any pending, shipped, or otherwise non-final order blocks closure. Orders pass only if every returned order is clearly delivered or cancelled. Treat ambiguous output as a blocker and retry/escalate as appropriate.
   - Account age: calculate age from the account opening date and current date. It must be at least 60 calendar days.
   - Balance: the current outstanding balance must be $0.00 exactly. Pending transactions should post before the customer pays the full statement balance.

   `scripts/evaluate_closure_eligibility.py` can consistently evaluate supplied dates, balance, dispute status, and replacement statuses. It is advisory only: the executor must obtain the underlying facts from authorized banking tools.

4. **If blocked, do not retain or close.**
   Explain the specific blocker and the next step. For a nonzero balance, explain that the balance must be paid down to $0.00 (after pending transactions post) before the closure request can proceed. Do not call reason logging, retention, downgrade, waiver, or closure tools for an ineligible account.

5. **If eligible, follow the retention protocol.**
   - Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id`.
   - If a closure-reason record exists within the past year, skip offers and proceed to the customer's closure decision.
   - Otherwise ask the reason if it is not already clear. Log one allowed reason using `log_credit_card_closure_reason_4521` with exactly `credit_card_account_id`, `user_id`, and `closure_reason`. Allowed values are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.
   - Address the stated concern. For annual-fee concerns, a customer of at least two years may be offered a one-year annual-fee waiver using `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, a one-year-from-today `MM/DD/YYYY` expiration date, and reason `loyalty_benefit`. A customer under two years may instead choose a same-category no-fee downgrade. Do not apply either option without the customer's agreement.
   - If the customer still wishes to close, make at most one tier-appropriate retention offer: entry $5/500 points, mid-tier $20/2,000 points, premium-and-above $50/5,000 points. Do not pressure the customer.

6. **Close only after the customer confirms the decision to close.**
   Unlock `close_credit_card_account_7834` and call it with exactly the verified `credit_card_account_id` and `user_id`. Use the normal banking tool result as the source of truth; never claim closure succeeded if it did not.

7. **Post-closure communication.**
   Confirm that a confirmation email and final statement will arrive within several business days. State that remaining rewards may be redeemed for 45 days after the closure request and are forfeited after that. If relevant, explain that a full annual-fee refund is available only when closure is within 37 days of the fee posting. If asked, explain that closing may affect credit utilization, available credit, and potentially the customer's credit score.

## Helper invocation

The helper reads one JSON object from standard input and writes one JSON object to standard output. Example:

```sh
python3 scripts/evaluate_closure_eligibility.py <<'JSON'
{"current_date":"2025-01-15","date_of_account_open":"2024-10-01","current_balance":"0.00","pending_disputes":false,"replacement_orders":[{"status":"delivered"}]}
JSON
```

Required input fields are `current_date`, `date_of_account_open`, `current_balance`, `pending_disputes`, and `replacement_orders`. Dates accept `YYYY-MM-DD`, `MM/DD/YYYY`, or a timestamp beginning with one of those dates. `pending_disputes` must be JSON `true` or `false`; use `null` when unknown. `replacement_orders` must be a JSON list of objects containing `status`, or `null` when unknown.

A valid result has `eligible` (boolean), `blockers` (list), `account_age_days` (integer or null), and `normalized_balance` (decimal string or null). Only an output with `eligible: true` supports proceeding to retention/closure; invalid or incomplete facts are reported as blockers.
