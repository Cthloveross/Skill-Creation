---
name: credit-card-account-closure
version: 1.0.0
description: Handle a customer's request to close a specific credit card account: verify identity, establish all closure prerequisites, follow the retention protocol only when allowed, and use the authorized closure tool when the customer confirms closure.
---

# Credit Card Account Closure

Use this Skill for a customer-initiated request to close a credit card. Treat a name, email lookup, account listing, or a customer's statement that they have no disputes as account-location or preliminary information, **not** identity verification.

## Required order of operations

1. **Identify the requested account.** Obtain the customer identifier through an available lookup and list that customer's credit-card accounts. Match the card the customer named; do not act on a different account merely because it belongs to the same customer.
2. **Verify identity before account action.** Ask the customer to confirm any two of the four profile fields: date of birth, email, phone number, and address. Do not read the values aloud as prompts. Compare the supplied values to the profile returned by an appropriate user-information tool. If two fields match, obtain the current timestamp and call `log_verification` with the complete profile fields and timestamp. If verification fails or is incomplete, do not disclose account details, make retention offers, or close the account.
3. **Establish closure eligibility before retention.** For the selected account, determine all of the following:
   - outstanding balance is exactly `$0.00`;
   - there are no active or pending disputes;
   - there is no pending replacement card;
   - the account has been open for at least 60 days.

   Use the packaged `scripts/closure_eligibility.py` helper to calculate the balance/age portion from runtime data. Obtain dispute and replacement-card status from available account tools or a verified customer's clear confirmation where no read tool exists. Unknown status is not eligible. If *any* condition fails, tell the customer only what needs resolution (for example, that a remaining balance must be paid in full), and stop. Do not log a closure reason, offer retention, apply a waiver, or attempt closure.
4. **Check prior retention activity.** If the account is eligible, unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`. If there is a closure-reason record within the past year, skip all retention steps and state that you will proceed with the closure request.
5. **For an account with no recent reason record, perform retention.** Ask for the closure reason if it is not already clear, normalize it to one permitted value, and unlock/call `log_credit_card_closure_reason_4521` with exactly `credit_card_account_id`, `user_id`, and `closure_reason`. Permitted reasons are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.

   Address the reason respectfully. For an annual-fee concern, determine tenure: at least two years may receive a one-year loyalty waiver; otherwise offer a permanent downgrade to a no-annual-fee card while preserving history. A waiver requires unlocking `apply_credit_card_account_flag_6147` and supplying `credit_card_account_id`, `user_id`, `flag_type: "annual_fee_waived"`, an expiration date exactly one year from the current date in `MM/DD/YYYY`, and `reason: "loyalty_benefit"`. For other reasons, follow the applicable concern discussion in the available policy.

   If the customer still wishes to close, make no more than the applicable tier offer: entry tier 500 points or $5; mid tier 2,000 points or $20; premium-and-above 5,000 points or $50. Do not pressure the customer. If the customer accepts a retention outcome, do not close the account.
6. **Close only after the customer elects closure.** When eligibility is still satisfied and the customer has declined retention (or retention was skipped due to prior history), unlock `close_credit_card_account_7834` and call it with `credit_card_account_id` and the verified `user_id`. Do not invent additional arguments. Report only the actual tool result.
7. **Post-closure communication.** On a successful closure, explain that a confirmation email and final statement arrive within several business days, that unredeemed rewards remain redeemable for 45 days after the closure request and are then forfeited, and that a full annual-fee refund may apply when closure occurs within 37 days of the fee posting.

## Failure and safety handling

- Do not infer that eligibility is met from the customer's request. Recheck account-specific balance and opening date at runtime.
- Do not use a closure tool as an eligibility probe and never retry a closure whose outcome is unknown.
- If an account cannot be uniquely matched, request clarification. If a required specialized tool cannot be unlocked/called, explain that the requested action cannot yet be completed rather than claiming success.
- If a customer wants a human instead, transfer with the applicable supported transfer reason and summarize verification and eligibility work already completed.

## Eligibility helper

`scripts/closure_eligibility.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs no bank action.

Input schema:
```json
{
  "account": {"date_of_account_open": "MM/DD/YYYY", "current_balance": "$0.00"},
  "current_time": "YYYY-MM-DD HH:MM:SS TZ",
  "pending_disputes": false,
  "pending_replacement_cards": false
}
```
`pending_disputes` and `pending_replacement_cards` may be `true`, `false`, or `null` if unknown. Output contains `eligible`, `account_age_days`, `balance_cents`, and a nonempty `blocking_reasons` list when not eligible. Validate that `eligible` is true and that all four prerequisite values are known before proceeding. Example runtime invocation: run the script with the selected account and current-time tool result; use its JSON response as a decision aid, then perform the required conversational and banking-tool steps above.
