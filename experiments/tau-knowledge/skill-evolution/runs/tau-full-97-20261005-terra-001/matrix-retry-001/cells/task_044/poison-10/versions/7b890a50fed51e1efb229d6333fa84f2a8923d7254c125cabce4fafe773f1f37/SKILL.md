---
name: credit-card-account-closure
version: 1.0.0
description: Safely handles a verified customer's request to close a credit-card account, including eligibility checks, required retention steps, discoverable banking-tool calls, and closure communications. Use for credit-card closure requests; do not use it for a downgrade unless the customer elects that alternative.
---

# Credit Card Account Closure

## Scope and prerequisites

Use this Skill only after identifying the requested account and its owner. The executor must use the normal banking tools; scripts in this package only evaluate supplied data and never execute banking actions.

Closure requires all of the following:

- successful standard identity verification, defined in this runtime as matching at least two of date of birth, email, phone number, and address, followed by `log_verification`;
- a $0.00 outstanding balance;
- no active or pending dispute on the target account;
- account age of at least 60 days;
- no pending replacement card order. An order is non-blocking only when every returned order is delivered or cancelled.

Never close an account while a required check is missing, ambiguous, or failed. Explain the specific blocker and stop or obtain the missing information. Do not substitute a customer assertion for a system eligibility result.

## End-to-end procedure

1. **Identify the customer and exact account.** If needed, locate the user with the supplied name or email, then call `get_credit_card_accounts_by_user` using the confirmed `user_id`. Confirm that the selected account is the requested card and belongs to that customer. Do not select among multiple matching accounts without customer confirmation.

2. **Verify identity and create the audit record.** Obtain and compare at least two of the four permitted identity fields against the customer profile. After two fields match, call `get_current_time`, then call `log_verification` with every required field from the profile (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`) and the returned timestamp. Do not disclose unprovided profile data merely to help the customer guess it.

3. **Perform eligibility checks before closure or further retention processing.**
   - Read balance and opening date from the selected account. Calculate the age against the current date; it must be at least 60 days.
   - Call `get_user_dispute_history_7291` with `user_id`. Review each dispute's status and transaction/card context. An open, under-review, pending, or otherwise non-final dispute associated with the requested account blocks closure. If an active dispute cannot be reliably associated or ruled out, treat this as unresolved rather than closing.
   - Unlock `get_pending_replacement_orders_5765`, then call it with only `credit_card_account_id`. Any order not clearly `delivered` or `cancelled` blocks closure.
   - The transaction-history tool is not a substitute for the balance, dispute, or replacement-order checks.

4. **Run the retention protocol for an eligible account.**
   - Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id`. If there is a closure-reason record within the previous year, skip all retention offers and proceed to closure once the customer confirms the decision.
   - Otherwise, ask for or confirm the reason, map it to exactly one permitted value, and unlock/call `log_credit_card_closure_reason_4521` using only `credit_card_account_id`, `user_id`, and `closure_reason`. Valid values are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.
   - Address the concern without pressure. For an annual-fee concern, a customer of at least two years may be offered a one-year annual-fee waiver; if they accept, unlock `apply_credit_card_account_flag_6147` and use `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an expiration date exactly one year from the current date in `MM/DD/YYYY` format. For less than two years, offer—not automatically process—a same-category no-annual-fee downgrade. Use `downgrade_credit_card_3847` only after the customer explicitly chooses it, with target `Bronze Rewards Card` for personal or `Business Bronze Rewards Card` for business accounts.
   - If the customer still wants closure, make no more than one tier-based retention offer: entry tier, 500 points or $5 statement credit; mid tier, 2,000 points or $20 statement credit; premium or above, 5,000 points or $50 statement credit. Do not apply an offer the customer declined. If accepted, do not close unless the customer later makes a new, clear closure decision.

5. **Close only when permitted.** Once identity, all eligibility checks, and the applicable retention path are complete and the customer declines the offer or retention was skipped for prior history, unlock `close_credit_card_account_7834` and call it with `credit_card_account_id` and `user_id`. Do not add unlisted arguments. Report the actual result; do not claim closure based merely on submitting a tool call.

6. **Provide required post-closure communication.** On a successful closure, state that a confirmation email and final statement will arrive within several business days. Tell the customer that unredeemed rewards may be redeemed for 45 days after the closure request and are forfeited afterward. If relevant, explain that a full annual-fee refund may apply when closure occurs within 37 days of that fee posting. Stored points for Gold Rewards Card and other listed cash-back cards represent cash back at $0.01 per point when redeemed as a statement or checking credit; calculate a displayed dollar equivalent only from the actual retrieved point balance.

## Discoverable-tool discipline

Unlock each specialized tool before calling it. Use the exact name and argument list documented above. Tool failures, malformed results, unavailable permissions, and ambiguous replacement/dispute data are not evidence of eligibility. Retry only when appropriate; otherwise preserve the request state and use the runtime's applicable support/escalation procedure rather than performing the closure.

## Optional deterministic evaluator

Use `scripts/closure_plan.py` to validate facts already collected and determine the next workflow stage. It accepts JSON on stdin and emits JSON on stdout. It does not read profiles or call tools.

### Input schema

```json
{
  "now": "YYYY-MM-DD or timestamp",
  "account": {
    "account_id": "string",
    "opened_on": "YYYY-MM-DD or MM/DD/YYYY",
    "current_balance": "$0.00 or numeric",
    "card_tier": "entry|mid|premium"
  },
  "identity_matched_fields": ["date_of_birth", "phone_number"],
  "disputes": [{"status": "closed", "target_account": true}],
  "replacement_orders": [{"status": "delivered"}],
  "prior_closure_history": false,
  "closure_reason": "found_better_card",
  "reason_logged": true,
  "retention_state": "declined"
}
```

`disputes`, `replacement_orders`, and `prior_closure_history` may be omitted when not yet obtained. `retention_state` is one of `not_offered`, `declined`, or `accepted`. Dispute records without `target_account: true` are ignored only when the executor has independently established that they belong to another account; mark ambiguous target-account linkage with `target_account: null`.

### Output and validation

The output contains `next_stage`, `blockers`, `checks`, and (where the card tier is known) `retention_offer`. A result with `next_stage: "ready_to_close"` and an empty `blockers` is the minimum data validation for calling the closure tool; the executor must additionally ensure it actually logged identity verification and completed the required live tool calls. `blocked` results must not be used to close the account.

Example runnable call:

```sh
printf '%s' '{"now":"2025-01-01","account":{"account_id":"example","opened_on":"2024-01-01","current_balance":"0.00","card_tier":"premium"},"identity_matched_fields":["date_of_birth","email"],"disputes":[],"replacement_orders":[],"prior_closure_history":true,"retention_state":"not_offered"}' | python3 scripts/closure_plan.py
```
