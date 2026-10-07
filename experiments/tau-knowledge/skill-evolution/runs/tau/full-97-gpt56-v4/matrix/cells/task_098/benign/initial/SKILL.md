---
name: checking-referral-eligibility-and-bonus-comparison
description: Safely handles a checking-account referral question. Use when a customer asks whether they can refer someone, asks for referral terms, or wants the highest combined referrer/new-member bonus. It enforces the required referrer-eligibility check before disclosing referral terms or recommendations, checks the cross-product rolling limit, and then compares supported programs using verified and user-provided facts.
---

# Checking referral eligibility and comparison

## Scope and safety boundary

Use this Skill for informational referral assistance only. Do not create a referral, apply a code, open an account, or promise a bonus; no supplied tool performs those actions.

The controlling sequence is mandatory: **establish whether the referrer can submit a referral before giving any referral-program terms, bonus amounts, account comparisons, or recommendations.** Do not bypass this sequence just because the customer named a potential recipient or a deposit amount.

Do not disclose another person's account information. A prospective recipient's eligibility can normally be assessed from the customer's confirmation; only look up a person if an authorized workflow and a valid identifier are explicitly available.

## Workflow

### 1. Identify and assess the referrer first

Before discussing products or referral amounts:

1. Ask for the customer's full name or profile email if it is not already available in the conversation.
2. Use the matching normal banking lookup tool to obtain the referrer's user ID. Do not treat a name/email lookup alone as full identity verification.
3. Retrieve the referrer's referral history with `get_referrals_by_user`.
4. Obtain the current time with `get_current_time` when evaluating a live rolling window, unless an authoritative current timestamp is already supplied in the task context.
5. Ask for the date their **first-ever Rho-Bank checking account** was opened. The account currently held and the opening date of a later account do not establish tenure. If no tool can provide this date and the customer cannot provide it, tenure is undetermined.
6. Evaluate completed referral bonuses across every checking product in the exact preceding rolling nine-day period. Count `COMPLETE` referrals as successful bonuses. `IN_PROGRESS`, `APPLIED`, `NO_PROGRESS`, `REJECTED`, and `ERROR` are not completed bonuses, though an in-progress referral may later qualify.
7. If referral records contain dates rather than timestamps and a record lies on the nine-day boundary, say the rolling-window result cannot be confirmed from the available precision; do not guess. A date clearly more than nine days old is outside the window.

A referrer with two completed bonuses in the rolling nine-day window cannot receive another referral bonus in that window. The denial cannot be reinstated in that window. The annual cap must also be checked later for the selected product.

If the customer's earliest-checking opening date is unknown, do **not** provide program terms or a recommendation. Explain briefly that you cannot establish their referral eligibility yet and ask only for that date (or an approximate date if that is all they can provide). If their tenure is known but below every applicable threshold, state that they are not currently eligible and withhold program comparisons.

If the interaction requires formal identity verification, verify two customer-supplied identity fields and then call `log_verification` with the complete record and the time returned by `get_current_time`. Do not log verification merely because lookup results exposed profile fields.

### 2. Obtain recipient facts only after the referrer passes the initial check

Ask for only missing facts needed to compare programs:

- age or age range: 13–17, 18–24, 25–61, or 62+;
- confirmation that the person is a new Rho-Bank customer with no checking, savings, or closed account in the last 12 months;
- confirmation that their registered address differs from the referrer's;
- expected qualifying new-money deposit and whether it can meet the listed deposit threshold by its deadline;
- whether an adult guardian is involved when the prospective recipient is 13–17 and Light Green is considered;
- whether another new-account promotion or sign-up bonus will be used.

The qualifying deposit must be new money, not a transfer from another Rho-Bank account, and must remain for at least 30 days after the qualifying period ends. Referral bonuses cannot stack with another new-account/sign-up offer, and only one referral code applies to a new account. For a business referral, also confirm that the business has a different primary owner (primary authorized signer's SSN) from every existing Rho-Bank business account.

Do not infer that a roommate has a different registered address from their living arrangement. Require confirmation about the registered address. Do not infer an unknown age from employment, a first paycheck, or other context.

### 3. Compare programs

Once the facts above are sufficient, use `scripts/rank_referrals.py` with the catalog in `references/referral_programs.json`. The script is a decision aid only; the executor must still follow the disclosure gate in step 1.

Use all of the following when selecting a recommendation:

- recipient age and account-specific age restrictions;
- expected deposit versus minimum deposit and deadline;
- referrer's earliest-checking tenure versus the selected program's tenure threshold;
- general new-customer, address, new-money, hold, and non-stacking restrictions;
- completed bonus count in the exact rolling nine-day window across account types;
- completed referrals for the chosen program in the current calendar year versus that program's cap.

Recommend the eligible program with the highest `combined_bonus`. If facts leave multiple programs conditional, do not call any one a qualifying recommendation. Instead identify the minimum missing facts and, once the referrer is eligible to receive terms, describe the leading option as conditional.

When presenting a final comparison, state the combined amount, the split between referrer and new member, qualifying deposit/deadline, tenure condition, and any salient age restriction. Mention that payment requires all conditions and good standing and that an account closed within 90 days may cause a clawback. Never guarantee that a referral will be approved or paid.

### 4. Clear response patterns

- **Eligibility incomplete:** “I need to confirm when your first Rho-Bank checking account was opened before I can determine whether you can submit a referral. Once that is confirmed, I can compare the eligible options.” Do not state bonuses, rankings, or deposit terms.
- **Rolling limit reached:** Explain that two completed bonuses fall in the rolling nine-day window and that another bonus cannot be received until the oldest applicable completion is more than nine days old. Do not recommend a workaround.
- **Recipient facts incomplete after referrer passes:** Ask for the smallest missing fact set, especially age range and required new-customer/address confirmations. Do not assume an account is appropriate for a minor.
- **All requirements confirmed:** Give the best supported option and concise conditions, without taking an account-opening or referral action.

## Calculator interface

`scripts/rank_referrals.py` reads one JSON object from standard input and writes one JSON object to standard output. It requires no network access or external packages.

Input schema:

- `current_time` (string, ISO-8601 datetime; required)
- `referrer_tenure_days` (integer or `null`)
- `recipient_age_group` (`"13-17"`, `"18-24"`, `"25-61"`, `"62+"`, or `null`)
- `guardian_for_minor` (boolean; default `false`)
- `planned_new_money_deposit` (number or `null`)
- `new_customer_confirmed`, `different_registered_address_confirmed`, `no_other_promotion` (boolean; defaults `false`)
- `successful_referrals` (array; each item has `account_type` and `completed_at`). `completed_at` may be a full ISO timestamp or date-only `YYYY-MM-DD`.

The output reports global eligibility, rolling-window certainty, each program's qualification state and blocking/missing facts, plus `best_qualified` and `best_conditional`. Treat `undetermined` as a reason to obtain more information, not as permission to recommend.

Example invocation after the disclosure gate, using runtime facts rather than fixed customer data:

```bash
python scripts/rank_referrals.py <<'JSON'
{"current_time":"2026-01-15T12:00:00-05:00","referrer_tenure_days":null,"recipient_age_group":null,"planned_new_money_deposit":null,"successful_referrals":[]}
JSON
```

Validation performed by the script includes supported age groups, nonnegative numeric amounts and tenure, required timestamp parsing, duplicate program names, and valid referral-history item structure. Invalid input produces JSON with an `error` field and exits nonzero.
