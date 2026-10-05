---
name: credit-card-closure-retention
version: 1.0.0
description: Safely authenticate a credit-card customer, determine whether a selected card is eligible for closure, complete the required retention sequence, and close the account only after all prerequisites and the customer's final decision permit it. Use for requests to close a Rho-Bank credit card account.
---

# Credit Card Closure and Retention

## Scope and required capabilities

Use this Skill when a customer asks to close a credit card. It covers identity verification, account selection, eligibility checks, replacement-order and dispute checks, retention-history abuse prevention, reason logging, retention handling, and closure communication.

The execution agent must use normal banking tools for all account actions. The packaged script is only a deterministic evaluator; it does not query systems, authenticate a customer, log verification, grant an offer, or close an account.

Never invent an account ID, a customer identifier, a tool result, a card tier, a closure reason, an offer acceptance, or a successful closure. Do not expose profile data merely to help the customer pass verification.

## Required policy facts

A requested account may be closed only when all of these are confirmed:

1. The customer has been identity-verified.
2. The selected account balance is exactly `$0.00`.
3. The selected account has no active or pending dispute.
4. The account has been open for at least 60 days.
5. There is no replacement-card order in a non-final state. Only `delivered` and `cancelled` are final for this check.
6. The retention protocol has been completed or correctly bypassed because of a closure-reason record within the last year.
7. The customer still requests closure after any required retention conversation.

A failed, missing, ambiguous, stale, or inaccessible prerequisite is not permission to close. Explain the blocking issue, request the needed information where appropriate, or escalate a technical access problem.

## Interaction workflow

### 1. Identify the person, authenticate them, and select the card

1. Locate the customer using information they supplied, then retrieve their credit-card accounts with `get_credit_card_accounts_by_user`.
2. Match the requested product to one account. If several accounts could match, ask the customer to identify the intended account without revealing unneeded sensitive data. Do not proceed based only on a product name where that is ambiguous.
3. Verify **two of these four** fields by comparing values the customer supplies against the profile: date of birth, email, phone number, and street address. A name lookup, account ID, or a value read from the profile does not itself count as one of the two customer-provided factors.
4. If the customer provided only one valid factor, request one additional factor from the remaining choices. Do not process closure, make retention offers, or disclose account details until two factors match.
5. After two factors match, obtain the current timestamp with `get_current_time` and call `log_verification` with the verified profile's required complete fields: `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`.
6. If a supplied factor does not match, do not reveal the expected value. Ask for another permitted factor or handle the security issue under normal procedures.

### 2. Collect and evaluate closure eligibility

After verification and account selection, collect current data for the selected card:

- Inspect the account's current balance and opening date from the account lookup. Re-query if the data is stale or unclear.
- Unlock and call `get_user_dispute_history_7291` with exactly `{"user_id":"<authenticated-user-id>"}`. Review status and transaction/card context for disputes associated with the selected account. An `open`, `pending`, `under_review`, or other non-final dispute blocks closure. A dispute record that cannot be confidently associated or disassociated from the selected account must be resolved before claiming the selected account has no pending disputes.
- Unlock and call `get_pending_replacement_orders_5765` with exactly `{"credit_card_account_id":"<selected-account-id>"}`. An empty collection passes. If any returned order is not clearly `delivered` or `cancelled`, closure is blocked.
- Use `scripts/closure_precheck.py` to evaluate the date, exact-zero balance, dispute statuses, and order statuses consistently when the results can be represented in its input schema. Treat an `unknown` script result as not cleared.

If a condition fails, explain only the necessary remediation and do not make retention offers or call the closure tool. Examples: pay the balance to exactly zero, wait for the account to reach 60 days, wait for dispute resolution, or wait for replacement delivery/cancellation.

### 3. Check retention history before offering retention

Unlock `get_closure_reason_history_8293` and call it with exactly:

```json
{"credit_card_account_id":"<selected-account-id>"}
```

Determine whether this **specific account** has a closure-reason record dated within the preceding year, using the current time when timestamps require comparison.

- If a record exists within that period, do not make a retention offer. Thank the customer and proceed to the final closure confirmation/checks if they still want closure.
- If no qualifying record exists, continue with the reason and retention steps below.
- If history cannot be obtained or its time range is ambiguous, do not assume that no prior attempt exists. Retry if appropriate; otherwise use the normal technical-error escalation path rather than bypassing the abuse-prevention check.

### 4. Log and address the reason

Ask why the customer wants to close if they have not already stated a reason. When their statement maps to one of the allowed values, unlock and call `log_credit_card_closure_reason_4521` using **only** these arguments:

```json
{
  "credit_card_account_id":"<selected-account-id>",
  "user_id":"<authenticated-user-id>",
  "closure_reason":"<annual_fee|not_using_card|found_better_card|unhappy_with_rewards|simplifying_finances|negative_experience|other>"
}
```

Map the customer's actual statement faithfully. If it cannot be mapped, use `other`; do not fabricate a more favorable category. Confirm the log succeeded before continuing.

Address the stated concern:

- **Annual fee:** A customer known to have at least two years of customer tenure may be offered a one-year annual-fee waiver. The tenure requirement is customer tenure, not merely card age. If tenure cannot be confirmed, do not assert waiver eligibility. For a customer with less than two years' tenure, offer a permanent downgrade to the applicable no-annual-fee card instead.
  - For an accepted, eligible waiver, unlock `apply_credit_card_account_flag_6147` and use `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one calendar year from the current date in `MM/DD/YYYY` format.
  - For an accepted downgrade, explain that account history, account number, and credit line are preserved while benefits and rewards rates change. Unlock `downgrade_credit_card_3847` and select `Bronze Rewards Card` for a personal card or `Business Bronze Rewards Card` for a business card. Confirm the target card and the customer's consent before calling it.
- **Not using the card:** Explain relevant benefits and suggest a recurring subscription only as a suggestion, not as a required action.
- **Found a better card:** Ask which features matter to the customer. Offer help comparing/applying only if an actual supported Rho-Bank alternative is known; do not make unsupported product claims.
- **Unhappy with rewards:** Check available bonus-category enrollment if a supported capability exists and discuss substantiated ways to maximize rewards.
- **Negative experience:** Apologize, gather details, and use normal escalation procedures when warranted. Do not invent a goodwill-credit tool or promise a credit.

No public capability is supplied to apply general bonus-points or statement-credit retention awards. Do not represent such an award as applied unless a supported, authorized execution capability is available.

### 5. Make one applicable retention offer

If there is no recent closure-reason record and the customer still wants to close after the concern is addressed, make one offer based on the card's documented tier:

- Entry tier: 500 bonus points or a $5 statement credit.
- Mid tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Use a documented tier classification; do not infer a tier from a card name alone when it is not established. If the tier is unavailable, seek the supported product source or explain that the retention offer cannot yet be determined. Wait for the customer's decision. If they accept a supported alternative or offer, do not close the account. If they decline, clearly reaffirm their request to close and continue without pressure.

### 6. Final check and close

Immediately before initiating closure, re-run `get_pending_replacement_orders_5765` for the selected account because a new replacement order blocks closure. Reconfirm any other prerequisite whose data may have changed, especially balance and disputes. Do not close if a non-final replacement order now exists.

Unlock `close_credit_card_account_7834` and call it only after all requirements above are passed, with exactly:

```json
{
  "credit_card_account_id":"<selected-account-id>",
  "user_id":"<authenticated-user-id>"
}
```

If the tool reports an error or an ineligible state, do not claim closure succeeded. Explain the reported blocker or escalate a technical system error through the normal process.

On confirmed success, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; afterward they are forfeited.
- If an annual fee posted within 37 days of closure, a full refund may be available.
- For cash-back cards, rewards stored as points represent cash back at `$0.01` per point when redeemed as a statement credit or checking-account credit. Apply this only to a known eligible product; do not calculate or disclose a reward balance unless authorized and verified.

Closing a credit card can reduce available credit and affect credit utilization, potentially affecting the customer's credit score. Mention this if useful to the customer's decision, without using it to pressure them.

## Tool and failure handling

Unlock each discoverable tool before calling it. Keep arguments exact, especially for `log_credit_card_closure_reason_4521`, which accepts only its three documented arguments.

If a required tool is unavailable, returns malformed data, or fails after an appropriate retry, do not substitute a guess. Preserve the customer's request, explain that the required check or processing step could not be completed, and use the normal transfer path with `technical_system_error` when a human must complete it. Use `account_closure_request` if transferring an otherwise valid unresolved closure request to a human queue.

## Deterministic precheck helper

`scripts/closure_precheck.py` receives one JSON object on standard input and emits one JSON object on standard output. It has no external dependencies and does not retain inputs.

Input schema:

```json
{
  "current_time": "current timestamp or date",
  "date_of_account_open": "account opening date",
  "current_balance": "balance string or JSON number",
  "disputes": [{"status": "status string"}],
  "replacement_orders": [{"status": "status string"}]
}
```

`disputes` and `replacement_orders` may be empty arrays when a completed lookup returned no records. Use `null` when the corresponding lookup was unavailable or ambiguous. Accepted dates include `MM/DD/YYYY`, `YYYY-MM-DD`, and timestamps beginning with `YYYY-MM-DD`.

Output fields are `account_age_days`, per-check states (`pass`, `block`, or `unknown`), and `eligible` (`true`, `false`, or `null`). `eligible: true` is only a computational summary; the execution agent must still complete verification, retention, final recheck, and the closure tool call.

A runnable invocation is `python3 scripts/closure_precheck.py`, with a JSON object matching the schema sent on stdin. Before relying on output, validate that the selected account's opening date, current balance, dispute records, and replacement orders—not a different account's data—were supplied.
