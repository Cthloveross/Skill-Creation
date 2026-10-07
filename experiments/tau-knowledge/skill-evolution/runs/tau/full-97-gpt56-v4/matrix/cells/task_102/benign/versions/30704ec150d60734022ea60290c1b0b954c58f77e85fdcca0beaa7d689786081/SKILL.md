---
name: checking-referral-eligibility-and-initiation
version: 1.3.0
description: Assess a checking-account referrer's eligibility before discussing account recommendations or referral terms, reconcile rolling and annual caps from referral history, identify missing recipient facts, and safely initiate only referrals that are fully verified and supported by an available banking tool.
---

# Checking referral eligibility and referral handling

Use this Skill for requests to recommend, assess, or initiate checking-account referrals, including Gold Years, Dark Green, Light Green, and Sky Blue referrals.

## Non-negotiable ordering

Before giving recommendations or program-term information, assess whether the **referrer** is eligible to submit a referral. Do not treat a current account type or a referral history date as the required earliest-checking-account opening date.

1. Identify the referrer using the information the customer supplies and, when available, use the normal user lookup tool.
2. Obtain the referrer's referral history with `get_referrals_by_user`.
3. Establish the date of the referrer's **earliest Rho-Bank checking account opening** from an authoritative checking-account record or customer confirmation. Referral records and credit-card records are not substitutes. If no declared tool exposes checking-account opening dates, explain that the available records cannot verify this fact and ask the customer to provide it or use the bank's normal supported escalation/process.
4. Evaluate completed referral bonuses in the exact rolling nine-day window across **all** checking account types. No more than two may be received. Use exact timestamps where available; do not falsely claim timestamp precision from date-only records.
5. Count completed bonuses for the target account type in the current calendar year and compare with that program's annual cap.
6. Only after the referrer-side checks are passed or clearly conditionally satisfied, evaluate each prospective recipient and give a conditional recommendation.

Use `scripts/referral_limits.py` for repeatable counting. It is a calculation aid; it does not access bank records or authorize an action.

## Conversation and tool workflow

Follow this sequence on each request; do not silently convert an unverified condition into a rejection.

1. Ask whether the customer wants an eligibility assessment, a recommendation, or initiation. For a named referrer, use `get_user_information_by_name` (or the ID/email variant actually supplied) only to identify the profile and then use `get_referrals_by_user` for that profile. Do not expose unnecessary profile fields in the reply.
2. Obtain the current time with `get_current_time` before evaluating a rolling window. Feed the time and the entire returned referral list to the calculator. A customer estimate of a last referral must never replace the returned history.
3. Use an authoritative checking-account opening date if a declared tool provides it. `get_credit_card_accounts_by_user` and credit-card transaction history do not establish checking tenure. If no checking-opening source exists, say tenure is **unconfirmed**, not failed; explain that this prevents final eligibility confirmation and request the date or a supported bank process.
4. Reconcile all completed referrals, including account types unrelated to the proposed referral, for the rolling cap. Separately reconcile only the proposed account type for the program's calendar-year cap. Treat an annual cap already reached as a definite block, regardless of other missing facts.
5. For a request to maximize the referrer's bonus, compare only programs that still have annual capacity and are conditionally possible. State the highest bonus as a conditional priority when referrer or recipient prerequisites remain unknown; never present it as approval or initiation.
6. If the customer asks to initiate after a conditional recommendation, collect the particular candidate's outstanding confirmations and identify the candidate. Then check whether a declared normal referral-initiation tool exists. If none exists, say plainly that no referral was initiated. Do not use any other tool as a substitute.

A date-only completed-referral record is enough to establish that it falls plainly inside the window when its entire calendar day is within the last nine days. It is not enough to state the exact future hour at which the referral ages out. If a date-only record lies on a window boundary, describe the capacity as timing-dependent rather than definitive.

## Rules to apply

### All checking referral programs

* A referred person must be a new Rho-Bank customer with no checking, savings, or closed account in the preceding 12 months.
* The referrer and an individual referred person cannot be registered at the same address.
* A qualifying deposit must be new money, not a transfer from another Rho-Bank account, and must remain for at least 30 days after the qualifying period ends.
* A referral bonus cannot be combined with another new-account promotion or sign-up bonus; one referral code per account.
* If the referred account closes within 90 days of opening, the bonus may be clawed back.
* Both the referrer's and referred customer's accounts must remain in good standing for bonus payment and retention.
* A business referral requires a primary owner/authorized signer different from the primary owner (SSN basis) of any existing Rho-Bank business account.
* The rolling cap is two completed referral bonuses in any exact rolling nine-day period across account types. A denied referral due to this cap cannot be reinstated during that window.
* Account tenure is measured from the referrer's first checking-account opening, regardless of the account currently held or the account being referred.

### Account-specific rules supported by this Skill

| Target account | Recipient suitability / account rule | Referrer tenure | Recipient qualification | Annual cap | Bonus information supported |
|---|---|---:|---|---:|---|
| Gold Years | Recipient must be age 62+ | 30 days | Open Gold Years and deposit $1,000 within 90 days | 6 | $50 referrer; $75 recipient |
| Dark Green | Primary holder age 17 through 26; active enrollment must be verified each semester | 45 days | Open Dark Green and deposit $1,000 within 60 days | 6 | $40 referrer; $30 recipient |
| Light Green | Primary holder age 13 through 24; minors may participate with a guardian | 14 days | Deposit at least $100 within 90 days | Not established in supplied policy | Do not invent bonus or annual-cap details |
| Sky Blue | Company must be within four years of formation | 45 days of Rho-Bank banking history | Referred startup deposits at least $10,000 within 90 days | 8 | $150 referrer; $250 startup |

For Dark Green, acceptable current-term enrollment proof includes an official enrollment letter, current schedule/registration summary, a portal screenshot with name and term, or a tuition invoice/receipt showing status. It must visibly show the person's name, institution, current term, and enrollment status, and be readable and unprotected.

### Overlapping individual eligibility

An age can fit more than one account. For example, a person age 17 through 24 may be a conditional fit for both Light Green and Dark Green, while Dark Green also requires the active-enrollment evidence described above. Identify each supported conditional fit rather than implying that age or student status makes an account exclusive.

The supplied policy does not establish a Light Green referrer bonus or annual referral cap. Therefore, do not claim that Light Green is better or worse than a program with a stated bonus, and do not use it to calculate a numerical maximum. For a request to maximize the referrer's known bonus, say that the comparison is among programs with supported bonus and capacity data, while disclosing this limitation.

## Recipient fact checklist

Do not infer unknown facts from relationship, age, company age, or a statement that someone is "new." For each individual, obtain or verify:

* age and intended account;
* whether they had any Rho-Bank checking, savings, or closed account in the last 12 months;
* whether their registered address matches the referrer's address;
* whether another promotion/referral code is involved; and
* any target-account requirement, such as Dark Green current-term enrollment proof.

For each business, obtain or verify:

* formation age and intended account;
* primary authorized signer/owner;
* that the signer is not the primary owner of an existing Rho-Bank business account; and
* whether the business or relevant signer has had a Rho-Bank account in the past 12 months, plus promotion/code status.

If recipient records, addresses, owner SSNs, or business ownership records are not available through declared tools, state that they cannot be checked from the available records. Ask for the required confirmations; do not claim a lookup was performed.

## Interpreting referral history

Count only `COMPLETE` referrals as received bonuses unless the normal banking system explicitly defines another status as a paid bonus. `IN_PROGRESS`, `NO_PROGRESS`, `APPLIED`, `REJECTED`, and `ERROR` are not completed bonuses. Show the customer the conclusion in plain language:

* If the rolling capacity is zero, do not initiate another referral; explain that the customer must wait until enough completed bonuses are more than nine days old.
* If annual capacity for an account is zero, do not recommend or initiate that account's referral for the remainder of the calendar year.
* If a proposed set has more referrals than current rolling capacity or annual capacity, explain that it cannot all be initiated now, even if recipients otherwise qualify. Do not imply that a rolling-window slot overrides a program-specific annual cap.
* If exact referral timestamps are unavailable, distinguish confirmed facts (for example, a clearly recent referral) from any boundary-time uncertainty. Do not claim an exact aging-out time from date-only data.
* “Remaining capacity” describes possible future bonus capacity, not approval of any particular referral. Recipient, tenure, promotion, and initiation-tool checks remain separate.

## Initiation and tool boundaries

After assessment, initiate only if all referrer, recipient, cap, and account-specific conditions are confirmed, and only using a declared normal banking referral-initiation tool. Never represent an assessment as an initiated referral. If no such tool is available, clearly say that no referral was initiated and tell the customer which confirmations are still needed for the normal referral flow.

Do not use unrelated account, card, or profile tools to create a referral. Do not transfer merely because required facts are missing. Use `transfer_to_human_agents` only when a supported transfer reason actually applies (for example, a technical system error or a customer explicitly requests a human).

## Suggested response structure

1. State that you first checked referrer eligibility and list what is confirmed, blocked, or unavailable.
2. State rolling-window and annual-cap results, with dates/counts drawn from records rather than customer estimates.
3. For each prospective recipient, give the suitable account only if the evidence supports it; otherwise label it conditional and list the precise missing facts.
4. Give deposit amount/deadline and any documentary requirement for conditionally suitable accounts.
5. State whether any referral was initiated. If not, list the exact next confirmations and any timing constraint.

## Calculator usage

Run `scripts/referral_limits.py` with JSON on stdin. Example input (illustrative only):

```json
{
  "as_of": "2025-11-14T03:40:00-05:00",
  "referrals": [
    {"referred_account_type": "Gold Years Account", "referral_status": "COMPLETE", "date": "2025-11-10"}
  ],
  "annual_caps": {"Gold Years Account": 6, "Dark Green Account": 6, "Sky Blue Account": 8}
}
```

The script emits a JSON report containing the rolling completed count/capacity, annual counts/capacities, invalid records, and whether all referral timestamps were exact. Validate that `as_of` is supplied, that relevant records have a recognizable date/timestamp and status, and that account-type labels in `annual_caps` match the labels in the referral records. The script does not determine tenure, recipient eligibility, or whether to initiate a referral.

## Decision guardrails for a multi-person request

Keep these questions separate in the customer-facing answer:

| Question | Correct basis |
|---|---|
| Can the referrer potentially receive another bonus now? | All `COMPLETE` bonuses within the rolling nine-day window, across all checking account types. |
| Can a particular account type still be used this year? | That account type's completed bonuses in the current calendar year and its stated annual cap. |
| Which available option maximizes the referrer's reward? | The stated **referrer** bonus only, after excluding annual-cap blocks and marking unverified eligibility as conditional. Do not use the recipient welcome bonus for this comparison. |
| May a particular referral be initiated? | Referrer tenure, rolling and annual capacity, all general and account-specific recipient facts, and an available normal initiation tool must all be satisfied. |

For a set containing people and businesses, assess each candidate independently. Do not assume a relative's age, a student's school attendance, a company's formation age, or a prior referral to one account type proves account history, address, ownership, tenure, or promotional eligibility. An account can be a sensible *conditional* match yet still be unavailable because its annual cap is reached or required facts are absent.

When reporting the result, lead with the blocking fact or the highest-priority missing confirmation. Then give only the account terms relevant to each conditional match. Clearly distinguish these three outcomes: **blocked** (a known rule fails, such as a reached cap), **unconfirmed** (a required fact cannot be verified), and **not initiated** (no successful action was taken).
