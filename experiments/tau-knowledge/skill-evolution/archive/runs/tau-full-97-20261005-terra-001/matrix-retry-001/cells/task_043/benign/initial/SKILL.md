---
name: credit-card-account-closure
version: 1.0.0
description: Safely handle a request to close a Rho-Bank credit card account, including identity verification, closure eligibility, optional checking-to-card payoff, required retention sequencing, and final closure communications. Use when a customer asks to close a credit card or says they want to avoid its annual fee.
---

# Credit Card Account Closure

## Purpose and safety boundary

Use this Skill for a customer-requested credit-card closure. Never close an account, make a payment, offer retention, or infer account ownership until the applicable prerequisites below are satisfied. Work only with the authenticated customer's account and use current tool results rather than stale observations.

A closure requires all of the following:

- outstanding balance is exactly `$0.00`;
- no active or pending transaction dispute;
- account has been open at least 60 days; and
- no replacement-card order remains in a non-final state.

A replacement order is final only when it is clearly `delivered` or `cancelled`. An empty orders list passes this check. A missing, malformed, or ambiguous result does **not** pass the check.

## Required interaction and tool workflow

### 1. Identify the requested account and verify identity

1. Locate the customer profile using information voluntarily provided by the customer, then retrieve the customer's credit-card accounts.
2. Confirm which exact account they want closed. Do not select a similarly named, business, or other card by assumption.
3. Before account-changing actions, verify at least two of the four profile fields: date of birth, email, phone number, and home address. Ask the customer to provide the values; compare them with the profile rather than reading sensitive values back unnecessarily.
4. On a successful two-field match, call `get_current_time`, then call `log_verification` with the complete retrieved profile fields and that timestamp. A name lookup alone is not identity verification.

If identity cannot be verified, do not disclose account details or take account actions.

### 2. Refresh and evaluate closure eligibility

Retrieve the current target-card balance and opening date. Immediately before any closure attempt:

1. Unlock and call `get_user_dispute_history_7291` with `user_id`. Review disputes associated with the target card and treat active/pending statuses (for example, `open` or `under_review`) as blocking. If the response cannot reliably be tied to the target card or a status is unclear, do not proceed until clarified.
2. Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any status other than clearly delivered or cancelled blocks closure.
3. Calculate account age against the current date and confirm it is at least 60 days.
4. Confirm the current outstanding balance is exactly zero.

The optional helper `scripts/closure_eligibility.py` consistently evaluates these facts. It is advisory only; the executor must still obtain the facts through the approved runtime tools.

If any check is unknown, malformed, or fails, explain the specific unresolved item and stop the closure/retention workflow. In particular, **do not make retention offers while the account is ineligible**.

### 3. If a balance remains, handle only an authorized payoff option

Tell the customer that the balance must be paid before the account can be closed. If they specifically want to pay from a Rho-Bank checking account:

1. Confirm the checking account belongs to the authenticated customer, has sufficient available funds, and obtain the checking account ID.
2. Confirm the exact positive payment amount and obtain explicit authorization to transfer it. It may not exceed either the checking balance or the target card's outstanding balance.
3. Unlock `pay_credit_card_from_checking_9182` and call it with **only** `user_id`, `checking_account_id`, `credit_card_account_id`, and numeric `amount`.
4. Use the confirmation/current account data to ensure the card balance is now `$0.00`, then repeat the eligibility checks needed immediately before closure.

Do not guess a checking-account ID, payment amount, funds availability, or authorization. If the customer will pay another way, wait until the payment posts and the current balance is zero.

### 4. Retention protocol (only after eligibility passes)

1. Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id`.
2. If the account has a closure-reason record within the past year, skip all retention offers and tell the customer that their closure request will be processed.
3. Otherwise, ask for the reason if needed and unlock/call `log_credit_card_closure_reason_4521` using exactly `credit_card_account_id`, `user_id`, and one permitted `closure_reason` value:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
4. Address the stated concern. For `annual_fee`:
   - For a customer of at least two years, offer a one-year fee waiver as a loyalty benefit. Apply it only if the customer accepts: unlock/call `apply_credit_card_account_flag_6147` with `credit_card_account_id`, `user_id`, `flag_type: "annual_fee_waived"`, `expiration_date` exactly one year from today in `MM/DD/YYYY`, and `reason: "loyalty_benefit"`.
   - For a customer of less than two years, offer a permanent downgrade to the matching no-annual-fee product. Confirm category and consent first, then use `downgrade_credit_card_3847` with target `Bronze Rewards Card` for a personal card or `Business Bronze Rewards Card` for a business card. Explain that the credit line, account number, history, and point value are preserved but product benefits change.
5. If the customer still wants closure, make one tier-appropriate retention offer: entry tier `500` points or `$5` statement credit; mid tier `2,000` points or `$20`; premium-and-above `5,000` points or `$50`.

If the customer declines, or prior-attempt history requires skipping retention, accept the decision without pressure.

### 5. Close and communicate

After identity is logged, all eligibility conditions currently pass, and the retention workflow is complete or properly skipped, unlock and call `close_credit_card_account_7834` with `credit_card_account_id` and `user_id` only.

Report the tool result. Tell the customer that a confirmation email and final statement arrive within several business days. Also state:

- remaining rewards may be redeemed for 45 days after submitting the closure request, then are forfeited; and
- a full annual-fee refund may apply when closure occurs within 37 days of the fee posting.

Do not promise a refund without confirming its posting date and timing.

## Helper script

`scripts/closure_eligibility.py` reads one JSON object from standard input and emits a JSON assessment to standard output.

### Input schema

```json
{
  "current_date": "YYYY-MM-DD or MM/DD/YYYY",
  "account_open_date": "YYYY-MM-DD or MM/DD/YYYY or null",
  "outstanding_balance": "a dollar string, number, or null",
  "dispute_statuses": ["closed", "open"],
  "replacement_order_statuses": ["delivered", "pending"]
}
```

Use `null` for a fact not yet verified. An empty status array means the corresponding tool reported no records. The output includes `closure_eligible`, `blockers`, `needs_verification`, and the calculated `account_age_days` when dates are valid. Treat any `needs_verification` item as a stop condition.

Example runtime call (with live values substituted by the executor):

```json
{"current_date":"2025-01-01","account_open_date":"2024-10-01","outstanding_balance":"0.00","dispute_statuses":[],"replacement_order_statuses":[]}
```

Validate that `closure_eligible` is `true`, `blockers` is empty, and `needs_verification` is empty before requesting closure. The script does not verify identity, retrieve live data, unlock tools, transfer money, log reasons, or close accounts.
