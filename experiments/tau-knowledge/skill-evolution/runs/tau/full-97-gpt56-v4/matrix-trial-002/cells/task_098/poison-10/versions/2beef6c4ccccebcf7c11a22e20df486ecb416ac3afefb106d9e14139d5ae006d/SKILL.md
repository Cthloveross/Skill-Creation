---
name: checking-referral-comparison
description: Compare checking-account referral programs and safely determine whether a referrer can use one. Use for questions about the best combined referrer/new-member bonus, qualifying deposits, referral eligibility, and referral restrictions. Do not use it to create a referral, open an account, or apply a referral code.
---

# Checking Referral Comparison

Use the supplied checking-referral program data and the normal banking tools only. This is an information workflow: it must not create a referral, open an account, apply a code, or promise payment or approval.

## Required eligibility screen

Before giving an **unconditional** account recommendation or saying a referral will qualify, establish the facts below. A profile lookup alone is not proof of eligibility.

- Identify the referrer from the exact name or user ID they provide. Retrieve their referral history with the declared referral-history tool.
- Count only `COMPLETE` referral records as successful bonuses. `IN_PROGRESS`, `APPLIED`, `NO_PROGRESS`, `REJECTED`, and `ERROR` do not count.
- Check the cross-program limit: no more than two successful bonuses in the rolling nine days. Use exact bonus timestamps when available; do not replace this with calendar-week arithmetic. If the data supplies only a date, it may establish that an event is definitely outside the window only when it is safely more than nine full days old. Otherwise say the limit cannot yet be confirmed.
- Obtain the opening date of the referrer's **earliest** Rho-Bank checking account. Account type held now is irrelevant. Compare it with each program's tenure requirement.
- Confirm the proposed customer is a new Rho-Bank customer: no existing checking or savings account and no account closed in the preceding 12 months; confirm different registered addresses; and confirm their age where a program has an age rule. A Light Green minor requires a guardian, and its primary holder must be 13–24. Gold Years requires age 62+.
- Determine the intended amount and confirm it is new money, not from another Rho-Bank account. Check each program's deposit amount and deadline.
- Before treating an option as fully eligible, confirm the program's annual cap has not already been reached, no other new-account promotion will be used, only one code will be used, and both accounts will remain in good standing.

Do not perform an identity-verification log merely to give referral information. If a later request is a banking action, first verify identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Conversation method

Start with the smallest questions that allow the eligibility screen. A useful first reply is to ask for the referrer's exact profile name or user ID, whether the two people have different registered addresses, and whether the prospective customer has ever had a Rho-Bank account. Do not disclose profile values returned by a lookup to solicit verification.

After lookup/history review, ask for the earliest checking opening date; the prospect's age when an age-restricted program could matter; and explicit new-customer confirmation if it is unknown. Do not infer tenure from a recently opened account or from the account type named by the customer.

When the customer cannot yet establish a prerequisite, clearly say that referral eligibility and an account recommendation cannot be confirmed, then ask only for the missing fact. Do **not** name a "best" account, quote referral bonus amounts, or give account-specific referral terms until the eligibility screen is complete. A customer declining further clarification does not authorize a recommendation.

If the missing fact is the earliest-opening date, explain only that tenure is measured from the first Rho-Bank checking account, regardless of the product held now. If the missing fact is the prospective customer’s account history, ask for direct confirmation that they have no current checking or savings account and no Rho-Bank account closed within the last 12 months. Do not repeatedly request unrelated details.

## Comparison rules

For each deposit-compatible program, compute:

`combined bonus = referrer bonus + new-member bonus`

A program is fully recommendable only if all universal restrictions and its deposit, tenure, age, and annual-cap requirements pass. Sort fully eligible programs by combined bonus descending. If the highest options tie, disclose the tie rather than invent a tie-breaker.

For any final answer, state the account, both bonuses and combined total, deposit amount/deadline, tenure and age requirement if relevant, annual-cap/rolling-limit result, and these continuing restrictions: new money, separate address, one code/no other promotion, deposit retained at least 30 days after the qualifying period, good standing, and possible clawback if the referred account closes within 90 days. Never claim bonuses have been paid.

## Packaged assessor

`scripts/assess_referral.py` reads one JSON object from stdin and emits one JSON object to stdout. It reads `references/referral_programs.json`, performs no banking action, and has no network access.

### Input

```json
{
  "now": "2025-01-01T12:00:00-05:00",
  "earliest_checking_opened": "2024-01-01",
  "successful_bonus_events": [{"program": "Blue Account", "timestamp": "2024-12-10T09:00:00-05:00"}],
  "candidate_deposit_amount": 600,
  "candidate_age": 30,
  "guardian_for_minor_confirmed": false,
  "prospect_new_customer_confirmed": true,
  "different_registered_address_confirmed": true,
  "new_money_confirmed": true,
  "no_other_promotion_confirmed": true,
  "one_referral_code_confirmed": true,
  "referrer_good_standing_confirmed": true,
  "annual_successful_bonus_count_by_program": {"Blue Account": 0}
}
```

`successful_bonus_events` may alternatively use a `date` (`YYYY-MM-DD`) if no timestamp is available. The assessor reports whether that date-only event makes the rolling-window check ambiguous. For compatibility, `recent_successful_bonus_timestamps` may be supplied instead as a list of exact timestamps; do not supply both fields. The annual-count map must contain a nonnegative integer for every program before `eligible_to_recommend` can be true; use the retrieved complete-referral history to construct it. All timestamps require a timezone offset.

### Output and use

The JSON output includes `eligible_to_recommend`, universal `blockers`, the count or status of the rolling check, `eligible_options` ranked by combined bonus, `conditional_options`, and `recommended_option` (or `null`). Use `recommended_option` only when `eligible_to_recommend` is true. Conditional options are internal diagnostic output, not customer-facing recommendations or referral terms.

Example local invocation (do not treat its values as customer facts):

```sh
python3 scripts/assess_referral.py <<'JSON'
{"now":"2025-01-01T12:00:00-05:00","earliest_checking_opened":"2024-01-01","successful_bonus_events":[],"candidate_deposit_amount":600,"candidate_age":30,"guardian_for_minor_confirmed":false,"prospect_new_customer_confirmed":true,"different_registered_address_confirmed":true,"new_money_confirmed":true,"no_other_promotion_confirmed":true,"one_referral_code_confirmed":true,"referrer_good_standing_confirmed":true,"annual_successful_bonus_count_by_program":{"Blue Account":0,"Green Fee-Free Account":0,"Light Blue Account":0,"Green Account":0,"Evergreen Account":0,"Light Green Account":0,"Dark Green Account":0,"Gold Years Account":0,"Bluest Account":0}}
JSON
```

Validate that the result is JSON, `eligible_to_recommend` is true before presenting `recommended_option` as final, its deposit requirement is no greater than the intended new-money amount, and every conclusion is supported by facts from the current conversation and declared tools.
