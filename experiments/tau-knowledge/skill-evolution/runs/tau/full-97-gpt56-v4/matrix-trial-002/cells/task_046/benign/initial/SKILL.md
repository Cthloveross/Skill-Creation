---
name: credit-card-account-closure
version: 1.0.0
description: Handle a customer request to close a credit-card account. Use for authenticated closure requests; verify identity, identify the exact card, enforce closure eligibility before any retention activity, and close only through the authorized closure tool.
---

# Credit Card Account Closure

## Scope and prerequisites

Use this Skill when a customer asks to close a credit-card account. Do not infer that a named card is the only account, and never close a different account.

Before taking an account action:

1. Identify the customer and obtain the account list.
2. Perform standard identity verification: ask the customer to confirm **two of four** profile fields (date of birth, email, phone number, or address) and compare them to the retrieved customer record.
3. Once two fields match, call `log_verification` with the complete retrieved profile and the current timestamp from `get_current_time`.
4. If identity cannot be verified, do not disclose account details, make offers, log a closure reason, or close the account. Ask for the necessary verification information or use the applicable escalation path.

A name, account number, or statement that the customer has no disputes/replacement card is not by itself completed identity verification.

## Locate the requested card

Retrieve the authenticated customer's credit-card accounts using `get_credit_card_accounts_by_user`. Match the customer's requested card description to the returned `card_type` and confirm the intended account if more than one reasonable match exists. Retain the matching `account_id` and authenticated `user_id` for subsequent tool calls.

If no match exists, explain that the requested card could not be located and do not use a different card as a substitute.

## Mandatory eligibility gate

Check eligibility before retention discussion, reason logging, or closure. All conditions must be satisfied:

- account balance is exactly `$0.00`;
- there are no active or pending transaction disputes;
- no replacement card is pending receipt or activation;
- the account has been open for at least 60 days.

Use available account data for the balance and opening date. Obtain or confirm dispute and pending-replacement status through the normal supported banking workflow; do not treat their absence from an account listing as proof that they are clear. The customer may provide a relevant confirmation where the workflow supports it, but resolve conflicts or uncertainty before proceeding.

If any condition fails, clearly state only the blocking requirement(s). In particular, when a balance remains, explain that it must be paid in full before the account can be closed. Do **not** make retention offers, log a closure reason, or invoke closure while any eligibility condition is unmet. Invite the customer to return after resolution.

## Eligible-account protocol

Only after the eligibility gate passes:

1. Unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id` to determine whether that **specific** account has a closure-reason record in the preceding year.
2. If a qualifying prior record exists, skip all retention offers and proceed to closure if the customer continues to request it.
3. If no prior record exists, obtain the customer's reason if it is not already clear. Normalize it to exactly one allowed value:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
4. Unlock and call `log_credit_card_closure_reason_4521` with exactly `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add parameters.
5. Address the concern appropriately, then ask whether the customer still wants to close. For a customer who found a better card, ask what features appealed to them and, if applicable, offer help with a comparable Rho-Bank card rather than assuming one exists.
6. If the customer still wishes to close, make one tier-appropriate retention offer: entry tier: 500 points or $5 statement credit; mid tier: 2,000 points or $20 statement credit; premium and above: 5,000 points or $50 statement credit. Do not pressure the customer and do not invent a tier when it is not known.
7. For an annual-fee concern, a customer of at least two years may be offered a one-year fee waiver using `apply_credit_card_account_flag_6147` only after consent. Its arguments are `credit_card_account_id`, `user_id`, `flag_type`=`annual_fee_waived`, an `expiration_date` one year from the current date in `MM/DD/YYYY`, and `reason`=`loyalty_benefit`. For shorter tenure, discuss a permanent no-annual-fee downgrade that preserves history rather than claiming a waiver.

If the customer accepts a retention solution, apply only the authorized accepted solution and do not close the account. If they decline it, or retention was skipped due to prior closure history, proceed without pressure.

## Close and communicate

Unlock `close_credit_card_account_7834` and call it only after successful identity verification, a passed eligibility gate, and a clear continuing request to close. Supply the exact matching `credit_card_account_id` and authenticated `user_id`. Report the actual tool result; never claim success if the tool returns an error, rejection, or unknown outcome.

After a successful closure request, tell the customer:

- a confirmation email and final statement will arrive within several business days;
- unredeemed rewards may be redeemed for 45 days after the closure request, after which they are forfeited; and
- if an annual fee posted recently, a full refund may be available when closure occurs within 37 days of that fee charge.

## Tool-use safeguards

- Discoverable tool names above must first be unlocked with `unlock_discoverable_agent_tool`, then invoked using `call_discoverable_agent_tool` with a JSON argument string.
- Use current runtime data, never example identifiers or values from this Skill.
- A failed, unavailable, or ambiguous read/action must not be silently treated as a successful check or closure. Explain the limitation and use an appropriate human transfer only when normal resolution is not possible.
- Never repeat an account-changing operation whose status is reported as `UNKNOWN`.
