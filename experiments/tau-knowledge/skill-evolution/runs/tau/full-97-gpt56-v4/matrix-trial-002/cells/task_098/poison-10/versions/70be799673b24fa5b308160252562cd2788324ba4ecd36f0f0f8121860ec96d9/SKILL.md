---
name: checking-referral-eligibility-and-bonus-comparison
description: Safely handles questions about checking-account referral eligibility and compares combined referral bonuses only after the referrer and proposed referral have been verified as eligible. Use for referral-program advice, qualification checks, and non-transactional referral guidance.
---

# Checking Referral Eligibility and Bonus Comparison

Use this Skill for advice about referring someone to a Rho-Bank checking account. It does **not** create a referral, apply a code, open an account, or promise a bonus.

## Safety and sequencing

Before giving referral terms, bonus amounts, or a product recommendation, first check whether the customer can submit a referral. Do not treat a name lookup, an unverified assertion, or an incomplete referral record as proof of eligibility.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For advice-only work:

1. Identify the customer with an available customer lookup using the exact identifier they provided.
2. Verify identity by having the customer confirm at least two profile fields (date of birth, email, phone number, or address). If the runtime provides `log_verification`, get the current time and log the successful verification. Do not disclose profile values merely to obtain confirmation.
3. Retrieve the customer's referral history with the declared referral-history tool. Only `COMPLETE` referrals count as successful bonuses; `IN_PROGRESS`, `APPLIED`, `NO_PROGRESS`, `REJECTED`, and `ERROR` do not.
4. Obtain or verify all of the following before presenting a recommendation:
   - date the referrer opened their **earliest** Rho-Bank checking account;
   - exact timestamps of the last successful referral bonuses, sufficient to test the cross-product rolling nine-day cap;
   - the number of successful bonuses already earned in the relevant account program during the current calendar year;
   - that the proposed customer is new to Rho-Bank, with no current checking or savings account and no account closed in the past 12 months;
   - that the two people have different registered addresses;
   - proposed customer's age, and guardian confirmation if a minor is being considered for Light Green;
   - that the qualifying deposit will be new money, rather than a transfer from another Rho-Bank account; and
   - that no other new-account promotion will be used and only one referral code will be applied.
5. Confirm the intended opening account, qualifying-deposit amount, and deposit timing. The deposit must remain for at least 30 days after the qualifying period ends. Explain that closing the referred account within 90 days can result in a clawback and both accounts must remain in good standing.

If any required fact is unavailable, explain exactly what remains unconfirmed and ask for it. Do **not** name a “best” account, quote bonus amounts, or imply a referral will qualify until the check is complete. If the customer declines or cannot supply the needed information, state that eligibility and a recommendation cannot be confirmed.

A referral that would be a third successful bonus within the preceding rolling nine days is automatically denied and cannot be reinstated during that window. Do not substitute calendar-day or calendar-week arithmetic for exact timestamps. Account type does not affect referrer tenure: tenure begins on the opening date of the earliest checking account.

## Using the packaged assessor

`scripts/assess_referral.py` reads one JSON object from standard input and emits one JSON object on standard output. It performs deterministic comparison of the packaged account programs and labels missing prerequisites.

### Input schema

```json
{
  "now": "2025-01-01T12:00:00-05:00",
  "identity_verified": true,
  "earliest_checking_opened": "2024-01-01",
  "recent_successful_bonus_timestamps": ["2024-12-20T09:15:00-05:00"],
  "candidate_deposit_amount": 600,
  "candidate_age": 30,
  "guardian_for_minor_confirmed": false,
  "prospect_new_customer_confirmed": true,
  "different_registered_address_confirmed": true,
  "new_money_confirmed": true,
  "no_other_promotion_confirmed": true,
  "one_referral_code_confirmed": true,
  "referrer_good_standing_confirmed": true,
  "annual_successful_bonus_count_by_program": {
    "Blue Account": 0
  }
}
```

Use ISO-8601 timestamps with timezone offsets for `now` and successful-bonus timestamps. `recent_successful_bonus_timestamps` must contain the complete set needed to assess the preceding nine days, not just referrals currently in progress. Supply a numeric age when age-specific programs are being considered. The annual-count map must contain a count for every program to be eligible for a final recommendation.

The output contains:

- `eligible_to_recommend`: true only when every global check is satisfied and at least one program-specific option is fully qualified;
- `blockers`: missing or failed universal prerequisites;
- `eligible_options`: fully qualified options, ordered by combined bonus descending;
- `conditional_options`: deposit-compatible options with their unresolved program-specific conditions; and
- `recommended_option`: the highest combined fully qualified option, or `null`.

Do not show `conditional_options` as a recommendation. Use them only to decide what clarification is needed. If multiple fully eligible products tie, present the tie and let the customer choose; do not invent a tie-breaker.

### Runnable call example

At runtime, invoke the script through the supported packaged-script runner and pass a JSON object matching the schema above. For a local Python runtime, the equivalent interface is:

```sh
python3 scripts/assess_referral.py <<'JSON'
{"now":"2025-01-01T12:00:00-05:00","identity_verified":true,"earliest_checking_opened":"2024-01-01","recent_successful_bonus_timestamps":[],"candidate_deposit_amount":600,"candidate_age":30,"guardian_for_minor_confirmed":false,"prospect_new_customer_confirmed":true,"different_registered_address_confirmed":true,"new_money_confirmed":true,"no_other_promotion_confirmed":true,"one_referral_code_confirmed":true,"referrer_good_standing_confirmed":true,"annual_successful_bonus_count_by_program":{"Blue Account":0,"Green Fee-Free Account":0,"Light Blue Account":0,"Green Account":0,"Evergreen Account":0,"Light Green Account":0,"Dark Green Account":0,"Gold Years Account":0,"Bluest Account":0}}
JSON
```

Validate that the script returns valid JSON, that `eligible_to_recommend` is true before using `recommended_option`, that the chosen option's deposit requirement does not exceed the intended new-money deposit, and that every reported tenure, age, annual-cap, and rolling-window condition has evidence from the current interaction and declared tools.

## Response format after successful assessment

Keep the answer concise and conditional only on facts actually verified:

1. identify the qualifying account and combined total;
2. state the deposit amount and deadline, referrer tenure requirement, and any account-age restriction that applies;
3. state the rolling-nine-day and annual-cap result;
4. remind the customer of new-money, address, promotion/code, retention, and good-standing restrictions; and
5. offer the next non-transactional step, such as locating the referral link in the account dashboard.

Never claim a bonus has been paid or that an account will be approved. If a banking action is later requested, re-check all applicable prerequisites and use only declared banking tools with the required confirmation.

## Sources represented in this package

The program data in `references/referral_programs.json` is a structured transcription of the supplied checking-referral terms. General rules include the two-successful-bonuses rolling nine-day cap, new-customer and separate-address restrictions, new-money deposits, promotion/code restriction, retention, clawback, and good-standing requirements. Product-specific data covers Blue, Green Fee-Free, Light Blue, Green, Evergreen, Light Green, Dark Green, Gold Years, and Bluest checking referral programs.
