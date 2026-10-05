---
name: credit-card-account-closure
version: 1.0.0
description: Safely process a verified customer's request to close a credit-card account, including mandatory closure eligibility checks, retention controls, reward communication, and use of the prescribed account tools. Use when a customer asks to close a specific credit card.
---

# Credit Card Account Closure

Use this Skill for a customer-requested credit-card closure. It prevents a closure or retention attempt until the required identity and account eligibility controls are complete.

## Required runtime information

Obtain at runtime:

- The authenticated customer's `user_id` and the requested `credit_card_account_id`.
- The target account's owner, card type, opening date, current balance, and reward-points balance.
- System-confirmed pending-dispute and pending-replacement-card status for the **target account**.
- The current date/time for identity-verification logging, age calculation, and any date-based offer.
- Whether a closure-reason record exists for this account within the past year.
- The customer's closure reason and, if applicable, their response to a retention offer.

Never select an account merely because another account owned by the customer has a similar card type or a balance. Confirm that the requested account belongs to the verified customer.

## Tool access

The specialized credit-card tools are discoverable. Before each first use, unlock the named tool with `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool` with a JSON-string `arguments` value. Do not claim a tool action succeeded unless its result confirms success.

Tools prescribed by this workflow:

- `get_closure_reason_history_8293`
- `log_credit_card_closure_reason_4521`
- `apply_credit_card_account_flag_6147`
- `close_credit_card_account_7834`

Use only the documented arguments below. Other account-status lookup mechanisms may be used only when available in the runtime; do not invent a tool name or arguments.

## Procedure

### 1. Verify identity and select the target account

1. Locate the customer and obtain the account list using the normal read-only banking tools.
2. Ask the customer to confirm at least two of these profile fields: date of birth, email, phone number, and address. Compare the supplied values with the profile; do not treat a name alone as sufficient verification.
3. After two fields match, call `get_current_time` and create the audit record with `log_verification`. Its required arguments are all of: `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`.
4. Identify the requested account by its actual account ID and verify its `user_id` matches the authenticated customer. If identity cannot be verified, ownership does not match, or the requested card is ambiguous, do not continue to account actions.

### 2. Confirm closure eligibility before retention

All of the following must be confirmed for the target account before any retention discussion or tool call that changes the account:

1. **Outstanding balance:** the current balance must be exactly `$0.00`. A positive, negative, malformed, or unavailable balance is not approval. If any outstanding balance remains, tell the customer they must pay it off before closure and stop; do not make retention offers or close the account.
2. **Pending disputes:** there must be no active or pending transaction dispute. If one exists, explain that it must resolve before closure and stop.
3. **Pending replacement cards:** there must be no replacement card ordered but not received or activated. If one exists, explain that closure cannot proceed until it is resolved and stop.
4. **Account age:** the account must have been open at least 60 days. If not, tell the customer the earliest eligible date if it can be calculated, and stop.

A customer's assertion about disputes or replacement cards is useful context but is not system confirmation. If a required status cannot be verified from available account records, do not proceed to retention or closure; explain that the status must be confirmed first.

For a normalized, deterministic eligibility calculation, run:

```text
python scripts/evaluate_closure.py < normalized_closure_input.json
```

The script only evaluates supplied facts; it does not access banking systems or perform a closure. See [Eligibility helper I/O](#eligibility-helper-io).

### 3. Apply the retention-attempt control

Only after eligibility succeeds, unlock and call `get_closure_reason_history_8293` with exactly:

```json
{"credit_card_account_id":"<target account id>"}
```

If records exist within the past year, skip all retention activity. Tell the customer you will proceed with the closure request, then go to Step 6 once they confirm they still want closure. Do not log another reason, make an offer, or apply a waiver in this branch.

If no such record exists, continue to Step 4.

### 4. Log and address the reason

Ask for the closure reason if it is not already clear. Normalize it to exactly one permitted value:

- `annual_fee`
- `not_using_card`
- `found_better_card`
- `unhappy_with_rewards`
- `simplifying_finances`
- `negative_experience`
- `other`

Unlock and call `log_credit_card_closure_reason_4521` with **only** these arguments:

```json
{
  "credit_card_account_id":"<target account id>",
  "user_id":"<verified user id>",
  "closure_reason":"<one permitted value>"
}
```

Address the stated concern without pressure:

- Annual fee: for a customer of at least two years, offer a one-year fee waiver. If accepted, call `apply_credit_card_account_flag_6147` with `credit_card_account_id`, `user_id`, `flag_type` of `annual_fee_waived`, an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`, and `reason` of `loyalty_benefit`. For less than two years, offer a permanent downgrade to a no-annual-fee card while preserving account history; use a separate downgrade process only if one is provided by the runtime.
- Not using card: remind the customer of relevant benefits and suggest a recurring subscription if they want to keep it active.
- Found better card: ask which features attracted them and offer help applying for a comparable Rho-Bank product only when a supported option is known.
- Unhappy with rewards: check available bonus-category enrollment and discuss ways to maximize rewards based on spending.
- Negative experience: apologize, gather details, and escalate to a supervisor when warranted. Consider a modest goodwill credit only if a supported policy/tool authorizes it.
- Simplifying finances or other: acknowledge the reason and ask whether there is a non-pressuring alternative that would help.

### 5. Make one retention offer if the customer still wants closure

When the customer remains eligible, has no prior closure-reason record in the last year, and still wants to close after Step 4, make one offer based on verified product-tier metadata:

- Entry tier: 500 bonus points or a $5 statement credit.
- Mid tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Do not infer a tier from a marketing name if the tier is not established by available product data. If the runtime cannot establish the tier or cannot fulfill an offer through an authorized mechanism, state that limitation rather than fabricating an offer or account adjustment. If the customer declines the offer, do not pressure them.

### 6. Close after the customer confirms the decision

When all prerequisites are satisfied and the customer confirms they want to proceed, unlock and call `close_credit_card_account_7834` with exactly:

```json
{
  "credit_card_account_id":"<target account id>",
  "user_id":"<verified user id>"
}
```

If the closure tool errors or does not positively confirm completion, report that the closure was not confirmed and do not represent the account as closed. Follow available error handling or transfer procedures if needed.

After confirmed closure, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; after that, they are forfeited.
- If an annual fee posted recently, a full refund may apply if closure occurs within 37 days of the fee charge.

Credit-card reward balances may be stored as points even for cash-back cards. For the listed cash-back products, 1 point represents `$0.01` when redeemed as a statement credit or checking-account credit. The EcoCard's sustainability points also redeem at `$0.01` per point. State the reward balance and potential value accurately, but do not redeem rewards or promise a refund unless the customer asks and an authorized process supports it.

## Eligibility helper I/O

`scripts/evaluate_closure.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "account": {
    "account_id": "string",
    "user_id": "string",
    "date_of_account_open": "MM/DD/YYYY or YYYY-MM-DD",
    "current_balance": "currency string, number, or decimal string",
    "reward_points": "optional integer or numeric string"
  },
  "now": "current date/time containing YYYY-MM-DD or MM/DD/YYYY",
  "expected_user_id": "optional verified user ID",
  "pending_disputes": "true, false, or null when unverified",
  "pending_replacement_cards": "true, false, or null when unverified",
  "closure_request_date": "optional date/time; include only after a closure request is submitted"
}
```

Output schema:

```json
{
  "ok": true,
  "account_id": "string or null",
  "age_days": "integer or null",
  "earliest_eligible_date": "YYYY-MM-DD or null",
  "balance": "two-decimal string or null",
  "reward_points": "integer or null",
  "reward_credit_value": "two-decimal dollar string or null",
  "closure_eligible": "boolean",
  "blockers": ["machine-readable blocker"],
  "unknowns": ["unverified required field"],
  "rewards_redemption_deadline": "YYYY-MM-DD or null"
}
```

Treat `closure_eligible: true` only as confirmation of the supplied eligibility facts. It does not verify identity, check previous retention attempts, record a reason, obtain customer consent, or execute any banking action. A nonempty `blockers` or `unknowns` list means do not progress to retention or closure.
