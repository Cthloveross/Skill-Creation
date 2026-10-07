---
name: business-checking-account-recommendation
description: Provide a direct, evidence-based business checking recommendation from supplied account terms and customer needs. Use for informational account comparisons, fee-waiver analysis, promotion-aware ranking, and eligibility-sensitive alternatives; do not use to open, modify, or close an account.
---

# Business Checking Account Recommendation

Use this Skill when a customer asks which business checking account best fits their stated needs. This is an informational workflow: it does not open an account or make any banking change.

## Core decision rule

Give a direct recommendation when at least one account is a **confirmed fit** based on the supplied materials. Do not defer or transfer merely because another account has an unknown eligibility condition, or because the account terms have already been supplied. Unknown eligibility makes that particular account conditional; it does not prevent recommending another confirmed fit.

A human handoff is not a substitute for an ordinary product recommendation. Transfer only when a supported handoff reason independently applies or the customer requests one.

## Method

1. Extract the customer's requirements into three groups:
   - **Hard requirements:** non-negotiable items such as a zero overdraft fee, a required payment capability, a maximum acceptable monthly cost, or eligibility constraints.
   - **Preferences:** fee avoidance, lower balance requirements, ATM rebates, debit-card rewards, crew cards, deposit limits, or premium functionality.
   - **Unknown facts:** for example, a business formation date needed to establish eligibility. Never assume an unknown is satisfied.
2. Build an account-specific record using only supplied evidence. Keep every fee, waiver threshold, eligibility rule, and feature attached to the correct account.
3. Exclude an account only for a known conflict with a hard requirement. Mark an account **conditional** when a required eligibility or feature fact is unknown. A conditional account is not a confirmed fit.
4. Evaluate a fee waiver using the balance the customer can reliably maintain. If the customer provides a range, use its lower end unless they explicitly identify a different reliable minimum. A customer who can meet a threshold only intermittently should be warned that the fee may apply.
5. Apply an active promotion only among confirmed fits that satisfy every hard requirement. Promotional priority never overrides a known mismatch or an unverified eligibility requirement.
6. Rank confirmed fits by: active applicable promotional priority; ability to reliably avoid a requested fee; known monthly cost; lower waiver threshold; then documented preferred features. Do not use undocumented features as a tie-breaker.
7. If one or more confirmed fits remain, name the top account as the recommendation. Explain the material terms that led to it. Discuss a notable conditional alternative only with its exact unresolved condition.
8. If no confirmed fit remains, ask narrowly for the missing facts that could change the result or explain the hard conflicts. Do not invent account terms or eligibility.

Use `scripts/recommend_accounts.py` when a structured comparison is useful. Populate its candidate records from the current task materials; the script does not retrieve terms and must not be given guessed values.

## Script interface

`scripts/recommend_accounts.py` reads one JSON object from stdin and emits one JSON object on stdout.

Input fields:

- `as_of`: required ISO date or timestamp used to determine active promotions.
- `requirements`: object with optional `zero_overdraft_required`, `reliably_maintainable_balance`, `balance_range`, `avoid_monthly_fee`, `must_waive_monthly_fee`, `required_features`, and `preferred_features` fields.
- `candidates`: array of account records. Each needs `name`; it may include `overdraft_fee`, `monthly_fee`, `waiver_balance`, `eligibility`, `features`, and `sources`.
- `promotions`: optional array of `{name, starts_on, ends_on, priority}` records.
- `exclude_names`: optional array, such as an account the caller has decided not to consider.

`eligibility` can be `true`, `false`, `null`, or an object whose values use those states. `features` can be a list of available feature keys or an object mapping feature keys to `true`, `false`, or `null`. Monetary inputs are nonnegative numbers or numeric strings. `balance_range.minimum` is used when no explicit reliable balance is supplied.

For a runnable empty-data validation call, send this JSON object to the script:

```json
{"as_of":"2025-01-01","requirements":{},"candidates":[]}
```

The result contains `recommendation`, `qualified`, `conditional`, `excluded`, and `questions`. Validate before using a nonempty result that each selected factual field is supported by the current supplied materials and that candidate names are unique. The script reports validation errors as `{ "status": "error", "error": "..." }`.

## Customer-facing response

For a confirmed recommendation:

1. Lead with a clear statement that the named account is the best confirmed fit.
2. State how it meets each material hard requirement, especially any non-negotiable fee policy.
3. State the monthly maintenance fee and the exact waiver threshold. Say whether the customer's reliable balance supports the waiver; if cash flow may dip below it, say the fee can apply and suggest a balance alert.
4. Name the documented practical features relevant to the customer's preferences, including the actual limits or rates where supplied. Do not make a generic claim that an account has "more features" without naming supported features.
5. If a promoted account is discussed but has unknown eligibility, make the alternative explicitly conditional on verifying the relevant fact. Do not call it eligible, qualifying, or the recommended fit until verified.
6. Do not promise approval, availability, future fee reversals, or account actions that have not occurred.

## If the customer asks to open an account

Keep recommendation separate from account opening. Before any opening action, verify identity, authority, desired account class, and all documented opening eligibility requirements. Explain missing prerequisites rather than acting without them. Use only the approved opening workflow and banking tools available in the execution runtime after those checks are complete.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
