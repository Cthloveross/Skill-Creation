---
name: credit-card-account-closure
version: 1.0.0
description: Process a verified customer's credit-card closure request safely, including eligibility checks, retention-history controls, reason logging, retention handling, closure, and required customer communications.
---

# Credit Card Account Closure

Use this Skill when a customer asks to close a Rho-Bank credit card. Process one explicitly identified account at a time. Do not interpret a request to close several cards as permission to close every account; confirm the target account for each closure.

## Required prerequisites

1. **Identify and verify the customer.** Locate the customer and target card account. Confirm at least two of date of birth, address, email, and phone number against the profile. After two fields match, call `log_verification` with *all* required profile fields and the timestamp from `get_current_time`. Do not expose profile values merely to solicit confirmation.
2. **Use only the authenticated customer's account.** The account's `user_id` must match the verified user.
3. **Resolve account ambiguity.** If multiple cards have the same or unclear description, ask the customer to identify which one to close before proceeding.

## Discoverable tools to unlock when needed

Unlock each tool before its first call with `unlock_discoverable_agent_tool`:

- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_closure_reason_history_8293`
- `log_credit_card_closure_reason_4521`
- `apply_credit_card_account_flag_6147` (only for the documented long-tenure annual-fee waiver)
- `close_credit_card_account_7834`

Call them through `call_discoverable_agent_tool` using exactly the documented argument names. Never add undocumented fields.

## Closure workflow

### 1. Confirm closure eligibility before retention

Obtain current data rather than relying on old statements.

- **Disputes:** call `get_user_dispute_history_7291` with `user_id`. Review status and transaction/card context. A target-account dispute with an active, open, pending, or under-review status blocks closure. If returned data cannot reliably be associated with the target account, treat eligibility as unresolved and do not close until clarified.
- **Replacement cards:** call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty list permits this check. Any order not clearly `delivered` or `cancelled` blocks closure.
- **Account age:** use the account's opening date and current date from `get_current_time`. It must be at least 60 days old.
- **Balance:** use the current account balance. It must be exactly $0.00. Pending transactions must be allowed to post and any resulting balance paid before closure.

Run the replacement-order check immediately before initiating closure. If any criterion fails, explain the specific blocker and required remedy, and do **not** make retention offers, log a closure reason, or call the closure tool.

For repeatable date/reward calculations, the executor may run:

```bash
python3 scripts/evaluate_closure.py <<'JSON'
{"current_time":"YYYY-MM-DD HH:MM:SS TZ","date_opened":"MM/DD/YYYY","balance":"$0.00","disputes":[],"replacement_orders":[],"reward_points":0}
JSON
```

The helper is advisory: its JSON output reports the supplied evidence and eligibility. The executor remains responsible for fresh tool calls and interpreting account-specific dispute context.

### 2. Apply the retention-abuse check

For an eligible account, call `get_closure_reason_history_8293` with only `credit_card_account_id`.

- If any closure-reason record exists within the past year, skip all retention steps and proceed to closure after informing the customer that their request will be processed.
- If no qualifying record exists, continue below.

### 3. Record and address the reason

If the customer has not provided a reason, ask for one. Map their response to exactly one accepted value:

`annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

Call `log_credit_card_closure_reason_4521` with exactly:

```json
{"credit_card_account_id":"...","user_id":"...","closure_reason":"one_allowed_value"}
```

Address the concern respectfully:

- `annual_fee`: for a customer of 2+ years, offer a one-year annual-fee waiver. If accepted, call `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from today in `MM/DD/YYYY`. For less than 2 years, offer a permanent no-annual-fee downgrade that preserves account history; do not claim to perform a downgrade unless a supported tool/process is available.
- `not_using_card`: remind them of relevant benefits and suggest a recurring subscription if they wish to retain the card.
- `found_better_card`: ask what features matter and offer help applying for a comparable Rho-Bank card only if one is actually available.
- `unhappy_with_rewards`: review applicable enrollment/options; do not invent an enrollment status or reward offer.
- `negative_experience`: apologize, gather details, and escalate when warranted. Do not promise an unsupported goodwill credit.

If the customer continues to request closure, make one appropriate retention offer based on the account's documented tier: entry $5/500 points, mid $20/2,000 points, premium+ $50/5,000 points. Establish tier from a reliable account source; do not infer a tier solely from a card name. If tier cannot be determined, obtain authoritative guidance rather than fabricate an offer.

If the customer declines the offer, do not pressure them. If they accept a retention outcome, do not close the account unless they subsequently make a new closure request.

### 4. Close the account

Once eligible and the retention path permits closure, call `close_credit_card_account_7834` with exactly:

```json
{"credit_card_account_id":"...","user_id":"..."}
```

Do not retry if the result is ambiguous or unknown. Explain any reported failure and resolve or escalate safely instead. A successful close is the only point at which the account should be described as closed.

## Customer communication after a successful closure

Tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Remaining rewards may be redeemed for 45 days after the closure request, then are forfeited.
- A full annual-fee refund applies only if closure is within 37 days of the annual-fee posting; state this conditionally unless the posting date has been verified.
- Closing a card can reduce available credit and affect utilization/credit score.

For cash-back cards, including Green Rewards Card, stored reward points are cash back at **1 point = $0.01**. Use the helper's `reward_cash_value` or calculate points × 0.01 and present a properly rounded dollar amount. EcoCard sustainability points also redeem at $0.01 per point.

Never state that rewards were redeemed, an annual fee was refunded, a downgrade occurred, or an offer was applied unless the relevant supported action has actually succeeded.

## Failure handling

- Missing verification information: request another verification field; do not close or disclose account details beyond what is necessary.
- No matching account: ask for a valid account identifier or identifying card details.
- Eligibility blocker or ambiguous tool response: explain the blocker/ambiguity and stop the closure path.
- User requests a human agent: transfer with the applicable supported reason, such as `account_closure_request`, and summarize completed checks without revealing unnecessary data.
