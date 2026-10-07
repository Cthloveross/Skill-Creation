---
name: credit-card-closure-and-retention
version: 1.0.0
description: Handle a verified customer's request to close a specific credit-card account, including mandatory eligibility checks, closure-reason history, tailored retention, and safe final closure. Use for credit-card closure requests where the banking-tool environment is available.
---

# Credit Card Closure and Retention

## Purpose and boundaries

Use this Skill to conduct the required customer conversation and invoke the normal banking tools in the required order. It does not itself perform bank actions. Do not close an account, make a retention offer, or state that eligibility is satisfied based only on the customer's recollection; obtain the required system checks.

Treat the requested card as distinct from every other card held by the customer. Never infer an account ID from a card name when multiple accounts could match.

## Required information

Before a closure can be processed, establish all of the following for the *specific* account:

- authenticated customer identity;
- account ID and matching user ID;
- balance of exactly $0.00;
- no active or pending dispute;
- account open for at least 60 days as of the current date;
- no replacement order in a non-final state (for example pending or shipped);
- whether this account has a closure-reason record within the past year.

The retention protocol applies only after closure eligibility is confirmed. If an eligibility condition fails, explain the blocker and do not give a retention offer or invoke closure.

## Workflow

### 1. Identify the customer and authenticate

1. Obtain a customer identifier (name, email, or user ID) and query the corresponding user lookup tool. If the lookup is ambiguous, ask for a more specific identifier; do not select a customer arbitrarily.
2. Ask the customer to confirm two of the four identity fields: date of birth, email, phone number, and billing address. Compare the customer-provided values to the retrieved profile. A field displayed by the system is not, by itself, customer confirmation.
3. Once two fields match, get the current timestamp with `get_current_time` and call `log_verification` with **all** of the profile values required by that tool: `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`.
4. If two fields cannot be confirmed, do not disclose further account-specific details or perform account actions. Ask for another verification field or transfer if the issue cannot be resolved.

### 2. Locate the requested account

1. Call `get_credit_card_accounts_by_user` with the authenticated `user_id`.
2. Match the customer's requested card to one returned account. If no match or more than one plausible match exists, ask a clarifying question. Confirm the selected account ID and do not act on other accounts.
3. Record the account open date and balance from the returned account record. Use the current date to calculate the account age. The helper `scripts/evaluate_closure_eligibility.py` can make this date/balance calculation deterministic after the tool results have been interpreted.

### 3. Check closure eligibility

Perform each check before retention or closure:

1. **Balance and age:** Require balance `$0.00` and an open date at least 60 days before the current date.
2. **Disputes:** Unlock `get_user_dispute_history_7291`, then call it with `user_id`. Treat any dispute whose status is active, open, pending, or under review as blocking. If the returned dispute identifies cards/transactions, assess whether it pertains to the requested account; when the response cannot establish that, treat the result as unresolved and do not close until clarified.
3. **Replacement orders:** Unlock `get_pending_replacement_orders_5765`, then call it with `credit_card_account_id`. An empty collection passes. Any order that is not clearly `delivered` or `cancelled` blocks closure. If the response is empty, malformed, or ambiguous, retry once; if still ambiguous, do not proceed and escalate/transfer as appropriate.

If a check fails, clearly name the needed resolution (pay the balance, wait until the account is 60 days old, resolve the dispute, or complete/cancel the replacement order). Do not promise closure or proceed with retention.

### 4. Check prior retention activity

After all eligibility conditions pass, unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`.

- If there is any closure-reason record within the prior year, skip all retention offers. Tell the customer that you will proceed with the closure request, then follow Step 7 if they are still requesting closure.
- If there is no such record, continue with reason logging and retention.
- If dates or the tool response do not permit determining whether a record is within one year, do not guess. Obtain clarification or escalate rather than making an offer that may violate the prior-attempt rule.

### 5. Obtain and log the closure reason

Ask why the customer wants to close the account unless they already gave a clear reason. Map the response to exactly one allowed value:

- fee concern → `annual_fee`
- not using the card → `not_using_card`
- better outside card/product → `found_better_card`
- dissatisfaction with rewards → `unhappy_with_rewards`
- consolidation/simplification → `simplifying_finances`
- poor service/problem → `negative_experience`
- no suitable category → `other`

Unlock `log_credit_card_closure_reason_4521`, then call it with exactly `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add parameters. If the customer already described a competing card, that can supply `found_better_card`; do not force them to repeat themselves.

### 6. Address the concern and make one retention offer

Address the stated reason before the offer:

- For `found_better_card`, ask what features attract them if unknown. Compare only against actual, known Rho-Bank offerings. Do not invent product benefits. If a comparable option is genuinely known and supported by available tools/policy, offer to help with it instead of closing.
- For `annual_fee`, a customer with at least two years' tenure may be offered a one-year annual-fee waiver. Unlock `apply_credit_card_account_flag_6147` and call it only if the customer accepts, with `flag_type: annual_fee_waived`, `reason: loyalty_benefit`, and an `expiration_date` exactly one year from today in `MM/DD/YYYY` format. For tenure below two years, offer the documented permanent no-annual-fee downgrade; do not claim it was completed unless a supported tool completes it.
- For `not_using_card`, remind the customer of relevant benefits and suggest an appropriate recurring subscription.
- For `unhappy_with_rewards`, discuss available bonus-category enrollment and appropriate spending-based maximization only when supported by actual account/product information.
- For `negative_experience`, apologize, gather details, and escalate to a supervisor when warranted. Do not promise a goodwill credit without a supported process.

If the customer still wants closure, make **one** tier-based retention offer:

- entry tier: 500 bonus points or $5 statement credit;
- mid tier: 2,000 bonus points or $20 statement credit;
- premium or above: 5,000 bonus points or $50 statement credit.

Use a card tier only when it is provided by a reliable account/product source. A card name alone is not a documented tier mapping. If tier cannot be determined from available data, do not fabricate an offer; seek the applicable product information or escalate. Do not close until the customer explicitly declines the applicable offer or again clearly confirms they want to proceed after it.

### 7. Close only after the decision permits it

When the customer declines the offer, reconfirms closure after retention, or has a qualifying closure-reason record in the previous year, unlock `close_credit_card_account_7834` and invoke it with `credit_card_account_id` and `user_id`.

If closure succeeds, tell the customer:

- a confirmation email and final statement will arrive within several business days;
- unredeemed rewards may be redeemed for 45 days after the closure request, after which they are forfeited;
- a full annual-fee refund may apply if closure occurs within 37 days of the fee posting;
- closing a card can affect credit utilization, available credit, and potentially the credit score.

If the tool reports an error or an unknown outcome, do not repeat the closure action. Explain that completion could not be confirmed and escalate/transfer using the available human-transfer process.

## Tool-use rules

Discoverable tools must be unlocked before being called. Use only the arguments documented for each tool. In particular, the reason logger accepts only three arguments, while verification logging requires every listed profile field.

Suggested tool sequence for an ordinary eligible first-time request:

1. user lookup → account lookup → current time → `log_verification` (after two confirmations);
2. dispute-history check and replacement-order check;
3. closure-reason-history check;
4. closure-reason logger;
5. tailored discussion and one applicable offer;
6. after an explicit decline/confirmation, closure tool.

A customer assertion that they do not know of a dispute, replacement order, or previous attempt is not a substitute for the relevant system tool.

## Optional deterministic helper

`scripts/evaluate_closure_eligibility.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs only deterministic balance/age/replacement/dispute evaluation; the executor remains responsible for interpreting live tool outputs and carrying out tool calls.

Input schema:

```json
{
  "current_date": "YYYY-MM-DD",
  "date_opened": "MM/DD/YYYY or YYYY-MM-DD",
  "current_balance": "$0.00 or numeric string",
  "dispute_statuses": ["closed"],
  "replacement_statuses": ["delivered", "cancelled"]
}
```

Example invocation in a shell-capable runtime:

```sh
printf '%s' '{"current_date":"2025-01-01","date_opened":"2024-01-01","current_balance":"0.00","dispute_statuses":[],"replacement_statuses":[]}' | python3 scripts/evaluate_closure_eligibility.py
```

Validate the returned `eligible` field is true only when every `checks` value is true. Missing or malformed required input returns `eligible: false` and an `errors` list; it must be treated as a blocker, not as a pass.
