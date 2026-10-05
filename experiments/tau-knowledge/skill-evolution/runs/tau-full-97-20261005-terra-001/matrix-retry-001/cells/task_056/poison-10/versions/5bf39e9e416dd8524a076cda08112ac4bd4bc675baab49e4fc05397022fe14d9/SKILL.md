---
name: business-checking-account-recommendation
description: Give a direct, evidence-based recommendation for a documented business checking account using the customer's stated needs, supplied account terms, applicable promotions, and eligibility facts. Use for informational product comparisons and fee-waiver analysis; do not use it to open, change, or close accounts.
---

# Business Checking Account Recommendation

Use this Skill when a customer asks which documented business checking account is right for them. This is an informational comparison workflow, not an account-opening or account-maintenance action.

## Core rule

Once the conversation and supplied product materials establish at least one confirmed fit, provide one direct recommendation in the next customer-facing response. Do not claim that product terms are unavailable when they are present in the supplied materials. Do not repeat discovery questions that the customer has already answered. Do not transfer solely because another product has unresolved eligibility.

A product is a **confirmed fit** only when its relevant eligibility and hard requirements are supported by the conversation and documents. A product that depends on an unknown required fact is a **conditional alternative**, not a confirmed fit.

## Decision procedure

1. Read the opening request and all prior clarification answers. Treat answered clarifications as known customer inputs.
2. Separate the customer's information into:
   - **Hard requirements**, such as no overdraft fees, a stated maximum monthly cost, or a mandatory feature.
   - **Preferences**, such as reliably avoiding a maintenance fee, a lower balance threshold, ATM rebates, team cards, rewards, or upgrading from a basic account.
   - **Unknown eligibility facts**, such as a required formation date.
3. Extract an evidence-backed record for each plausible candidate from the supplied materials. Keep every term tied to its own product. Record, where available: eligibility, overdraft fee, monthly fee, fee-waiver threshold and measurement basis, ATM rebates, rewards, debit-card availability, transaction limits, and requested features.
4. When the customer gives a balance range, use its lower endpoint as the reliably maintainable balance unless they explicitly commit to a different minimum. A fee waiver is reliably attainable only if that balance meets the documented threshold.
5. Exclude candidates with a known conflict with a hard requirement. Mark a candidate conditional if a required eligibility fact, a hard requirement, or a necessary term is unknown. Never assume an unknown fact is satisfied.
6. Apply an active promotion only after identifying confirmed fits. A promotion ranks confirmed fits; it does not override unmet requirements or unverified eligibility.
7. Rank confirmed fits by active promotion, fulfillment of preferences, reliable fee avoidance, lower applicable fee or waiver threshold, and other documented useful features. When the customer says their present account is too basic, do not select it merely because it is inexpensive if another confirmed fit better addresses the stated need for more features.
8. Recommend the highest-ranked confirmed fit. If none is confirmed, explain the blocking condition and ask only for the missing fact that could change the result.

Use `scripts/recommend_accounts.py` after extracting structured, evidence-backed candidate records. It has no embedded product catalog: all candidate values must come from the materials supplied for the current request.

## Required response content

For a confirmed recommendation, provide customer-facing prose rather than only a tool result or another question. The response must:

1. Clearly identify one account as the best confirmed fit using direct language such as “I recommend [account].”
2. Explicitly address every hard requirement. If avoiding overdraft fees matters, plainly state the documented overdraft-fee outcome.
3. State the monthly maintenance fee and the exact fee-waiver threshold, including the threshold’s documented measurement basis when available.
4. Compare the threshold to the customer’s reliable balance. Where cash flow is variable, say that the fee can apply when the balance does not meet the threshold and suggest a balance alert. Never guarantee a waiver unless the evidence supports that guarantee.
5. Address practical requested features with their documented caps and qualifications. For ATM rebates, state the monthly cap and do not promise it will cover spending above that cap.
6. Mention a promotional account with unresolved eligibility only if useful. Label it conditional and state exactly what must be verified. Do not call it eligible, qualifying, or recommended.
7. Do not promise approval, fee reversals, or an account action.

Use `scripts/compose_recommendation.py` to render the response from the extracted terms. Before sending, confirm that every script input is supported by the current supplied materials. The executor must send the resulting direct recommendation when its inputs describe a confirmed fit; it must not replace it with a deferral.

## Screening script interface

`scripts/recommend_accounts.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input fields:

- `as_of`: required ISO date or timestamp used to assess promotion dates.
- `requirements`: object with optional `zero_overdraft_required` (boolean), `reliably_maintainable_balance` (nonnegative number), `maximum_monthly_fee` (nonnegative number), `must_waive_monthly_fee` (boolean), `required_features` (array of feature names), and `preferred_features` (array of feature names).
- `candidates`: array of evidence-backed candidate objects. Each requires `name`; optional fields are `overdraft_fee`, `monthly_fee`, `waiver_balance`, `waiver_basis`, `eligibility`, `features`, and `sources`.
- `eligibility`: optional object with `status` of `confirmed`, `conditional`, or `ineligible`. A nonempty `condition` is required for `conditional` and `ineligible`.
- `features`: optional object mapping feature names to `true`, `false`, or `null`.
- `promotions`: optional array of `{name, starts_on, ends_on, priority}` objects.

The output contains `recommendation`, `qualified`, `conditional`, `excluded`, and `questions`. A null recommendation means no confirmed candidate was supplied. Verify that candidate names are unique, supplied terms are evidence-backed, and all hard requirements are represented before relying on the result.

## Composition script interface

`scripts/compose_recommendation.py` reads one JSON object from stdin and emits `{"status":"ok","message":"..."}` on stdout.

Required `recommendation` fields are `name`, `overdraft_fee`, `monthly_fee`, and `waiver_balance`. Optional `waiver_basis` describes the threshold measurement. `customer` may contain `reliable_balance` and boolean `cash_flow_variable`. `features` may contain `atm_rebate_monthly`, `cashback_rate`, `cashback_qualifier`, `business_debit_cards`, and `additional`. `conditional_alternatives` may contain `{name, condition}` records.

The script validates input shape, renders only caller-supplied values, retrieves no account information, and performs no banking action.

## If the customer asks to open an account

Keep the recommendation separate from account opening. Before any banking action, verify customer identity, authority, account ownership where applicable, product eligibility, available balance or credit, fees, limits, cutoffs, recipient or card details, and required confirmations. Use only approved banking tools and the documented opening procedure after those checks.