---
name: credit-card-closure-workflow
description: Safely process a requested Rho-Bank credit-card closure, including identity verification, account-specific eligibility checks, required retention handling, closure, and required customer communications. Use when a customer asks to close one or more credit card accounts.
---

# Credit Card Closure Workflow

Process one specifically identified credit-card account at a time. Do not infer that a request to close several cards authorizes bulk closure: complete this workflow separately for each card the customer confirms.

## Required tools and records

Use the normal banking tools supplied by the runtime. The specialized tools named below must first be unlocked with `unlock_discoverable_agent_tool`, then invoked through `call_discoverable_agent_tool` with an exact JSON argument object.

- `get_user_dispute_history_7291` — query with `user_id`.
- `get_pending_replacement_orders_5765` — query with `credit_card_account_id`.
- `get_closure_reason_history_8293` — query with `credit_card_account_id`.
- `log_credit_card_closure_reason_4521` — query with exactly `credit_card_account_id`, `user_id`, and `closure_reason`.
- `apply_credit_card_account_flag_6147` — only for the supported long-tenure annual-fee waiver path.
- `close_credit_card_account_7834` — query with `credit_card_account_id` and `user_id`.

Never treat unlocking a tool, a customer statement, or a profile lookup as proof that a closure succeeded. Report closure as complete only after the closure tool returns a successful result.

## 1. Identify the customer and verify identity

1. Locate the profile using the customer-provided name or email and obtain the canonical `user_id`.
2. Retrieve the profile by `user_id` if needed to confirm the selected profile.
3. Ask the customer to confirm **two of the four** identity fields: date of birth, email, phone number, and address. Do not read unconfirmed values back merely to solicit a yes/no confirmation. Compare their supplied values to the profile.
4. Obtain the current timestamp with `get_current_time` and call `log_verification` only after two matching fields have been confirmed. Supply the complete required profile fields and timestamp to the logging tool.
5. If two fields do not match, cannot be obtained, or the profile is ambiguous, do not perform account actions. Resolve identity through the supported process or transfer when appropriate.

## 2. Select exactly one target account

Call `get_credit_card_accounts_by_user` and match the customer’s requested card name to one account. Confirm the target with the customer if multiple accounts could match. Record its account ID, opening date, balance, card type, and rewards shown by the account result.

Do not close a different card because it has a similar name, a zero balance, or is another card held by the same user.

## 3. Verify closure eligibility before retention

All of the following must be established for the selected account before any retention activity or closure attempt:

1. **Zero outstanding balance:** account balance is exactly $0.00.
2. **Account age:** the account has been open at least 60 days, calculated against the current date.
3. **No active or pending disputes:** unlock and query `get_user_dispute_history_7291`. Review returned disputes and determine whether any active/pending dispute belongs to the target account. Use transaction/card context where available. A user assertion is useful context but does not replace this system check. If account association cannot be determined reliably, do not close until resolved.
4. **No pending replacement card:** immediately before the closure path, unlock and query `get_pending_replacement_orders_5765` with the target account ID. An empty list passes. If any order is not clearly `delivered` or `cancelled` (for example, pending or shipped), closure is blocked.

Use `scripts/closure_eligibility.py` to make the date, balance, and status assessment reproducible after collecting the relevant facts. It does not replace the required banking calls or account-level dispute review.

If any requirement fails or is unknown, clearly explain the specific blocker and what must be resolved. Do **not** make retention offers, log a closure reason, or call the closure tool for that account. A later request can restart the checks.

## 4. Check prior retention attempts

For an eligible account, unlock and call `get_closure_reason_history_8293` with the account ID. Determine whether there is a record for that specific account within the past year.

- If a qualifying prior record exists, skip reason logging and all retention offers. Tell the customer you will proceed with their closure request, then continue to the immediate replacement-order recheck and closure.
- If none exists, continue with the reason and retention process below.
- If the history response is incomplete or cannot be interpreted, do not bypass this abuse-prevention check; resolve it before making an offer or closing.

## 5. Log reason and conduct the required retention process

Ask for the customer’s primary reason if it has not been provided or if they provide multiple reasons and no primary reason is clear. Normalize only to one allowed value:

`annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

Call `log_credit_card_closure_reason_4521` with exactly its three allowed arguments. Do not add notes, timestamps, tier, or arbitrary fields.

Address the reason before making a retention offer:

- `annual_fee`: for a customer of at least two years, offer a one-year fee waiver. If they accept, apply `annual_fee_waived` using `apply_credit_card_account_flag_6147`, with `reason` `loyalty_benefit` and an `expiration_date` exactly one year after the current date in `MM/DD/YYYY`. For under two years, offer the supported permanent no-annual-fee downgrade while preserving account history; do not invent a downgrade tool if none is supplied.
- `not_using_card`: remind the customer of applicable benefits and suggest a recurring subscription to keep the card active.
- `found_better_card`: ask what features they value and offer help applying for a Rho-Bank card with similar or better supported benefits if one is identified.
- `unhappy_with_rewards`: review available bonus-category enrollment and ways to maximize rewards based on spending.
- `negative_experience`: apologize, gather details, and escalate to a supervisor if warranted. Do not promise a goodwill credit without a supported mechanism.
- `simplifying_finances` or `other`: acknowledge the preference without pressure.

If the customer still wishes to close after this discussion, make one tier-appropriate retention offer:

- entry tier: 500 bonus points or a $5 statement credit;
- mid tier: 2,000 bonus points or a $20 statement credit;
- premium or above: 5,000 bonus points or a $50 statement credit.

Use a card-tier source supplied by the runtime or policy. Do not guess a tier from a card name. If no supported tier classification is available, explain that the offer cannot be determined through the available workflow and obtain assistance rather than fabricating an offer.

Honor the customer’s decision. Only proceed after a clear continued closure request or decline of the retention offer. If the customer accepts a retention solution, do not close the account.

## 6. Final recheck and close

Immediately before calling the closure tool, repeat the pending-replacement-order check for the selected account. If a non-final replacement order now appears, stop. If account facts may have changed materially since eligibility was checked, refresh the relevant account/dispute information as well.

Unlock and invoke `close_credit_card_account_7834` with:

```json
{"credit_card_account_id":"<selected account ID>","user_id":"<verified user ID>"}
```

Do not retry a closure operation after an ambiguous, timeout, or unknown result. Preserve the result and escalate through the supported process. If the tool explicitly reports an eligibility failure, explain it and do not claim closure.

## 7. Complete customer communication

After confirmed successful closure, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards may be redeemed for 45 days after the closure request; after that they are forfeited.
- A full annual-fee refund may be available if closure occurs within 37 days after the annual fee posted.
- Closing a credit card can affect credit score by reducing available credit and affecting utilization, especially for a high-limit or old card.

Where applicable, disclose documented product effects. For example, a Green Rewards Card is listed as providing a 0.4% Green Account savings APY bonus, so closure may affect the customer’s qualifying savings APY. Do not claim unrelated product effects without a supporting policy.

## Eligibility helper

`scripts/closure_eligibility.py` reads one JSON object from stdin and emits one JSON object to stdout. It is advisory validation; the executor must supply facts obtained from banking tools.

Input schema:

```json
{
  "opened_on": "MM/DD/YYYY",
  "current_date": "YYYY-MM-DD or timestamp beginning YYYY-MM-DD",
  "balance": "$0.00 or numeric value",
  "disputes_for_account": [{"status":"closed"}],
  "replacement_orders": [{"status":"delivered"}]
}
```

Set `disputes_for_account` to `null` when a user-level dispute response cannot be reliably associated with the target account. The output contains individual check results, `eligible`, and `blockers`. Example invocation from a shell-capable executor:

```sh
python3 scripts/closure_eligibility.py <<'JSON'
{"opened_on":"01/01/2024","current_date":"2025-01-01","balance":"$0.00","disputes_for_account":[],"replacement_orders":[]}
JSON
```

Validate that `eligible` is true only when all four checks pass. A malformed date, balance, dispute set, or order set must be treated as a blocker, not as a pass.
