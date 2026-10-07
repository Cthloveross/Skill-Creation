---
name: business-checking-account-recommendation
description: Provide a direct, evidence-based recommendation for a business checking account from supplied product materials and a customer's stated needs. Use for informational comparisons, fee-waiver analysis, promotion-aware ranking, and eligibility-sensitive alternatives. Do not use to open, modify, or close an account.
---

# Business Checking Account Recommendation

Use this Skill when a customer asks which documented business checking account best fits their business. This is an informational recommendation workflow; it does not itself perform a banking action.

## Completion rule

When the conversation and supplied product materials establish one or more confirmed fits, give the customer one direct recommendation in the next customer-facing response. Do not say that terms are unavailable when they are in the supplied materials. Do not repeat discovery questions that the customer has already answered, and do not transfer solely because another product has an unresolved eligibility condition.

A product can be recommended only when its relevant hard requirements and eligibility are supported by the current conversation and documents. A product with an unknown required eligibility fact is a **conditional alternative**, not a confirmed fit.

## Decision procedure

1. Read the opening request and every clarification in the current conversation. Treat prior clarification answers as known customer inputs.
2. Separate inputs into:
   - **Hard requirements:** for example, zero overdraft fees, a maximum monthly cost, or a mandatory operational feature.
   - **Preferences:** for example, reliably avoiding a maintenance fee, a lower waiver threshold, ATM rebates, team cards, rewards, or an upgrade from a basic account.
   - **Unknown product eligibility facts:** for example, a required business formation date.
3. Build a separate evidence-backed record for each candidate. Keep product terms attached to the product they describe. Record, where available: overdraft fee, monthly fee, waiver threshold and its measurement basis, eligibility rules, ATM rebates, rewards, card limits, and other requested features.
4. For a stated balance range, use its lower end as the reliable balance unless the customer clearly commits to a different minimum. A fee waiver is reliably attainable only when that reliable balance meets the documented threshold.
5. Exclude any account with a known hard-requirement conflict. Mark an account conditional when a required eligibility fact, hard requirement, or necessary product term is unknown; never assume an unknown is satisfied.
6. Apply an active promotion only after determining confirmed fits. Promotional priority ranks confirmed fits; it never overrides a conflict or an unverified eligibility requirement.
7. Rank confirmed fits by applicable promotion, coverage of stated preferences, reliable fee avoidance, lower documented costs or waiver threshold, and documented useful features. If the customer says their current account is too basic, do not select it merely because it is inexpensive when a confirmed upgrade better addresses the stated preferences.
8. Recommend the top confirmed fit. If none exists, state why and ask only for the missing fact that could change the outcome.

Use `scripts/recommend_accounts.py` when records for multiple candidates have been structured. The script contains no product catalog; populate all records from the supplied materials for the current task.

## Required customer-facing response

For a confirmed recommendation, answer in plain customer-facing prose, not merely with a tool result or a question. The response must:

1. Begin by clearly naming one account as the **best confirmed fit** (or equivalent direct wording).
2. Confirm every hard requirement. In particular, explicitly state the documented overdraft-fee outcome when avoiding overdraft fees matters.
3. State the monthly maintenance fee and the exact waiver threshold, including its documented basis (for example, daily balance) when available.
4. Compare that threshold with the customer's reliable balance. If cash flow is variable and can drop below the threshold, clearly say that the maintenance fee can apply during those periods and suggest a balance alert. Do not imply that a waiver is guaranteed.
5. Explain the documented features that make the account practical for the customer, including relevant limits and qualifiers. When documented and relevant, include the out-of-network ATM-rebate cap, cashback rate and eligible-purchase qualifier, and available business debit-card count.
6. If a promotional product is mentioned but its eligibility is unconfirmed, call it a conditional alternative and state exactly what must be verified. Do not describe it as eligible, qualifying, or the recommended account.
7. Do not promise approval, fee reversals, or any account action.

Use `scripts/compose_recommendation.py` to draft this response after extracting the terms from the supplied evidence. Review the draft against the source records before sending it. A script draft is not a substitute for checking that its caller-supplied values are supported by the current materials.

## Screening script interface

`scripts/recommend_accounts.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

- `as_of`: required ISO date or timestamp used for promotion evaluation.
- `requirements`: object with optional `zero_overdraft_required` (boolean), `reliably_maintainable_balance` (nonnegative number), `maximum_monthly_fee` (nonnegative number), `must_waive_monthly_fee` (boolean), `required_features` (array of feature names), and `preferred_features` (array of feature names).
- `candidates`: array of objects. Each needs `name`; optional terms are `overdraft_fee`, `monthly_fee`, `waiver_balance`, `waiver_basis`, `eligibility`, `features`, and `sources`.
- `eligibility`: optional object with `status` of `confirmed`, `conditional`, or `ineligible`, plus a nonempty `condition` when status is `conditional` or `ineligible`.
- `features`: optional object mapping feature names to `true`, `false`, or `null`.
- `promotions`: optional array of `{name, starts_on, ends_on, priority}` objects.

The result contains `recommendation`, `qualified`, `conditional`, `excluded`, and `questions`. A null recommendation means that no confirmed candidate was supplied.

Example structural input:

```json
{"as_of":"2025-01-01","requirements":{},"candidates":[]}
```

Before using a nonempty result, verify candidate names are unique, each supplied term is evidence-backed, and all hard requirements have been represented.

## Composition script interface

`scripts/compose_recommendation.py` reads one JSON object from stdin and writes `{"status":"ok","message":"..."}` to stdout.

Required `recommendation` fields are `name`, `overdraft_fee`, `monthly_fee`, and `waiver_balance`. Optional `waiver_basis` describes how the threshold is measured. `customer` may contain `reliable_balance` and boolean `cash_flow_variable`. `features` may contain documented `atm_rebate_monthly`, `cashback_rate`, `cashback_qualifier`, `business_debit_cards`, and `additional`. `conditional_alternatives` is an optional array of `{name, condition}` records.

The script rejects malformed or unsupported-shaped input. It only renders values supplied by the executor and never retrieves account data.

## If the customer asks to open an account

Keep the recommendation separate from account opening. Before any banking action, verify customer identity, authority, account ownership where applicable, product eligibility, available balance or credit, fees, limits, cutoffs, recipient or card details, and required confirmations. Use only the approved banking tools and documented procedure after those checks.