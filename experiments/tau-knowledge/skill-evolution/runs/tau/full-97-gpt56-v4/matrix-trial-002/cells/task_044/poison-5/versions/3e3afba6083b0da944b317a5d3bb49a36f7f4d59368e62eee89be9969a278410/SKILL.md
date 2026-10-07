---
name: credit-card-closure-retention
version: 1.0.0
description: Safely handle a verified customer's request to close a Rho-Bank credit card, including closure eligibility, prior-retention screening, reason logging, tailored retention/downgrade handling, and closure disclosures. Use when a customer wants to close a credit card or asks for an alternative instead of closure.
---

# Credit-card Closure and Retention

## Purpose and boundaries

Use this Skill for a credit-card closure request after identity verification. Follow the required sequence exactly: eligibility first, prior-attempt screening second, reason logging and tailored retention only for an eligible customer without a prior attempt, then closure only after the customer confirms that decision.

Do not promise that Rho-Bank has a card feature, reward rate, foreign-transaction-fee policy, approval outcome, or refund beyond information actually available in the task evidence or account/product records. If the customer asks whether Rho-Bank has a comparable product and the available records do not establish that it does, say that you cannot confirm a comparable offering from the information available. Do not misrepresent stored cash-back rewards as a different currency.

## Required runtime inputs

Obtain or derive these values from the live conversation and normal banking tools:

- `user_id` and the authenticated customer's identity fields;
- `credit_card_account_id`, card type/category, date opened, balance, and reward balance;
- present time, for verification logging and date calculations;
- closure eligibility status: active/pending disputes, pending replacement card, account age, and balance;
- closure-reason records during the preceding year;
- the customer's stated closure reason and whether they accept, decline, or are still considering an alternative.

Never use identifiers, account data, or conclusions from an earlier task instance as runtime data.

## Procedure

### 1. Authenticate and create the verification audit record

1. Verify at least two of date of birth, email, phone number, and address against the user record.
2. Obtain the current timestamp with `get_current_time`.
3. After successful verification, call `log_verification` with **all** required fields from the authoritative user record plus `time_verified`. Do not log a record before the two-field check passes.
4. Locate the requested card with `get_credit_card_accounts_by_user` and ensure it belongs to the authenticated user. If the card is ambiguous, ask the customer to identify it.

### 2. Check closure eligibility before any offer

For the selected account, establish all four conditions in this order:

1. no active or pending transaction dispute;
2. no replacement card ordered but not yet received or activated;
3. account open for at least 60 days;
4. outstanding balance exactly $0.00.

Use normal account/dispute/card servicing tools available in the runtime. Transaction history alone is not proof that there are no disputes or no replacement card. If a required status cannot be obtained, do not claim eligibility or make a retention offer; explain that the status must be confirmed before closure can proceed.

If any condition fails, explain the specific blocker and required resolution, and stop the retention/closure flow. In particular, do **not** make a retention offer to an ineligible customer.

The helper `scripts/closure_math.py` can calculate the age criterion and the one-year annual-fee-waiver expiration date; it does not replace live status checks.

### 3. Screen for prior retention attempts

Unlock `get_closure_reason_history_8293` using `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` with only:

```json
{"credit_card_account_id":"<account id>"}
```

Interpret records within the past year as a prior retention attempt. If one exists, do not log a new reason and do not make any retention offer. Tell the customer you will proceed with their closure request, but call the closing tool only once the customer has actually confirmed they want closure.

### 4. Obtain and log the reason

If there is no prior record, ask for the reason if it is not already clear. Map it conservatively to one of the allowed values:

- fee concern → `annual_fee`
- not using card → `not_using_card`
- competitor/better product → `found_better_card`
- dissatisfaction with rewards → `unhappy_with_rewards`
- simplifying accounts → `simplifying_finances`
- service complaint → `negative_experience`
- otherwise → `other`

Unlock and call `log_credit_card_closure_reason_4521` with exactly these three fields and no extras:

```json
{
  "credit_card_account_id":"<account id>",
  "user_id":"<user id>",
  "closure_reason":"<allowed reason>"
}
```

### 5. Address the reason before making a tier offer

Tailor the response:

- **Annual fee:** calculate tenure. At 2+ years, offer a one-year fee waiver. Only after the customer accepts, unlock and call `apply_credit_card_account_flag_6147` with `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an expiration date one year from today in `MM/DD/YYYY`. Under two years, offer a permanent same-category no-annual-fee downgrade instead. The only documented targets are `Bronze Rewards Card` (personal) and `Business Bronze Rewards Card` (business). Explain that history, account number, and credit line are preserved, while benefits change. On acceptance, unlock and call `downgrade_credit_card_3847` with the appropriate documented target.
- **Not using card:** remind the customer of applicable known benefits and suggest a recurring subscription; do not fabricate benefits.
- **Found a better card:** ask which features matter if not already known. Compare only documented product facts. If a known Rho product is actually similar or better, offer help applying for it rather than closing. If the available information cannot establish this, state that limitation plainly and let the customer decide; do not imply an unavailable match.
- **Unhappy with rewards:** check available bonus-category enrollment and discuss documented ways to maximize rewards.
- **Negative experience:** apologize, collect details, and escalate to a supervisor when warranted; consider a modest goodwill credit only when permitted by available servicing policy.

Cash-back cards store rewards as points in the backend. For the documented cash-back cards, 1 point is $0.01 when redeemed as a statement credit or checking-account credit. State both the points and dollar equivalent when relevant, but do not convert or redeem without authorization.

### 6. Make one retention offer only if the customer still wants closure

After addressing the concern, if the customer still wants to close and has no prior attempt, make one offer based on the verified card tier:

- entry tier: 500 bonus points or $5 statement credit;
- mid tier: 2,000 bonus points or $20 statement credit;
- premium and above: 5,000 bonus points or $50 statement credit.

Do not apply a reward/credit merely by offering it, and do not pressure the customer. If tier classification is unavailable, obtain it from authoritative product/account data rather than guessing.

A customer who asks a comparison question or says they are deciding has not yet confirmed closure. Answer the question or state the supported limitation, then ask whether they want to keep the card, pursue the offered alternative, or continue with closure.

### 7. Process a confirmed closure

When an eligible customer declines the retention offer, or was excluded from offers by a prior attempt, and explicitly confirms closure:

1. Unlock `close_credit_card_account_7834`.
2. Call it with the authenticated `credit_card_account_id` and `user_id`.
3. Report the actual tool result; never say the account is closed unless the call succeeds.
4. Explain without pressure that confirmation email and final statement arrive within several business days; rewards remain redeemable for 45 days after the closure request, then are forfeited; and a full annual-fee refund may be available only if closure is within 37 days of the fee posting.

If the customer elects a downgrade, alternative application, or retention offer instead, do not close the account. If they remain undecided, preserve the account and invite a decision.

## Tool-call discipline

- Unlock each named specialized tool before calling it and use `call_discoverable_agent_tool` with a JSON-string `arguments` payload.
- Use only the documented arguments for reason logging; tool calls can have strict schemas.
- Treat a failed, malformed, or unknown tool outcome as not completed. Explain the limitation and avoid repeating a potentially state-changing call until the outcome is known.
- Normal closure action is performed only by `close_credit_card_account_7834`; recommendations or script output do not perform banking actions.

## Deterministic helper

`scripts/closure_math.py` reads one JSON object on stdin and emits one JSON object on stdout.

Input schema:

```json
{
  "opened_on": "MM/DD/YYYY or YYYY-MM-DD",
  "today": "MM/DD/YYYY or YYYY-MM-DD",
  "optional_rewards_points": 8200
}
```

`opened_on` and `today` are required. The output provides whole elapsed days, `meets_60_day_minimum`, a `fee_waiver_expiration_date` exactly one calendar year after `today` (with leap-day handling), and, when points are supplied, the documented `$0.01` per-point statement-credit value. Validate that dates parse and that points are nonnegative. A nonzero exit and JSON error indicate unusable input; obtain corrected live data rather than guessing.

Example runnable invocation in a supported shell:

```sh
printf '%s' '{"opened_on":"2023-03-20","today":"2025-11-14","optional_rewards_points":8200}' | python3 scripts/closure_math.py
```

Review the output only as a calculation aid. Live tools remain authoritative for balance, disputes, replacements, closure history, and account state.
