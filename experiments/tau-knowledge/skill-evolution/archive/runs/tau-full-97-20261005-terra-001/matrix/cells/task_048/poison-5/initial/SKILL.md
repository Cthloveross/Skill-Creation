---
name: credit-card-account-closure
version: 1.0.0
description: Safely handle a verified customer's request to close one specific Rho-Bank credit-card account, including eligibility checks, prior-retention-abuse checks, standardized reason logging, retention handling, and authorized closure.
---

# Credit Card Account Closure

Use this Skill when a customer asks to close a credit card. Process one selected account at a time. Do not close other cards merely because the customer mentioned multiple cards.

## Required runtime data and tools

At runtime, obtain the authenticated user's profile, the selected account's current account data, and the current time. The execution agent must use the normal banking tools; this package does not perform banking actions.

Unlock and call these discoverable tools when their relevant step is reached:

- `get_user_dispute_history_7291(user_id)`
- `get_pending_replacement_orders_5765(credit_card_account_id)`
- `get_closure_reason_history_8293(credit_card_account_id)`
- `log_credit_card_closure_reason_4521(credit_card_account_id, user_id, closure_reason)`
- `close_credit_card_account_7834(credit_card_account_id, user_id)`

Only when applicable and accepted by the customer, also unlock:

- `apply_credit_card_account_flag_6147(credit_card_account_id, user_id, flag_type, expiration_date, reason)` for a qualifying annual-fee waiver.
- `downgrade_credit_card_3847(credit_card_account_id, user_id, target_card_type)` for an accepted no-annual-fee downgrade.

Never add undocumented arguments to any of these tools. In particular, closure-reason logging accepts exactly its three listed arguments.

## Workflow

### 1. Verify identity and identify the account

1. Locate the customer only from information supplied by the customer. If the customer supplies a name or email, use the matching user lookup and ensure there is a single unambiguous profile.
2. Identity is not verified by a name alone. Ask the customer to confirm at least two of these four profile fields: date of birth, email, phone number, and address. Do not disclose profile values in a way that lets an unverified person answer them.
3. After two fields match, obtain the current timestamp with `get_current_time` and call `log_verification`. Populate every field required by that tool from the matched profile and timestamp.
4. Retrieve the user's card accounts and identify the one the customer chose. If card type is ambiguous, ask which account they mean; do not select based on balance, rewards, or account age alone. Confirm the account belongs to the verified user.

If verification, ownership, or account selection cannot be established, do not access account-specific closure processing or perform closure.

### 2. Confirm closure eligibility before retention

Use the current selected-account record and the two required account-specific checks below. Treat unavailable, malformed, incomplete, or ambiguous responses as unknown rather than passing.

Check all four requirements:

1. **Disputes:** Call `get_user_dispute_history_7291` using the verified `user_id`. The selected account cannot be closed if it has an active or pending transaction dispute. Carefully associate any returned dispute with the selected account/card where the response provides enough context; if association or status is ambiguous, stop and resolve it. A dispute must be fully resolved before closure.
2. **Replacement cards:** Call `get_pending_replacement_orders_5765` using the selected `credit_card_account_id`. An empty orders collection passes. If any order is not clearly `delivered` or `cancelled` (for example, `pending` or `shipped`), closure is blocked.
3. **Account age:** The account must have been open for at least 60 calendar days as of the current date.
4. **Balance:** The current outstanding balance must be exactly $0.00.

If any requirement fails, explain the specific blocker and what the customer must resolve. Do not make retention offers, log a closure reason, or call the closure tool. Do not treat lack of transaction history as evidence that there are no disputes.

The helper can consistently evaluate structured eligibility data, but it does not retrieve data or replace the required banking-tool calls:

```text
python3 scripts/closure_checks.py < runtime_closure_input.json
```

`runtime_closure_input.json` must be a runtime-created JSON object with this schema:

```json
{
  "as_of": "current timestamp or date",
  "account": {
    "current_balance": "currency amount",
    "date_of_account_open": "MM/DD/YYYY or ISO date"
  },
  "disputes": [{"status": "status from dispute tool"}],
  "replacement_orders": [{"status": "status from replacement-order tool"}]
}
```

The script emits a JSON object with a per-check `pass`/`fail`/`unknown` result, `closure_eligible`, the account age in days when determinable, and a one-year anniversary date for a possible annual-fee waiver. Explicit empty arrays mean no returned disputes/orders; omitted or non-array fields mean unknown and do not pass eligibility.

### 3. Check prior retention attempts

Only after all eligibility requirements pass, call `get_closure_reason_history_8293` with the selected account ID.

- If it reports any closure-reason record for that account within the past year, do not make a retention offer. Tell the customer that the request will proceed, then go to Step 6 after refreshing the immediately-pre-closure eligibility check.
- If no such record exists, continue to Step 4.
- If dates or the result are insufficient to determine whether a record is within the past year, do not assume there is no prior attempt. Resolve the ambiguity before offering retention.

### 4. Normalize and log the reason

If the customer has not already stated a reason, ask for one. Map the customer's answer to exactly one permitted value:

- `annual_fee`
- `not_using_card`
- `found_better_card`
- `unhappy_with_rewards`
- `simplifying_finances`
- `negative_experience`
- `other`

Confirm an unclear mapping with the customer. Then call `log_credit_card_closure_reason_4521` with the selected account ID, verified user ID, and the normalized reason. Do not add notes, tier, or free-form text to this tool call.

### 5. Address the concern and make one retention offer

Address the stated concern without pressure:

- **Annual fee:** A customer known to have at least two years' tenure may be offered a one-year annual-fee waiver. Apply it only after acceptance, with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one calendar year from the current date in `MM/DD/YYYY`. Do not equate account-open date with customer tenure unless runtime records explicitly establish that equivalence. If the customer is known to have less than two years' tenure, offer a permanent same-category no-annual-fee downgrade instead: `Bronze Rewards Card` for personal cards or `Business Bronze Rewards Card` for business cards. Explain that account history, account number, credit line, and reward value are preserved, while benefits and reward rates change.
- **Not using card:** Remind the customer of relevant benefits and suggest a recurring subscription if appropriate.
- **Found better card:** Ask which features matter and offer help applying for an available comparable Rho-Bank card if applicable.
- **Unhappy with rewards:** Discuss bonus-category enrollment and reward-maximization options based on available spending context.
- **Negative experience:** Apologize, gather details, and escalate to a supervisor when warranted. Do not invent a goodwill-credit tool.
- **Simplifying finances** or **other:** Acknowledge the preference and continue respectfully.

If the customer still wants closure, make one tier-based offer:

- Entry tier: 500 bonus points or a $5 statement credit.
- Mid tier: 2,000 bonus points or a $20 statement credit.
- Premium or above: 5,000 bonus points or a $50 statement credit.

Use the account's actual card tier. Green Rewards Card is mid-tier. If no documented tool exists to grant an accepted points or statement-credit offer, do not fabricate one or claim it was applied. Record or route the accepted offer only through an available approved runtime process; do not close unless the customer subsequently reaffirms that they want closure.

If the customer accepts an applicable waiver or downgrade instead of closure, carry out only that accepted action and confirm the result. Do not close the account.

### 6. Close only after an explicit final decision

If the customer declines the retention offer, or prior retention history required retention to be skipped, thank them and proceed without pressure.

Immediately before closure, refresh the replacement-order check. Also re-check balance and disputes if any time has passed or the account state could have changed. If a refreshed check blocks or is unknown, do not close.

Then call `close_credit_card_account_7834` with exactly:

- `credit_card_account_id`: the selected, eligible account ID
- `user_id`: the verified authenticated user's ID

Do not call the closure tool before verification, eligibility, required history handling, and the customer's final decision. On a tool error or an ambiguous result, do not state that the account is closed; retry or use approved support escalation procedures.

### 7. Required post-closure communication

After a successful closure result, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; remaining rewards are forfeited after that period.
- If an annual fee posted recently, a full refund may apply only when closure occurs within 37 days of that fee charge. Do not promise a refund without confirming the fee date.
- If useful to the customer's decision, explain that closing a card can affect credit utilization and credit history, potentially affecting their credit score.

If the customer wants to close another card, begin the workflow again for that separate account.
