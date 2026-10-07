---
name: checking-referral-screening-and-recommendation
description: Screen a checking-account referrer's eligibility before discussing referral recommendations, match prospective personal or business referrals to supported account programs, calculate annual and rolling referral constraints, and identify information that must be verified before a referral or account-opening action.
---

# Checking Referral Screening and Recommendation

Use this Skill for requests to recommend checking accounts in connection with a referral, assess whether a referral can proceed, or explain a referral's applicable qualification conditions. It supports read-only screening and recommendations; it does **not** submit referrals, open accounts, or promise a bonus.

## Banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Inputs and scope

Gather, at minimum:

- Referrer identity or user ID, the current time, and the intended account type(s).
- The referrer's account history, including the earliest checking-account opening date. Tenure is based on the oldest checking account, not the account currently held.
- The referrer's referral history, including status, program/account type, and an exact completion/bonus timestamp where possible.
- For an individual: age and facts required by the proposed product (for example, current student enrollment for Dark Green).
- For a business: formation age and the primary authorized signer/owner. Do not collect or disclose more contact data than is needed for the next step.
- Before referral submission: confirmation the referred party is a new customer with no open account or account closed in the last 12 months; a different registered address; and, for businesses, a different primary owner than every existing Rho-Bank business account based on the primary authorized signer's SSN.

Treat an answer already supplied by the user or a clarification as an established fact unless it is internally inconsistent. Maintain a fact ledger while responding. Do not re-request, describe as unknown, or say that confirmation is needed for a fact in that ledger.

In particular, if a candidate's supplied age meets an account and referral age threshold, state that the candidate meets that age requirement based on the supplied age. Keep separate any requirement for documentary verification. For example, a 19-year-old currently enrolled student meets Dark Green's age and general referred-person age requirements; current-semester enrollment documentation can still be required. Say that enrollment verification is needed, not that the person's exact age or age-18 threshold must be reconfirmed.

The available read-only tools may be used as follows:

1. Resolve an unambiguous referrer identity with `get_user_information_by_name`, `get_user_information_by_id`, or `get_user_information_by_email`.
2. Obtain referral history with `get_referrals_by_user`.
3. Obtain checking-account dates and statuses with `get_all_user_accounts_by_user_id_3847` when that tool is available in the runtime.
4. Obtain the current timestamp with `get_current_time` before evaluating a rolling window.

Do not treat a name lookup as identity verification. If the request advances to a banking action, verify two of the four identity fields (date of birth, email, phone number, address) and call `log_verification` before acting.

## Required screening order

**Do this before providing referral recommendations or describing referral terms.**

1. Resolve the referrer and read their account and referral records.
2. Determine their checking tenure from their earliest checking opening date.
3. Count `COMPLETE` referrals by program in the current calendar year and compare them to that program's annual cap.
4. Count successful referral bonuses in the exact trailing nine-day interval across **all** checking-account programs. Do not substitute calendar weeks. A dated-but-not-timestamped record near the cutoff is indeterminate; obtain the timestamp rather than asserting it is out of the window.
5. For each proposed target program, confirm referrer tenure, annual-cap availability, and rolling-window availability. If the referrer is not eligible for that target, do not recommend it as a referral program. State the blocking category and what timing or information is needed instead.
6. Only after the referrer screen passes for a target, assess the prospective referral's product match and clearly distinguish established facts from prerequisites that still need validation.

Multiple referrals may be in progress, but no more than two successful referral bonuses may be received in any rolling nine-day window. The rolling limit is shared across all checking programs. Do not infer that applications or referrals will qualify simultaneously; qualification dates determine bonus-limit impact.

## Program matching rules

Use `references/referral_programs.json` as the supported-product catalog. Do not invent program benefits, caps, deposits, or deadlines absent from the catalog.

- **Dark Green Account:** a candidate may match the product at ages 17–26, but a referral candidate is subject to the general 18+ restriction. Current enrollment must be verified each semester. For a qualifying referral, the referrer needs 45 days of checking tenure and the referred person must deposit $1,000 within 60 days. The annual cap is six. If the candidate's supplied age is 18–26, their age condition is satisfied; do not ask to reconfirm it.
- **Gold Years Account:** candidate must be 62 or older. The referrer needs 30 days of checking tenure; the qualifying deposit is $1,000 within 90 days; the annual cap is six.
- **Sky Blue Account:** company must be within four years of formation. The referrer needs 45 days of checking tenure; the startup must deposit $10,000 within 90 days; the annual cap is eight. During the documented November 1–30, 2025 promotion, recommend Sky Blue first only when it meets every stated requirement and multiple business products qualify.
- Other catalog programs may have referral requirements but incomplete product-fit data. Do not assert that they are suitable unless the customer's requirements can be checked from authoritative information.

For every potentially qualifying referral, explain that qualifying funds must be new money, cannot come from another Rho-Bank account, and must remain for at least 30 days after the qualifying period. A bonus cannot be combined with another new-account promotion or sign-up bonus; only one referral code may be used. A bonus may be clawed back if the referred account closes within 90 days, and both accounts must remain in good standing.

## Running the helper

Run the deterministic helper with JSON on stdin:

```json
{
  "now": "2025-01-15T12:00:00-05:00",
  "referrer": {
    "earliest_checking_opened": "2024-01-01"
  },
  "referrals": [
    {
      "referred_account_type": "Gold Years Account",
      "referral_status": "COMPLETE",
      "completed_at": "2025-01-10T09:00:00-05:00"
    }
  ],
  "candidates": [
    {
      "label": "prospective-person",
      "account_type": "Gold Years Account",
      "profile": {"kind": "person", "age": 65}
    }
  ]
}
```

Use:

```text
run_skill_script(relative_path="scripts/review_referrals.py", input_json=<object above>)
```

The script emits JSON with `errors`, `screening_complete`, shared `rolling_window`, annual counts, and one `candidates` result per requested target. A candidate is `referral_recommendation_permitted` only if the target program is known, the referrer tenure is established and sufficient, that program's annual cap has remaining capacity, and the shared rolling window is not already full. `product_fit.established_conditions` records supplied conditions already satisfied; do not later present them as pending. `pending_general_referral_checks` lists checks not established from the supplied data.

Validate that: (a) `errors` is empty, (b) `screening_complete` is true before relying on referral recommendations, (c) every suggested target has `referral_recommendation_permitted: true`, and (d) `product_fit.status` is `eligible` or explicitly conditional with the required proof described. Treat `unknown`, `ineligible`, and `blocked` values as a stop for that referral recommendation.

## Completing the customer response

Give a short, decision-oriented result:

1. State whether the referrer screen was completed and whether the shared nine-day capacity affects timing.
2. For each prospective referral, first state relevant established candidate facts and conditions they already meet, then list only genuinely unresolved requirements. Do not turn a supplied age, enrollment statement, company age, or other established fact into a new question.
3. Name only an account that is both an eligible product match and a referral-permitted target. If one is merely a good account fit but its referral cap is exhausted, say it is not currently available as a bonus-eligible referral; do not imply otherwise.
4. Identify unresolved eligibility: new-customer/12-month history, different address, business primary-owner comparison, exact rolling timestamps, deposits, and any required enrollment proof. A statement that someone is currently enrolled establishes the enrollment fact but does not replace a policy requirement for acceptable current-semester documentation.
5. Explain annual counts from records rather than relying on the customer's estimate.
6. Do not open an account, create a referral, or expose another person's record. If asked to take an action, follow the banking control above, obtain explicit account selection and any required confirmation, and use only tools actually available in the runtime. If a required owner-record comparison tool is unavailable, say that eligibility cannot yet be confirmed rather than guessing.

Referral statuses can be described accurately when asked: `COMPLETE` means qualification was met; `IN_PROGRESS` means the account is open but its deposit requirement is unmet; `NO_PROGRESS` means no application; `APPLIED` means awaiting a decision; `REJECTED` means denied; and `ERROR` means a system error.
