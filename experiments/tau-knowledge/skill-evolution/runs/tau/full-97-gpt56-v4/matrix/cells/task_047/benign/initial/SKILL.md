---
name: credit-card-closure-with-retention
version: 1.0.0
description: Safely handles a verified customer's request to close a credit-card account, including account-specific eligibility checks, required retention workflow, closure, and policy disclosures. Use when a customer asks to close a credit card or indicates they want to leave for another card.
---

# Credit Card Closure With Retention

## Scope and safety rules

Use this Skill for a customer-requested credit-card closure. Perform actions only for the authenticated customer and the specific account they identify. Do not infer account identifiers, card tier, dispute status, replacement status, a closure-reason history result, or a customer's decision to decline retention.

A closure requires all of the following:

- authenticated identity;
- a $0.00 outstanding balance;
- no active or pending disputes;
- account age of at least 60 days;
- no pending replacement card orders.

A pending or ambiguous prerequisite blocks closure until resolved. Do not call the closure tool merely because the customer states that a condition is satisfied.

## Runtime inputs and account selection

1. Identify the user using an identifier supplied by the customer, or look up the customer by the supplied name or email with the corresponding normal banking lookup tool.
2. Retrieve that user's credit-card accounts. Match the requested card against the returned card type and account information. If there are multiple plausible matches, ask the customer to identify the intended account; do not select one based only on a similar name.
3. Obtain a current timestamp using `get_current_time` when identity verification must be logged or when evaluating account age/history dates.

## Identity verification

Before discussing sensitive account details, retention, or submitting a closure:

1. Ask the customer to confirm **two of these four** identity fields: date of birth, email, phone number, and address.
2. Compare each supplied field with the user record. Information retrieved from the system is not itself a customer confirmation.
3. After two fields match, call `log_verification` once with the complete values from the authenticated user record (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`) and the current timestamp as `time_verified`.
4. If fewer than two fields are confirmed, a value does not match, or the user cannot be uniquely identified, explain that verification is incomplete and do not proceed with account actions.

## Required eligibility sequence

After successful verification, gather fresh account-specific evidence. Use the account profile for balance and open date, but use the specialist tools below rather than asking the customer to know dispute or replacement status.

1. Check the requested account balance and calculate whether the open date is at least 60 calendar days before the current date.
2. Unlock `get_user_dispute_history_7291`, then call it with `user_id`. Review dispute records for the target account where an account/card association is available. Any active, pending, open, or under-review dispute blocks closure. If the response cannot establish whether a relevant dispute is resolved, treat it as unresolved and do not close.
3. Unlock `get_pending_replacement_orders_5765`, then call it with `credit_card_account_id`. An empty collection passes. If orders are returned, only `delivered` and `cancelled` are final; any other, missing, or ambiguous status blocks closure.
4. Optionally send the gathered facts to `scripts/assess_closure_eligibility.py` to consistently assess balance, age, disputes, and replacement orders. The script is advisory: the executor remains responsible for passing only target-account dispute records where the tool makes that distinction available.
5. If any check fails, clearly identify the condition that must be resolved. Do not make a retention offer and do not call the closure tool.

Immediately before actually calling the closure tool, recheck replacement orders if a material amount of time or additional conversation has occurred since the first check. A newly pending replacement blocks closure.

## Retention workflow for an eligible account

Follow these steps only after all eligibility requirements pass.

1. Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id`. Determine whether this *specific* account has a closure-reason record within the preceding year.
2. If a record exists within that period, do not make a retention offer. Tell the customer that you will proceed with their requested closure once they confirm they still want it.
3. If there is no such record, obtain the customer's reason. A clearly stated reason in the opening request can be used, but confirm the categorization if it is unclear. Map it to exactly one allowed value:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
4. Unlock and call `log_credit_card_closure_reason_4521` with exactly `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add fields.
5. Address the reason before offering retention. For a customer who found a better card, ask which features matter and explain any supported comparable benefits; do not claim unknown benefits or approval outcomes. For annual-fee concerns, only offer a one-year waiver to a customer known to have at least two years of tenure, using `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, a date one year from today in `MM/DD/YYYY`, and reason `loyalty_benefit`. For shorter tenure, offer the documented no-annual-fee downgrade rather than a waiver if that option is available in the runtime.
6. If the customer still wants to close, make one tier-appropriate offer:
   - entry tier: 500 bonus points or $5 statement credit;
   - mid tier: 2,000 bonus points or $20 statement credit;
   - premium or above: 5,000 bonus points or $50 statement credit.

Do not infer a retention tier from a card's branding, rewards type, or a card name. Determine it from an authoritative runtime account field or supported policy source. If no authoritative tier is available, say that the available records do not establish the applicable standardized offer and obtain the customer's direction or route the retention question to the appropriate specialized team rather than inventing an offer.

Do not close after an offer unless the customer expressly declines it or otherwise clearly reaffirms the request to close. If they accept an offer or need time, leave the account open.

## Closing the account

Once identity is verified, the account is eligible, the retention protocol is either skipped due to prior history or completed, and the customer has expressly confirmed closure:

1. Reconfirm that the selected account and authenticated `user_id` are the intended pair.
2. Recheck pending replacement orders immediately before closure if needed.
3. Unlock `close_credit_card_account_7834` and call it with exactly `credit_card_account_id` and `user_id`.
4. Report only the tool's actual outcome. Never retry a closure operation whose outcome is unknown.

After a successful closure, tell the customer that:

- a confirmation email and final statement will arrive within several business days;
- remaining rewards may be redeemed for 45 days after submitting the closure request, after which they are forfeited;
- a full annual-fee refund may be available only when closure is within 37 days of the fee posting.

For cash-back cards whose rewards are stored as points, explain that one point equals $0.01 for a statement-credit or eligible checking-credit redemption. Calculate a cash equivalent only from the selected account's observed reward balance; do not mix rewards from other accounts.

## Tool and failure handling

- Unlock every named specialist tool with `unlock_discoverable_agent_tool` before `call_discoverable_agent_tool`.
- If a lookup returns no unique user/account, ask for the needed identifier.
- If a specialist check errors or returns incomplete/ambiguous data, do not close; retry only when appropriate or use the supported escalation path.
- If the customer asks for a human, or the workflow cannot safely establish a required condition, transfer with the most applicable supported transfer reason and a concise summary of verification and checks already completed.
- Keep account IDs, user IDs, retrieved PII, and customer-specific results out of reusable notes and scripts.

## Eligibility helper

`scripts/assess_closure_eligibility.py` reads one JSON object from stdin and writes one JSON object to stdout. It does not call bank systems or perform actions.

Input schema:

```json
{
  "current_time": "timestamp containing a calendar date",
  "account": {"current_balance": "currency string or number", "date_of_account_open": "MM/DD/YYYY or YYYY-MM-DD"},
  "disputes": [{"status": "..."}],
  "replacement_orders": [{"status": "..."}]
}
```

`disputes` must contain only records the executor has determined are relevant to the target account; use an empty array only when the tool reliably establishes none are relevant. Output contains `decision` (`eligible`, `blocked`, or `review_required`) and individual check results. A runnable invocation is:

```sh
python3 scripts/assess_closure_eligibility.py < eligibility_input.json
```

Before relying on an `eligible` result, confirm that all four output checks are `pass`. Treat `review_required`, malformed input, or a nonzero script exit as a reason to pause rather than close.
