---
name: credit-card-account-closure
version: 1.0.0
description: Safely handles a customer's request to close a credit card account, including identity verification, eligibility gating, required retention protocol, authorized closure-tool use, and post-closure disclosures. Use for any credit-card closure request.
---

# Credit Card Account Closure

## Scope and safety rules

Use this Skill when a customer asks to close a credit card account. Account closure is permitted only after all required eligibility conditions are confirmed and the customer has been identity-verified.

Never close an account, make a retention offer, log a retention reason, or apply a retention benefit while a known eligibility condition fails. Do not infer account ownership, card tier, customer tenure, dispute status, replacement-card status, annual-fee date, or eligibility from a card name alone.

The required closure conditions are:

1. Outstanding balance is exactly `$0.00`.
2. There are no active or pending transaction disputes.
3. The account has been open at least 60 days.
4. There is no replacement card that has been ordered but not yet received or activated.

A pending transaction should be allowed to post before its balance is evaluated. A credit or negative balance is not the required `$0.00` balance; resolve it through the applicable account process before requesting closure.

## Required workflow

### 1. Identify the customer and the intended account

1. Obtain an email address, full name, or customer ID if the customer has not supplied enough information to locate them.
2. Use the applicable user lookup tool, then retrieve the customer's credit-card accounts using `get_credit_card_accounts_by_user`.
3. Match the account requested by the customer to an account belonging to the authenticated customer. If several accounts could match, ask the customer to identify the intended account. Do not use an account ID belonging to another user.

### 2. Verify identity before account action

Ask the customer to provide and confirm at least **two of these four** profile fields: date of birth, email address, phone number, and address. Compare the customer-provided values against the user profile; a name or account selection alone is not sufficient verification.

After two fields match, obtain the current timestamp with `get_current_time` and call `log_verification`. That tool requires all of the following fields, populated from the matched profile and current time:

- `name`
- `user_id`
- `address`
- `email`
- `phone_number`
- `date_of_birth`
- `time_verified`

If the customer cannot be verified, do not disclose account details, perform retention actions, or close the account.

### 3. Confirm closure eligibility

Check the conditions in this order:

1. Pending or active transaction disputes.
2. Pending replacement card status.
3. Account-open date and age in days.
4. Current outstanding balance.

Use authorized account/dispute/card-status sources available in the runtime. The packaged `scripts/evaluate_closure_eligibility.py` helper can consistently evaluate supplied dates, balance, and boolean statuses; it does not retrieve data and does not take banking actions.

If any condition is failed or cannot be confirmed:

- Do not continue to retention or closure.
- Explain only the applicable remediation: wait for dispute resolution; receive/activate or cancel the replacement process; wait until the 60th day; or wait for pending transactions and pay the full balance to `$0.00`.
- Invite the customer to return after the condition is resolved.

If a required status cannot be retrieved after the customer is verified and no authorized source is available, do not represent the account as eligible. Escalate using the normal human-transfer path when further account-closure processing is required.

### 4. Apply the retention protocol only for an eligible account

After all eligibility conditions pass, unlock and call `get_closure_reason_history_8293` with exactly the target `credit_card_account_id`.

- If there is a closure-reason record for this account within the prior year, skip all retention offers. Tell the customer you will proceed with the closure request.
- If no such record exists, obtain the customer's reason if it is not already clear and log it with `log_credit_card_closure_reason_4521`.

The reason logger accepts **only** these three arguments:

```json
{
  "credit_card_account_id": "<target account id>",
  "user_id": "<verified user id>",
  "closure_reason": "<allowed value>"
}
```

Allowed reason values are: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`. Map the customer's stated reason faithfully; ask a short clarification if no safe mapping is clear. Do not add timestamps, notes, or any other parameter to this tool call.

Address the concern before making one final retention offer:

- **Annual fee:** Determine customer tenure from an authoritative customer-tenure source. With 2 or more years of customer tenure, offer a one-year annual-fee waiver as a loyalty benefit. Apply it only after the customer accepts: unlock `apply_credit_card_account_flag_6147` and call it with `credit_card_account_id`, `user_id`, `flag_type` of `annual_fee_waived`, an `expiration_date` exactly one calendar year from today in `MM/DD/YYYY` format, and `reason` of `loyalty_benefit`. With less than 2 years' tenure, offer a permanent downgrade to a no-annual-fee card while preserving account history, using only an authorized downgrade process if one is available.
- **Not using card:** Mention relevant benefits and suggest a recurring subscription if appropriate.
- **Found a better card:** Ask which features matter and offer help applying for an appropriate available card if one exists.
- **Unhappy with rewards:** Review available bonus-category enrollment and reward-maximization options.
- **Negative experience:** Apologize, gather details, and escalate service complaints when warranted; only offer a goodwill credit if authorized by the applicable process.

If the customer still wants to close, make one offer based on the account's **authoritatively determined** tier:

- Entry tier: 500 bonus points or a $5 statement credit.
- Mid tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Do not guess tier from marketing wording. Obtain an authorized classification before selecting an offer. If the tier cannot be determined, do not invent an offer amount or pressure the customer; honor a continuing request to close.

If the customer declines an offer, or retention was skipped because of a recent prior attempt, thank them and proceed without further pressure.

### 5. Process closure

Only after identity verification, all eligibility checks, and the applicable retention path are complete:

1. Unlock `close_credit_card_account_7834`.
2. Call it with exactly the verified `user_id` and target `credit_card_account_id`.
3. Report the tool result accurately. Do not claim success if the tool fails or returns an error; explain the failure and use an appropriate supported escalation path if needed.

### 6. Required customer communication when closure proceeds

Tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Remaining rewards may be redeemed for 45 days after the closure request. They are permanently forfeited after that period.
- A full annual-fee refund may be available when closure occurs within 37 days after the annual fee posted. Confirm the fee-posting date from an authorized record before stating that the customer qualifies.
- Closing a credit card can reduce total available credit and may affect utilization and credit score, especially for a high-limit or older account.

## Discoverable-tool handling

The closure-reason history, reason logging, annual-fee waiver, and closure tools are specialized internal tools. Unlock each tool with `unlock_discoverable_agent_tool` before calling it through `call_discoverable_agent_tool`. Use the exact tool names and argument sets specified above. A recommendation in this Skill never itself performs a banking action.

## Eligibility helper

Run the helper with a JSON object on standard input and read its JSON result from standard output:

```sh
python scripts/evaluate_closure_eligibility.py < closure_eligibility.json
```

`closure_eligibility.json` must contain:

```json
{
  "current_balance": "string or number representing the outstanding balance",
  "opened_date": "YYYY-MM-DD or MM/DD/YYYY",
  "as_of_date": "YYYY-MM-DD or MM/DD/YYYY",
  "pending_disputes": true,
  "pending_replacement_card": false
}
```

Use `null` for an unavailable status. The result has `status` (`eligible`, `ineligible`, or `needs_information`), `account_age_days` when dates are valid, and structured `blockers`. Closure may proceed only when `status` is `eligible`; still complete identity verification and the retention workflow before calling the closure tool.
