---
name: credit-card-closure-with-retention
version: 1.0.0
description: Safely handle a request to close a credit card account. Use when a verified customer requests closure and the agent must verify identity, determine eligibility, follow the required retention/history workflow, and either close the exact eligible account or clearly explain why closure cannot yet proceed.
---

# Credit Card Closure With Retention

## Scope and safety boundary

Use this Skill for credit-card closure requests only. A closure is an account-changing action. Do not close an account, log a closure reason, make a retention offer, or apply a retention benefit until the prerequisites below have been met in their required order.

Always operate on the account the customer specifically named. A customer may have multiple cards; never use another account's balance, rewards, age, or identifier as a substitute.

## Required workflow

### 1. Identify and verify the customer

1. Obtain enough information to locate the customer and retrieve their credit-card accounts.
2. Confirm that the requested card exists and belongs to that customer.
3. Independently verify the customer's identity by confirming **two of these four fields** against the profile: date of birth, email, phone number, and address.
   - A name, account ID, or a customer statement that they are eligible is not identity verification.
   - Do not disclose nonpublic account details before verification.
4. After two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with all required profile fields, the authenticated user ID, and that timestamp.

If two fields cannot be verified, do not perform or disclose the closure workflow. Ask for the needed verification information or follow the available support/escalation process if verification cannot be completed.

### 2. Check closure eligibility before retention

For the exact requested account, establish all of the following:

- outstanding balance is exactly `$0.00`;
- there are no active or pending transaction disputes;
- the account has been open for at least 60 days; and
- there is no pending replacement card.

Use account records and any supported sources for pending disputes/replacement status. A customer's assertion may be useful context but must not override an available system record. If a required status cannot be established, do not treat it as passed.

You may run the deterministic age/balance check helper after gathering the facts:

```bash
python3 scripts/closure_decision.py <<'JSON'
{"today":"YYYY-MM-DD","date_opened":"YYYY-MM-DD","current_balance":"0.00","pending_disputes":false,"pending_replacement_cards":false}
JSON
```

The script reads one JSON object from standard input and emits one JSON object to standard output. Its input fields are:

- `today`: current local date in `YYYY-MM-DD` format;
- `date_opened`: account open date in `YYYY-MM-DD` format;
- `current_balance`: a nonnegative numeric amount or a currency string such as `$12.34`;
- `pending_disputes`: `true` or `false`;
- `pending_replacement_cards`: `true` or `false`.

The output contains `eligible`, `account_age_days`, normalized `balance`, and a `blockers` list. It only evaluates supplied facts; it does not verify identity, query systems, or authorize any action.

If **any** requirement fails, stop the closure and do not begin retention. Explain the specific blocker(s) and what the customer must resolve. For example, a positive balance must be paid to `$0.00` before closure can proceed. Do not call the closure-reason history, reason logging, retention-benefit, or account-closure tools for an ineligible account.

A rewards balance does not offset a card balance unless a separate supported redemption process explicitly does so.

### 3. Check for prior closure-reason records

Only after eligibility passes:

1. Unlock `get_closure_reason_history_8293` with `unlock_discoverable_agent_tool`.
2. Call it through `call_discoverable_agent_tool` using only the required `credit_card_account_id`.

If the account has closure-reason records within the prior year, skip reason logging and all retention offers. Tell the customer that you will proceed with the closure request, then proceed to Step 6 after confirming the customer still wants closure if that confirmation is needed by the conversation.

If no such records exist, continue to Step 4.

### 4. Capture and log the closure reason

Ask why the customer wishes to close unless the customer has already given an unambiguous reason. Map the reason faithfully to exactly one permitted value:

- `annual_fee`
- `not_using_card`
- `found_better_card`
- `unhappy_with_rewards`
- `simplifying_finances`
- `negative_experience`
- `other`

Unlock `log_credit_card_closure_reason_4521`, then call it with **only** `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add any other parameter.

### 5. Address the concern and make one applicable retention offer

Address the stated concern without pressure:

- **Annual fee:** if customer tenure is at least two years, the one-year annual-fee waiver may be offered as a loyalty benefit. If accepted, unlock and call `apply_credit_card_account_flag_6147` with `credit_card_account_id`, `user_id`, `flag_type` set to `annual_fee_waived`, an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`, and `reason` set to `loyalty_benefit`. For tenure under two years, offer the documented permanent downgrade option instead; do not use the waiver flag.
- **Not using card:** remind the customer of relevant benefits and suggest a recurring subscription if appropriate.
- **Found a better card:** ask what features attracted them and offer help applying for a comparable Rho-Bank card only if one is actually available.
- **Unhappy with rewards:** check available bonus-category enrollment where supported and suggest appropriate reward-maximization options.
- **Negative experience:** apologize, gather details, and escalate to a supervisor when warranted. Do not invent or apply a goodwill credit without a supported process.

If the customer still wants to close, make exactly one retention offer based on the account's confirmed tier:

- entry tier: 500 bonus points or a $5 statement credit;
- mid tier: 2,000 bonus points or a $20 statement credit;
- premium or above: 5,000 bonus points or a $50 statement credit.

Do not infer a tier merely from a color or product name when the tier is not established by an available account/product record. Resolve the tier through supported information before quoting a tier-specific offer. Do not invent a tool or apply points/credits absent a supported tool and customer acceptance.

If the customer accepts an available retention solution, do not close the account. If they decline the offer or continue to request closure, proceed without further pressure.

### 6. Process an eligible, confirmed closure

Once identity is logged, all eligibility criteria pass, the history/retention path is complete, and the customer confirms closure after any applicable offer:

1. Unlock `close_credit_card_account_7834`.
2. Call it using only the exact requested `credit_card_account_id` and authenticated `user_id` required by that tool.
3. Report the actual tool result. Do not claim closure succeeded unless the tool reports success.

After a successful closure request, tell the customer that a confirmation email and final statement will arrive within several business days. Tell them that unredeemed rewards can be redeemed for 45 days after the closure request and are forfeited afterward. If relevant, note that a full annual-fee refund may be available when closure occurs within 37 days of the fee charge.

For documented cash-back cards, backend `points` represent cash back at `$0.01` per point. State a dollar equivalent only when the point total is known and the card is one of the documented cash-back cards; this fact does not itself redeem rewards or pay a balance.

## Response behavior and validation checklist

Before any closure tool call, confirm all of the following are true:

- [ ] The customer passed two-field identity verification and a verification record was logged.
- [ ] The requested account belongs to the authenticated customer.
- [ ] Balance is `$0.00`.
- [ ] No pending dispute and no pending replacement card were established.
- [ ] Account age is at least 60 days.
- [ ] Closure-reason history was checked after eligibility passed.
- [ ] The appropriate history path was followed: either retention was skipped for a recent prior record, or the reason was logged and a single applicable offer was made.
- [ ] The customer has not accepted a retention outcome and still wants closure.
- [ ] The closure call uses the requested account ID and authenticated user ID only.

If a checklist item is false, communicate the next required customer action instead of attempting closure. In particular, when a supplied account record shows a nonzero balance, the correct outcome is to explain that payoff is required; do not use retention or closure tools merely because the customer requested closure.
