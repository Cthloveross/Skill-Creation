---
name: credit-card-account-closure
version: 1.0.0
description: Process a verified customer's request to close one specified Rho-Bank credit-card account. Use for closure eligibility, required retention sequencing, final replacement-card check, closure execution, and required customer communication.
---

# Credit-card account closure

Use this Skill for **one explicitly selected card account at a time**. Do not close other cards merely because the customer mentioned multiple cards.

## Inputs and required evidence

Obtain at runtime:

- Authenticated/verified customer identity and `user_id`.
- The selected `credit_card_account_id` and account details (card type, opening date, current balance, and, if available, tier).
- The customer's closure reason, normalized to one of: `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
- Current time for identity-verification logging and date-based eligibility calculations.

Use the supplied banking tools for live facts. Account listings and prior read-only observations can identify an account, but eligibility-sensitive checks must be current when performed.

## Required workflow

1. **Confirm scope and identity.** Confirm which single card is to be closed. Verify the requester by matching at least two of email, date of birth, phone number, and address against the profile. After a successful match, call `log_verification` with all fields requested by that tool and the current timestamp. Do not continue if identity cannot be verified or the requested account does not belong to that user.

2. **Collect account details and run core eligibility checks.** Retrieve the user's credit-card accounts and locate the exact selected account. Check:
   - balance is exactly `$0.00`;
   - account has been open for at least 60 calendar days;
   - there are no active or pending disputes relating to the selected account; and
   - there are no pending replacement-card orders.

   Unlock and call `get_user_dispute_history_7291` with `user_id`. Review statuses and transaction/card context. Treat open, pending, or under-review disputes for the selected card as blocking. If returned data cannot be tied confidently to the selected account, obtain sufficient account/card context or do not certify this requirement as passed.

   Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. Any order not clearly `delivered` or `cancelled` blocks closure. Repeat this replacement-order check immediately before the close operation, even if it was checked earlier.

   If any eligibility requirement fails, explain the specific blocker and what must be resolved. Do not make retention offers, log a new closure reason, or close the account.

3. **Check for prior closure-reason attempts.** Unlock and call `get_closure_reason_history_8293` using only the selected `credit_card_account_id`. Determine whether it reports a closure-reason record for this account within the prior year. If it does, bypass reason logging and all retention efforts; tell the customer that their request will proceed to closure after final checks.

4. **Log and address the reason when no prior attempt exists.** Ask for a reason if not already supplied, normalize it to the allowed enum, then unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.

   Address the concern before an offer:
   - `annual_fee`: for a customer of at least two years, offer a one-year fee waiver as a loyalty benefit. Apply it only if the customer accepts: unlock `apply_credit_card_account_flag_6147` and use `flag_type: annual_fee_waived`, `reason: loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`. For shorter tenure, offer a permanent no-annual-fee downgrade preserving account history; no unsupported tool action should be invented.
   - `not_using_card`: explain relevant benefits and suggest a recurring subscription.
   - `found_better_card`: ask which features matter and offer help applying for a comparable Rho-Bank card when applicable.
   - `unhappy_with_rewards`: review available bonus-category enrollment and reward-maximization options.
   - `negative_experience`: apologize, gather facts, and escalate to a supervisor when warranted. Do not invent a goodwill-credit tool.
   - `simplifying_finances` or `other`: acknowledge the request without pressure.

5. **Make one retention offer if applicable.** If the customer still wants closure and retention was not bypassed, make the one offer for the account tier:
   - entry tier: 500 bonus points or a $5 statement credit;
   - mid tier: 2,000 bonus points or a $20 statement credit;
   - premium and above: 5,000 bonus points or a $50 statement credit.

   Use a documented tier from the account/profile context; do not infer one from a card name if the runtime does not establish the mapping. If a valid offer and an explicit customer decline are already recorded in the live task context, do not repeat the offer. If the customer accepts a retention path, do not close the account. There is no specified tool for posting a generic points or statement-credit offer, so do not fabricate one.

6. **Close only after final verification.** When the customer declines the offer or retention was validly bypassed, rerun `get_pending_replacement_orders_5765` immediately before closing. Also ensure no new information invalidates the zero-balance, age, or dispute requirements. Unlock and call `close_credit_card_account_7834` with `credit_card_account_id` and `user_id`. Do not add arguments not specified by policy. Report success only from the tool result; on tool failure, do not claim closure and follow the returned error/escalation path.

7. **Customer communication after a successful close.** Confirm that a confirmation email and final statement will arrive within several business days. State that unredeemed rewards may be redeemed for 45 days after the closure request and are then forfeited. If relevant, advise that a full annual-fee refund may apply only if closure is within 37 days of the annual-fee charge. Closing may reduce available credit and affect credit utilization/credit score. Do not promise any unverified fee refund.

## Tool discipline

Discoverable tools must be unlocked before calling them. Use normal banking tools for all live actions; the included script only evaluates supplied structured data and never executes banking actions. Do not expose internal identifiers or unneeded profile data in the customer-facing response.

## Deterministic precheck helper

`scripts/closure_precheck.py` evaluates dates, balance, dispute statuses, and replacement-order statuses from structured facts already retrieved by the executor. It cannot establish whether a user-level dispute belongs to an account; supply only disputes already confirmed as belonging to the selected account, and set `disputes_attributable` accordingly.

Input JSON:

```json
{
  "as_of_date": "YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD",
  "current_balance": "0.00",
  "disputes_attributable": true,
  "dispute_statuses": ["closed"],
  "replacement_order_statuses": ["delivered"]
}
```

Output JSON contains `eligible`, `account_age_days`, `blockers`, `warnings`, and a check-by-check `checks` object. Example invocation in the Skill runtime: run `scripts/closure_precheck.py` with the JSON object above on stdin. Validate that `eligible` is true and `blockers` is empty before advancing to retention/history steps; regardless of this result, perform the required live final replacement-order check immediately before closure.
