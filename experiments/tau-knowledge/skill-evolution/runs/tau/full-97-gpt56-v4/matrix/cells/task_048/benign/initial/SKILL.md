---
name: credit-card-closure-with-retention
description: Handle a verified customer's request to close a specific Rho-Bank credit card. Use for closure requests that require identity verification, eligibility checks, a one-time retention workflow, and a final closure or explanation of blocking conditions.
---

# Credit Card Closure With Retention

## Purpose and boundaries

Use this Skill to process one specifically identified credit card account at a time. Do not close other cards merely because the customer mentions having several cards. Identity must be verified before an account-changing action. A closure may proceed only when all eligibility conditions are confirmed and the customer still chooses closure after the applicable retention step.

The executor must use the normal banking tools described below; this Skill does not itself perform any bank action.

## Required information

Obtain or confirm:

- the authenticated customer's `user_id`;
- the exact `credit_card_account_id` and intended card type;
- two matching identity fields out of date of birth, email, phone number, and street address;
- the customer's closure reason, mapped to one of:
  `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

A name alone is not identity verification. If the customer has not supplied two identity fields in the conversation, ask them to confirm two fields without disclosing the values on file. Look up the customer record as necessary and compare the response. Once two fields match, call `get_current_time` and then call `log_verification` with all required record fields and that returned timestamp. If verification fails or the account/card cannot be identified unambiguously, do not continue to closure.

## Tool discovery

Before each first use, unlock these internal tools with `unlock_discoverable_agent_tool`:

- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_closure_reason_history_8293`
- `log_credit_card_closure_reason_4521`
- `close_credit_card_account_7834`

Unlock `apply_credit_card_account_flag_6147` only when an eligible annual-fee waiver is to be applied. Then invoke unlocked tools through `call_discoverable_agent_tool`, encoding exactly the documented arguments as JSON strings.

## Workflow

### 1. Identify the account and verify the customer

1. If needed, use `get_user_information_by_name`, `get_user_information_by_email`, or `get_user_information_by_id` to locate the customer. Use `get_credit_card_accounts_by_user` to identify the requested account.
2. Verify two identity fields and create the `log_verification` audit record as described above.
3. Confirm to the customer which card will be considered. Do not infer that the request covers every card on the profile.

### 2. Confirm closure eligibility before retention

Check all of the following for the selected account. Do not make a retention offer or log a closure reason if any condition fails.

1. **Disputes:** call `get_user_dispute_history_7291` with `{"user_id":"<user_id>"}`. Treat any dispute that is active, open, pending, or under review as a blocker. If status terminology or results are ambiguous, do not close; explain that all disputes must be fully resolved first.
2. **Replacement cards:** call `get_pending_replacement_orders_5765` with `{"credit_card_account_id":"<account_id>"}`. An empty order collection passes. If any order is not clearly `delivered` or `cancelled`, closure is blocked until it is delivered or cancelled.
3. **Account age:** compare the account opening date with the current date. The account must be at least 60 calendar days old.
4. **Balance:** the selected account's outstanding/current balance must be exactly `$0.00`.

If blocked, clearly state the applicable condition(s) and what the customer must resolve. Do not call the closure tool and do not pressure the customer with retention. If the balance may include unposted activity, advise the customer to wait for pending transactions to post and pay the full statement balance.

### 3. Determine whether retention is allowed

For an eligible account, call `get_closure_reason_history_8293` with `{"credit_card_account_id":"<account_id>"}`.

- If there is one or more closure-reason record within the past year, skip all retention offers. Tell the customer you will proceed with the closure request, then obtain/confirm that they want closure now and continue to Step 6.
- If no such recent record exists, continue to Step 4.
- If the result is unavailable or ambiguous, do not assume there is no history; resolve the tool issue before offering retention or closing.

### 4. Log the reason and address it

If the customer already gave a clear reason, map it to the permitted enum. Otherwise ask why they want to close the card. Call `log_credit_card_closure_reason_4521` with **only**:

```json
{
  "credit_card_account_id": "<account_id>",
  "user_id": "<user_id>",
  "closure_reason": "<permitted_reason>"
}
```

Address the concern briefly:

- `annual_fee`: for a customer of at least two years, offer a one-year fee waiver. If accepted, call `apply_credit_card_account_flag_6147` with the account ID, user ID, `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from today in `MM/DD/YYYY` format. For less than two years, offer a permanent downgrade to a no-annual-fee card while preserving account history.
- `not_using_card`: remind them of relevant benefits and suggest a recurring subscription if they wish to keep it active.
- `found_better_card`: ask which benefits matter and offer help applying for a comparable Rho-Bank card if one is available.
- `unhappy_with_rewards`: review available bonus-category enrollment and ways to maximize rewards from spending patterns.
- `negative_experience`: apologize, gather details, and escalate to a supervisor where warranted; a modest goodwill credit may be considered for a service complaint.
- `simplifying_finances` or `other`: acknowledge the goal without inventing benefits or applying an unsupported account change.

A fee-waiver acceptance or a requested downgrade changes the immediate outcome: do not close the account unless the customer later makes a fresh, explicit closure request.

### 5. Make exactly one tier-appropriate retention offer

If the account is still eligible, had no recent closure-reason history, and the customer still wants to close after the concern is addressed, make one retention offer based on the current card tier:

- Entry tier: 500 bonus points **or** a $5 statement credit.
- Mid tier: 2,000 bonus points **or** a $20 statement credit.
- Premium and above: 5,000 bonus points **or** a $50 statement credit.

The customer must be allowed to accept or decline. Do not close while awaiting their response. Do not make repeated offers or apply a retention benefit unless a separately available tool and the customer's explicit acceptance support that action.

### 6. Close after a valid decision

Proceed only if the customer explicitly declines the single retention offer, or if retention was correctly skipped due to recent closure-reason history and the customer confirms closure.

Call `close_credit_card_account_7834` with exactly:

```json
{
  "credit_card_account_id": "<account_id>",
  "user_id": "<user_id>"
}
```

If the tool reports failure, do not claim the account is closed. Explain the reported issue and preserve the customer's request for appropriate follow-up.

## Required customer disclosures when closure succeeds

After successful closure, tell the customer:

- They will receive a confirmation email and final statement within several business days.
- Remaining rewards can be redeemed for 45 days after the closure request; any unredeemed rewards are permanently forfeited after that period.
- If an annual fee posted within the preceding 37 days, they may be eligible for a full refund; otherwise no refund applies.
- Closing a card can affect credit utilization, total available credit, and potentially their credit score.

If a displayed reward balance is stored as points on a cash-back card, explain it as cash back at `$0.01` per point when redeemed as a statement credit or checking-account credit. Calculate the displayed dollar equivalent only from the account data currently retrieved; never assume or invent a reward balance.

## Conversation completion rules

- Clearly distinguish an eligibility block, a pending customer response to an offer, a retention acceptance, and a successful closure.
- Never represent a card as closed until `close_credit_card_account_7834` reports success.
- Do not disclose account information or perform actions for an unverified person.
- If the customer asks to close another card, repeat this workflow independently for that account, including its own eligibility and closure-reason-history check.

## Example execution outline

For a verified, identified account with a stated reason: retrieve accounts → check disputes and replacement orders → verify account age and zero balance → check closure-reason history → log the permitted reason if retention is allowed → address the reason → make one correctly tiered offer → wait for an explicit decline → call the closure tool → provide post-closure disclosures.
