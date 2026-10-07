---
name: business-checking-account-recommendation
description: Recommend exactly one business checking account when a customer describes cost, overdraft, eligibility, and feature needs. Applies to informational account-selection conversations; it does not open or alter an account.
---

# Business Checking Account Recommendation

Use this Skill to turn stated customer needs into one supported account recommendation. Treat non-negotiable requirements as hard filters, then apply any active promotion only among accounts that pass every hard filter.

## Scope and safety

- This is an informational recommendation. Do not identify a customer, verify identity, open an account, or make account changes merely to recommend an account.
- Do not imply that an existing account makes the customer eligible for a new one. If the customer later asks to open an account, follow the separate opening procedure, including identity and eligibility checks, before any account-opening action.
- Do not invent fees, eligibility rules, features, waivers, or availability. An unverified value is not evidence that a hard requirement is met.
- A monthly fee cap and a request to avoid a fee are different: a stated cap tests the listed monthly fee, while fee-waiver details should be disclosed separately when material.

## Method

1. Extract the customer’s actual requirements from the opening and all clarifications. Mark explicit language such as “need,” “must,” “non-negotiable,” and a maximum fee as hard requirements. Treat preferences such as enhanced service as tie-breakers unless the customer makes them mandatory.
2. Obtain the current date from a supplied observation or the approved time tool if a date-sensitive policy matters.
3. Build an account fact set from `references/business_checking_facts.md` and any current task materials. Keep only facts directly supported by those materials.
4. Reject an account if it fails or cannot be shown to meet a hard requirement. In particular, check age/formation eligibility, monthly maintenance fee ceiling, and an exact $0 overdraft-fee requirement independently.
5. If more than one account qualifies, apply an active promotion in its stated order. A promotion never overrides a failed requirement. If there is still a tie, select the account with the strongest documented match to the customer’s stated preferences; ask a focused question only when no single supported choice is possible.
6. Use `scripts/select_account.py` for a repeatable filter/ranking decision when the account facts have been structured. The script makes no bank action and its result must still be checked against the source facts.
7. Give the customer one direct recommendation. State why it meets the hard needs, disclose meaningful tradeoffs or thresholds, and briefly explain why a higher-priority promotional option was not selected when relevant. Do not present an unqualified alternative as equally suitable.

## Response shape

Use concise customer-facing language:

- Lead with: “I recommend **[account]**.”
- Tie the recommendation to each stated hard need using verified facts.
- State material ongoing conditions (for example, a monthly charge, waiver threshold, or minimum-balance condition) without claiming the customer will qualify for a waiver.
- If a promotion is relevant, say it was applied only after eligibility and hard requirements were checked.
- Offer to explain the selected account or discuss opening next; do not begin opening in the same step without the required separate checks.

For the supplied account materials, the relevant verified product facts and promotion dates are in `references/business_checking_facts.md`.

## Script interface

`python3 scripts/select_account.py < request.json`

The script reads one JSON object from standard input and writes one JSON object to standard output. It accepts:

- `as_of`: ISO date (`YYYY-MM-DD`), required.
- `requirements`: object with optional `company_age_years`, `max_monthly_fee`, `zero_overdraft_required`, and `required_features` (list of feature strings).
- `accounts`: nonempty list of objects containing `name`, `monthly_maintenance_fee`, `overdraft_fee`, optional `max_company_age_years`, and optional `features`.
- `promotions`: optional list of objects containing `account`, `start`, `end`, and integer `rank` (lower rank is preferred).

For a hard requirement, use a numeric fee or age limit when known. Use `null` only for non-required facts; a candidate with an unknown value for a requested hard constraint is excluded. The output includes `qualified`, `selected`, `rejections`, and `selection_basis`. Validate that `selected` is either `null` or appears in `qualified`, and confirm the prose only uses facts supplied to the script or source material.
