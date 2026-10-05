---
name: credit-card-account-closure
version: 1.0.0
description: Safely process or defer a credit-card account closure request. Use when a verified customer asks to close a specific card and the executor must verify closure blockers, follow the required retention sequence, invoke approved closure tools, and provide required post-closure disclosures.
---

# Credit Card Account Closure

## Scope and required conditions

Use this Skill only for a request to close a credit-card account. A closure may proceed only after all of the following have been confirmed for the selected account:

- identity has been verified through the standard process;
- outstanding balance is exactly `$0.00`;
- there are no active or pending transaction disputes;
- the account has been open for at least 60 calendar days; and
- there is no replacement-card order that remains pending, shipped, or otherwise not clearly delivered or cancelled.

A customer statement alone does not replace an available account or order check. If a required fact cannot be reliably established, treat closure as incomplete and explain the required follow-up; do not submit a closure.

## Inputs

Obtain at runtime, rather than embedding them in this Skill:

- authenticated/identified customer name or email, and the resulting `user_id`;
- the intended card's `credit_card_account_id`, card type/category, opening date, balance, and rewards balance;
- two customer-confirmed identity fields out of date of birth, email, phone number, and address;
- current timestamp for the verification audit record;
- dispute status from an authoritative source or an explicit, sufficient case status;
- pending replacement-order results;
- prior closure-reason history, if eligibility is satisfied;
- the customer's reason, decision after any retention discussion, and card tier when an offer is required.

The supplied task observations are runtime evidence. Do not hardcode user IDs, account IDs, balances, dates, names, or an assumed eligibility result into scripts or instructions.

## Procedure

1. **Identify the customer and account.** Use the available user lookup and credit-card account lookup. Match the requested card type/category to exactly one account owned by the customer. If multiple accounts match, ask the customer to identify the account; if none match, do not act on another account.
2. **Verify identity.** Ask the customer to confirm any two of the four identity fields (date of birth, email, phone number, address), compare them with the user record, get the current time, and call `log_verification` only after both match. Pass all required user-record fields and the obtained timestamp to that tool. A name, an account lookup, or a prior clarification by itself is not a two-field verification.
3. **Check closure eligibility before retention.** Confirm dispute status, calculate whether the account age is at least 60 days, and verify the current balance is zero. Unlock and call `get_pending_replacement_orders_5765` with only `credit_card_account_id`; an empty `orders` collection passes, while any order not clearly `delivered` or `cancelled` blocks closure. Use `scripts/evaluate_closure_eligibility.py` to make the deterministic age, balance, and replacement-status decision from the collected facts.
4. **Stop on any blocker.** Clearly state each verified blocker and what must happen first (for example, pay the full balance after pending transactions post, resolve disputes, wait until day 60, or complete/cancel a replacement). Do not make a retention offer, log a closure reason, or call a closure tool while any eligibility condition fails. Do not claim closure was submitted.
5. **Check retention-attempt history only after eligibility passes.** Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id`. If a record exists within the preceding year, skip all retention offers and move to closure once the customer still wishes to proceed.
6. **Log and address the reason if there is no prior attempt.** Obtain or clarify one accurate allowed reason and unlock/call `log_credit_card_closure_reason_4521` with exactly `credit_card_account_id`, `user_id`, and one of: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`. Do not add arguments. Address the concern according to policy. For annual-fee concerns, a customer of at least two years may receive the one-year loyalty waiver only by calling `apply_credit_card_account_flag_6147` with `flag_type: annual_fee_waived`, `reason: loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`; for less than two years, offer the applicable same-category no-annual-fee downgrade if the customer wants it.
7. **Make one tier-based retention offer when required.** If the customer still wants to close, make one offer: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium and above: 5,000 points or $50 statement credit. Do not guess a tier that is not present in authoritative account information. If it cannot be determined, obtain the needed classification through the approved workflow before offering. If the customer declines, do not pressure them.
8. **Close only after all preceding applicable steps.** Unlock and call `close_credit_card_account_7834` with `credit_card_account_id` and `user_id` only. Report success only from the tool response.
9. **When closure succeeds, communicate post-closure terms.** State that a confirmation email and final statement will arrive within several business days. Remaining rewards may be redeemed for 45 days after the closure request, then are forfeited. A full annual-fee refund is available only if closure occurs within 37 days of the fee posting. For cards whose stored points represent cash back, explain that points redeem at $0.01 each; this does not change the 45-day deadline.

## Failure handling

- If identity cannot be verified, do not disclose account details or perform account actions.
- If lookup data, dispute status, or replacement-order results are missing, ambiguous, malformed, or access is denied, do not close; request/perform the approved follow-up or escalate through the normal support path.
- If a specialized tool fails after an action may have been submitted, do not retry blindly or assert an outcome. Preserve the error context and use the normal technical escalation path.
- A request to close is not itself permission to apply a downgrade, annual-fee waiver, credit, or retention benefit. Obtain the customer's affirmative decision before such an alternative action.

## Eligibility helper

`scripts/evaluate_closure_eligibility.py` receives JSON on stdin and emits JSON on stdout. It performs no banking action.

Input schema:

```json
{
  "account_open_date": "YYYY-MM-DD",
  "as_of_date": "YYYY-MM-DD",
  "current_balance": "0.00",
  "has_pending_disputes": false,
  "replacement_orders": [{"status": "delivered"}]
}
```

`has_pending_disputes` may be `true`, `false`, or `null` when unavailable. `replacement_orders` may be `null` when the replacement check was unavailable. The script returns `eligible`, `blockers`, `checks`, and `age_days`. A null or invalid required input produces `eligible: false` and an explicit indeterminate blocker rather than treating the condition as passed.

Example executor call after gathering live facts:

```text
run_skill_script(
  relative_path="scripts/evaluate_closure_eligibility.py",
  input_json={...live eligibility facts...}
)
```

Validate that `eligible` is true and `blockers` is empty before starting history/retention or calling the closure tool. The helper's output is a decision aid; the executor must still ensure identity verification and use the required banking tools for any account action.
