---
name: credit-card-closure-with-paydown
version: 1.0.0
description: Safely handles an authenticated customer's request to pay a credit-card balance from a Rho-Bank checking account and close the card. Use for credit-card closure requests, including retention workflow, closure eligibility, and checking-funded payoff.
---

# Credit Card Closure With Checking-Funded Payoff

Use this Skill when a customer requests closure of a credit card, including when a remaining balance must first be paid from a Rho-Bank checking account. It is a banking workflow: do not take an action based only on a customer-supplied account identifier or an unverified assertion.

## Controls that apply before every banking action

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow specifically:

1. Verify the customer by confirming at least **two of four** profile fields: date of birth, email, phone number, and address.
2. Obtain the authoritative profile using the appropriate user lookup, and call `log_verification` only after the two fields are confirmed. Include the returned current timestamp and the complete requested profile values.
3. Confirm the authenticated user's ownership of every selected checking and credit-card account by comparing account `user_id` values.
4. Treat a customer statement that they do not know of a dispute as insufficient evidence. Check dispute status through the documented dispute-history tool.
5. Do not repeat an action that returns an unknown outcome. Re-query status, preserve the result, and escalate if the outcome cannot be established.

## Tool invocation convention

The specialized tools named below are agent-discoverable. Before their first use in a session, call `unlock_discoverable_agent_tool` with the exact tool name, then invoke it with `call_discoverable_agent_tool` and an arguments JSON object containing only documented fields. If a named tool is already directly available in the runtime, use that normal banking tool with the same fields. Never claim that a recommended action ran unless its tool result confirms it.

## End-to-end workflow

### 1. Establish customer, authority, and requested card

1. Verify identity and log the verification record as described above.
2. Look up all of the authenticated user's credit-card accounts with `get_credit_card_accounts_by_user`.
3. Identify the requested card by authoritative card type and/or a customer-confirmed account identifier. If more than one card could match, ask the customer to choose; do not close another card.
4. Record the card account ID, account owner, account-opening date, current balance, rewards balance, and card tier if authoritatively available.

### 2. Check closure eligibility before retention or closure

All four conditions must be satisfied before a retention offer or account closure can proceed:

- outstanding balance is exactly `$0.00`;
- no active or pending dispute exists for the account;
- the account has been open at least 60 calendar days;
- no pending replacement card order exists.

Perform and preserve these checks:

1. Determine age from the account opening date and current time. Exactly 60 days is eligible.
2. Unlock and call `get_user_dispute_history_7291` with `{"user_id": "..."}`. Review all returned records applicable to the selected card where enough card/transaction context is present. Any status such as `open`, `pending`, or `under_review` blocks closure. If a dispute cannot be confidently associated or ruled out for the selected account, do not assume eligibility; resolve or escalate.
3. Balance must come from the account lookup or a fresh post-payment lookup, not a prior customer statement.
4. Immediately before any final closure invocation, unlock and call `get_pending_replacement_orders_5765` with `{"credit_card_account_id": "..."}`. An empty order collection passes. Any order that is not clearly `delivered` or `cancelled` blocks closure. Re-run this check after delays or intervening work and immediately before closure.

If any condition fails, explain the specific blocker and do not make retention offers or close the card. For a balance, offer the payoff path below if the customer wants it.

### 3. Pay a balance from a checking account when requested

Use this only after the customer explicitly authorizes the payment and identifies (or selects after being shown) a source checking account.

1. Retrieve bank accounts using `get_all_user_accounts_by_user_id_3847` with the authenticated user's ID. Consider only an owned, active Rho-Bank checking account.
2. If the customer has not provided a checking-account ID, present the eligible checking choices needed to select a source. Ask for the source selection and confirm the exact payment amount. A general request to pay from checking does not select among multiple accounts.
3. Reconfirm that the selected checking balance is at least the positive payment amount and that the credit-card balance is at least that amount. For a full payoff, use the freshly observed card balance; do not exceed either balance.
4. Obtain explicit authorization to debit that selected account for the stated dollar amount. Preserve the selected source, destination card, amount, ownership checks, available balances, and authorization.
5. Unlock `pay_credit_card_from_checking_9182`, then call it with exactly:
   ```json
   {
     "user_id": "<authenticated user id>",
     "checking_account_id": "<selected owned checking account id>",
     "credit_card_account_id": "<selected owned card account id>",
     "amount": 0.0
   }
   ```
   Replace `0.0` with the authorized positive dollar amount.
6. Read the confirmation, including both new balances. Re-query the credit-card account before proceeding. If its balance is not exactly zero, stop and tell the customer that closure remains unavailable.

### 4. Retention protocol after eligibility is established

1. Unlock and call `get_closure_reason_history_8293` with the selected card ID. Determine whether a closure-reason record exists within the past year.
2. If such a record exists, skip all retention offers and proceed directly to the final closure decision in Step 5.
3. Otherwise, obtain the customer's reason if it is not already clear. Log one primary reason using `log_credit_card_closure_reason_4521` with exactly `credit_card_account_id`, `user_id`, and one of:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, `other`.
4. Address the stated concern without pressure:
   - **annual_fee:** for a customer of at least two years, offer a one-year annual-fee waiver. If accepted, unlock `apply_credit_card_account_flag_6147` and use `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`. For shorter tenure, offer a permanent no-annual-fee downgrade that preserves history if such a supported process is available.
   - **not_using_card:** remind the customer of applicable benefits and suggest a recurring subscription if they want to retain it.
   - **found_better_card:** ask which features matter and offer help applying for an available comparable Rho-Bank card if supported.
   - **unhappy_with_rewards:** review available bonus-category enrollment and reward-maximization options.
   - **negative_experience:** apologize, gather details, and escalate to a supervisor if warranted; do not invent or apply a goodwill credit without a supported authorization path.
5. If the customer still wants to close, make one tier-based retention offer: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20; premium and above: 5,000 points or $50. Determine tier from an authoritative product record. If tier cannot be established, do not guess an offer; explain that the required tier cannot be confirmed and use an approved escalation path.
6. If the customer declines, or the prior-attempt rule required offers to be skipped, accept the decision without pressure.

### 5. Final closure

Immediately before closing, revalidate account ownership, zero balance, dispute status, account age, and replacement-order status. Then unlock and invoke `close_credit_card_account_7834` with exactly:

```json
{
  "credit_card_account_id": "<selected owned card account id>",
  "user_id": "<authenticated user id>"
}
```

Only communicate completion after a successful tool response. Tell the customer that a confirmation email and final statement will arrive within several business days, unredeemed rewards may be redeemed for 45 days after the closure request and are then forfeited, and an annual fee may receive a full refund if closure occurs within 37 days after that fee posted.

## Failure handling

- **Identity, authority, ownership, or card selection cannot be established:** do not act; request the missing verification or clarification.
- **Balance, dispute, age, or replacement blocker:** state the blocker and the required resolution; do not offer retention or close.
- **No sufficiently funded checking account or no selected checking account:** do not attempt a payment; request a selection or another funding method.
- **Tool error or ambiguous response:** do not infer success. Re-query read-only status where safe; otherwise escalate through the approved human-transfer process.
- **Customer wants a human:** transfer with the appropriate available closure-related reason and a concise summary of completed checks and actions.

## Optional deterministic eligibility helper

`scripts/closure_eligibility.py` evaluates supplied, already-authoritative facts. It does not contact bank systems and cannot authorize, pay, retain, or close an account.

Run it by sending one JSON object on stdin, for example:

```json
{
  "as_of": "2025-01-01T00:00:00-05:00",
  "date_opened": "2024-10-01",
  "current_balance": "0.00",
  "disputes": [{"status": "closed"}],
  "replacement_orders": [{"status": "delivered"}]
}
```

It writes JSON containing `eligible`, `account_age_days`, `blockers`, and individual condition booleans. Validate that `eligible` is true and every listed condition is true before considering closure; runtime tool checks, authentication, ownership, retention, authorization, and the immediate pre-closure replacement check remain mandatory.
