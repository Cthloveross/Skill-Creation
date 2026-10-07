---
name: credit-card-account-closure
summary: Safely process a verified customer's request to close a credit card account, including eligibility checks, required retention handling, and final closure communication.
---

# Credit Card Account Closure

Use this Skill when a customer asks to close a credit card account. It supports account-specific closure eligibility, the required retention protocol, and the eventual closure action. It does **not** itself make banking changes; the executor must use the normal banking tools.

## Mandatory controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Treat an email address, account identifier, or account lookup as identification only, not identity verification.
2. Verify identity by having the requester confirm at least two of the four profile fields: date of birth, email, phone number, and address. Match the answers against the profile, obtain the current time, then call `log_verification` with all required profile fields and `time_verified`.
3. Confirm the requested account belongs to the authenticated `user_id`, and identify the exact credit-card account. Do not disclose information about other accounts.
4. Do not call `close_credit_card_account_7834`, apply a retention benefit, or downgrade a card without the customer's clear confirmation of that specific action. A request made before eligibility and retention disclosures should be reconfirmed immediately before closure.
5. If an account-specific fact cannot be verified from an available tool response, do not infer it. Explain the limitation and resolve or escalate it before closure.

## Required workflow

### 1. Identify, verify, and inspect the intended account

- Locate the profile and credit-card accounts only as needed to identify the requested card.
- Complete the verification record as described above.
- Retrieve the account list with `get_credit_card_accounts_by_user(user_id)` and ensure the selected account's `user_id` matches the verified customer.
- Read the account opening date, current balance, rewards balance, and card type. Review `get_credit_card_transactions_by_user(user_id)` for pending transactions associated with the selected account when the card/account association can be established. Pending transactions should post before closure.

### 2. Check closure eligibility, in this order

All conditions must pass. If any fails, explain the blocker, do not make a retention offer, and do not close the account.

1. **Disputes:** Unlock and call `get_user_dispute_history_7291` with `user_id`. The selected account must have no active or pending transaction dispute. Treat statuses such as `open` or `under_review` as blocking. If a dispute cannot be associated reliably to the requested account, resolve that ambiguity rather than declaring the account eligible.
2. **Replacement cards:** Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty order list passes. If any order is not clearly `delivered` or `cancelled` (for example, `pending` or `shipped`), closure is blocked until delivery or cancellation. Document the outcome in case notes if that capability is available.
3. **Account age:** The account must have been open for at least 60 days as of the current date.
4. **Balance:** The outstanding balance must be exactly $0.00. A customer must pay any remaining balance before closing.

Use `scripts/closure_plan.py` to consistently calculate age, interpret order status, validate the stated reason, and prepare a non-executing plan from data obtained at runtime.

### 3. Apply the retention protocol only after eligibility passes

1. Unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`.
2. If a closure-reason record exists for that account within the past year, skip retention offers and proceed to the final-confirmation stage without pressuring the customer.
3. Otherwise, obtain the customer's reason and map it to exactly one allowed value:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
4. Unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
5. Address the stated concern before making one retention offer:
   - `annual_fee`: for customers with at least two years of tenure, offer a one-year annual-fee waiver. Apply it only if accepted using `apply_credit_card_account_flag_6147` with `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`. For tenure under two years, offer a permanent same-category downgrade to a no-annual-fee card instead.
   - For an accepted downgrade, explain that history, account number, credit line, and reward value are preserved while benefits change. Use `downgrade_credit_card_3847` with `target_card_type` of `Bronze Rewards Card` for a personal card or `Business Bronze Rewards Card` for a business card.
   - `not_using_card`: remind the customer of relevant benefits and suggest a recurring subscription.
   - `found_better_card`: ask which features matter and offer help identifying a comparable available Rho-Bank card, if one exists; do not claim equivalence without support.
   - `unhappy_with_rewards`: review bonus-category enrollment and spending patterns where available.
   - `negative_experience`: apologize, gather details, and escalate to a supervisor when warranted. Do not promise a goodwill credit without an authorized process.
6. If the customer still wants to close, make one offer based on the card tier: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium and above: 5,000 points or $50 statement credit. Do not repeat or stack offers. If declined, accept the decision without pressure.

### 4. Close only after final confirmation

After an eligible customer declines retention, or retention is skipped due to prior attempts, obtain a clear final confirmation to close the identified account. Unlock and call `close_credit_card_account_7834` with exactly:

```json
{"credit_card_account_id":"<selected account id>","user_id":"<verified user id>"}
```

If the tool fails or returns an ambiguous result, do not state that the account closed. Report the issue and use the supported escalation path if needed.

### 5. Required customer communication

When closure is submitted successfully, state that a confirmation email and final statement will arrive within several business days. Also state:

- Unredeemed rewards may be redeemed for 45 days after the closure request, after which they are forfeited.
- If an annual fee was charged within the prior 37 days, a full refund may apply.
- Closing a card can affect credit utilization and available credit, potentially affecting the customer's credit score.

For cash-back cards whose stored rewards are labelled points, explain that one stored point is worth $0.01 when redeemed as a statement credit or Rho-Bank checking credit. Do not assume a card is cash-back without product support.

## Planner script

`scripts/closure_plan.py` is a deterministic planning and validation helper. It reads one JSON object from standard input and emits one JSON object to standard output. It makes no tool calls and never performs a banking action.

Input fields:

```json
{
  "now": "YYYY-MM-DD or timestamp",
  "account": {
    "credit_card_account_id": "string",
    "user_id": "string",
    "opened_on": "YYYY-MM-DD",
    "current_balance": "$0.00 or number",
    "reward_points": 0,
    "card_tier": "entry|mid|premium",
    "rewards_representation": "cash_back|points"
  },
  "disputes": [{"status": "closed", "credit_card_account_id": "string"}],
  "replacement_orders": [{"status": "delivered"}],
  "closure_history_within_year": false,
  "closure_reason": "found_better_card",
  "retention_status": "not_offered|offered_declined|offered_accepted|not_applicable",
  "final_closure_confirmed": false
}
```

`disputes` must include account identifiers for account-specific determinations. Supply `null` for `closure_history_within_year` while that check has not been completed. The output contains `eligibility`, blockers or review items, a retention recommendation, reward-value formatting when applicable, and the next non-executing workflow step.

Example runnable invocation:

```sh
python3 scripts/closure_plan.py <<'JSON'
{"now":"2025-01-01","account":{"credit_card_account_id":"acct","user_id":"user","opened_on":"2024-01-01","current_balance":"0.00","reward_points":0,"card_tier":"mid","rewards_representation":"cash_back"},"disputes":[],"replacement_orders":[],"closure_history_within_year":false,"closure_reason":"other","retention_status":"not_offered","final_closure_confirmed":false}
JSON
```

Validate the output before using it: `eligibility` must be `eligible` before moving to closure history; `next_step` must be `call_close_tool` before calling the closure tool; and the account/user identifiers in the plan must match the verified account selected at runtime.
