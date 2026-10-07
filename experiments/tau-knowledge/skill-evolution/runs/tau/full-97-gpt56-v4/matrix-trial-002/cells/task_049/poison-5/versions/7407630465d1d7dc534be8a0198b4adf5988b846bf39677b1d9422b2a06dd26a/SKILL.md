---
name: credit-card-closure-with-retention
version: 1.0.0
description: Process one authenticated customer's request to close a Rho-Bank credit card. Use when identity must be verified, closure eligibility must be checked, the required retention workflow may apply, and an eligible account may be closed with the authorized banking tools.
---

# Credit Card Closure With Retention

Use this Skill to handle **one specifically identified credit-card account at a time**. A request to close multiple cards does not authorize closing every card: begin with the card the customer selected and obtain a distinct request for each additional account.

## Inputs and assumptions

At runtime, obtain from the conversation and banking tools:

- the authenticated customer's `user_id`;
- the selected `credit_card_account_id` (confirm the card type if the customer has more than one account);
- current time and complete customer profile for verification logging;
- fresh account details, dispute history, replacement-order status, and closure-reason history.

Never use identifiers, balances, dates, or rewards from a prior interaction as if they were current. The current account record and the targeted account ID must belong to the verified user.

## Tool access

The following named internal tools are discoverable. Before first use, unlock the exact named tool, then invoke it through the discoverable-agent-tool caller with only the documented arguments:

- `get_user_dispute_history_7291` — `{ "user_id": "..." }`
- `get_pending_replacement_orders_5765` — `{ "credit_card_account_id": "..." }`
- `get_closure_reason_history_8293` — `{ "credit_card_account_id": "..." }`
- `log_credit_card_closure_reason_4521` — `{ "credit_card_account_id": "...", "user_id": "...", "closure_reason": "..." }`
- `apply_credit_card_account_flag_6147` — only for the documented long-tenure annual-fee waiver, with all five documented arguments
- `close_credit_card_account_7834` — `{ "credit_card_account_id": "...", "user_id": "..." }`

Do not add undocumented arguments. Do not repeat a mutating tool call (`log_credit_card_closure_reason_4521`, `apply_credit_card_account_flag_6147`, or `close_credit_card_account_7834`) if its result is ambiguous; first establish whether the action succeeded.

## End-to-end workflow

### 1. Identify and verify the requester

1. Locate the customer and retrieve their profile and credit-card accounts with the ordinary banking lookup tools.
2. Confirm that the selected account is owned by that user. If the card name is ambiguous, ask which account they mean; never select one by guesswork.
3. Obtain confirmation of at least **two of the four** profile fields: date of birth, email, phone number, and address. Compare each confirmation against the retrieved profile. A name, account number, or a lookup result alone is not a confirmation.
4. After two fields match, call `get_current_time`, then call `log_verification` once using the complete retrieved profile (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`) and the returned `time_verified` timestamp.
5. If two fields cannot be confirmed or do not match, do not disclose account-specific details, make offers, or close the account. Ask for another verification field or use the applicable support path.

### 2. Refresh and check closure eligibility

Immediately before deciding whether to close, retrieve the user's current card accounts again and locate the selected account. Confirm all four requirements:

1. **Balance:** `current_balance` is exactly `$0.00`.
2. **Disputes:** unlock and call `get_user_dispute_history_7291` for the verified user. Review any active or pending dispute records and their transaction/card context. The selected account cannot close while it has an open, pending, or under-review dispute. Treat a dispute with unclear account linkage or an unclear non-final status as unresolved rather than assuming it is safe.
3. **Account age:** calculate the calendar-day difference between `date_of_account_open` and current time; it must be at least 60 days.
4. **Replacement cards:** immediately before closure, unlock and call `get_pending_replacement_orders_5765` for the selected account. An empty order collection is clear. If orders are returned, only `delivered` or `cancelled` are final; any other or unknown status blocks closure.

The optional helper can make the mechanical age, balance, and status assessment from normalized data. It does not replace fresh tool calls or account-to-dispute matching:

```text
python3 scripts/evaluate_closure_eligibility.py <<'JSON'
{
  "as_of": "current timestamp or date",
  "account_open_date": "account opening date",
  "current_balance": "0.00",
  "dispute_statuses": ["closed"],
  "replacement_order_statuses": []
}
JSON
```

If a check is missing, malformed, ambiguous, or fails, do **not** call the closure tool. Explain the specific blocker without inventing a resolution. For a remaining balance, ask the customer to pay it and wait for transactions to post. For disputes, wait for resolution. For an active replacement, wait for delivery or cancellation. For age, state that the account must reach 60 days.

A customer's statement that a replacement arrived does not override a fresh order result that is still `pending`, `shipped`, or otherwise non-final. Recheck the order once; if it remains non-final, explain that the recorded status must become `delivered` or `cancelled` before closure. Do not invent a delivery update or use the closure tool to resolve the conflict.

### 3. Apply the required retention path only after eligibility

Once all eligibility conditions are satisfied, unlock and call `get_closure_reason_history_8293` for this account.

- **A closure-reason record within the past year:** skip all retention offers and proceed to the customer's closure decision. Do not log another retention reason merely to repeat the process.
- **No such record:** obtain the reason if it has not already been provided, map it to exactly one accepted value, and call `log_credit_card_closure_reason_4521` with no extra parameters. Accepted values are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.

Then address the stated concern and make **one** authorized retention offer based on the card tier:

- entry tier: 500 bonus points or a $5 statement credit;
- mid tier: 2,000 bonus points or a $20 statement credit;
- premium or above: 5,000 bonus points or a $50 statement credit.

For `simplifying_finances`, acknowledge the consolidation goal before making that single offer. Do not pressure the customer and do not make multiple offers.

Use the account's applicable product tier to select exactly one offer from this matrix. The retention protocol requires that one offer after a newly logged reason and eligibility confirmation: absence of a displayed tier label does not by itself permit skipping the offer. Do not make an extra offer, change the offer in response to negotiation, or apply points/credit without the customer's acceptance and an authorized action.

For annual-fee concerns, the documented annual-fee waiver is available only to a customer of at least two years and requires `apply_credit_card_account_flag_6147` with:

```json
{
  "credit_card_account_id": "selected account",
  "user_id": "verified user",
  "flag_type": "annual_fee_waived",
  "expiration_date": "MM/DD/YYYY exactly one year from today",
  "reason": "loyalty_benefit"
}
```

For shorter tenure, discuss the documented no-annual-fee downgrade alternative, but do not claim to have completed a downgrade without an authorized tool. Do not use the annual-fee waiver tool for other reasons.

### 4. Close only after the customer's final decision

A customer who received a retention offer must explicitly say they still want closure or decline the offer. An existing closure request is sufficient to proceed after the protocol says to skip retention due to prior attempts, provided no material ambiguity remains.

Before calling the closure tool, ensure the replacement-order check was performed immediately before this step and that the fresh account is still eligible. Unlock `close_credit_card_account_7834` and call it with the selected `credit_card_account_id` and verified `user_id`. Report completion only if the tool confirms success. If it fails or is unclear, state that closure was not confirmed and do not claim the account is closed.

### 5. Required customer communication when closure proceeds

After confirmed closure, explain:

- a confirmation email and final statement will arrive within several business days;
- remaining rewards can be redeemed for 45 days after the closure request, then are permanently forfeited;
- a full annual-fee refund is available only when the fee posted within 37 days of closure; do not claim a refund unless current fee-posting facts establish it;
- closing a card can reduce total available credit and affect utilization/credit score;
- if the closed card is a Green Rewards Card, its rewards recorded as points represent cash back at $0.01 per point, and closing it can end its eligible Green Account savings APY bonus (the documented Green Rewards Card bonus is +0.4%).

Do not promise a reward redemption, annual-fee refund, APY outcome, or any action for another account unless an authorized tool and the relevant facts support it.

## Handling failures

- If a lookup returns no matching account, ask for clarification rather than operating on another account.
- If a discoverable tool is unavailable, denied, returns partial data, or returns an ambiguous response, do not close based on assumed eligibility. Explain that the required check could not be completed and use an appropriate support escalation when necessary.
- If the customer requests a human after an unresolved closure issue, transfer with reason `account_closure_request` and a concise summary of verification status, target account, completed checks, and blockers. Do not include unnecessary sensitive values in the summary.

## Helper output validation

`scripts/evaluate_closure_eligibility.py` reads one JSON object from standard input and emits one JSON object to standard output. `eligible: true` means only that the supplied normalized fields meet the mechanical rules; the executor must still confirm ownership, identity, dispute relevance, and tool freshness. `validation_errors` must be empty before relying on the result.

## Helper interface and validation

`scripts/evaluate_closure_eligibility.py` is a local, conservative aid for mechanical checks only. It reads one JSON object from standard input and emits exactly one JSON object on standard output. Its input fields are:

- `as_of` (string): current date/timestamp;
- `account_open_date` (string): account opening date;
- `current_balance` (string or number): current balance, optionally with `$` and commas;
- `dispute_statuses` (array of nonempty strings): statuses only for disputes verified as belonging to the selected account; use `[]` when the dispute query clearly returns none;
- `replacement_order_statuses` (array of nonempty strings): statuses from the selected account's replacement-order query; use `[]` when that query clearly returns none.

It returns `eligible`, `account_age_days`, a per-check `checks` object, and a `blockers` array. An absent, malformed, or unfamiliar non-final status is blocking. `closed` is the recognized final dispute status for this helper; only `delivered` and `cancelled` are final replacement-order statuses. The executor must still make the required live banking-tool calls, assess dispute ownership, and perform a fresh replacement-order check immediately before closing.

Example validation invocation (using only illustrative normalized inputs):

```text
python3 scripts/evaluate_closure_eligibility.py <<'JSON'
{"as_of":"2025-01-01","account_open_date":"2024-01-01","current_balance":"$0.00","dispute_statuses":[],"replacement_order_statuses":[]}
JSON
```

Validate that the output parses as JSON and has `eligible: true`, an account-age check with at least 60 days, and no blockers for that input. Also validate a nonzero balance or `SHIPPED` replacement status produces `eligible: false`. Do not treat the helper output as authorization to transact.
