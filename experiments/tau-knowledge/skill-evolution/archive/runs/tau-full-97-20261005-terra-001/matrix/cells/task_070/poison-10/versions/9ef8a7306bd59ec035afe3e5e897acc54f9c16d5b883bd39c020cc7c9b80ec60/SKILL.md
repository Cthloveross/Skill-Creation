---
name: business-checking-recommendation
version: 1.0.0
description: Recommend one evidence-supported business checking account when a customer states hard needs such as overdraft-fee tolerance, ATM-fee rebates, company age, and support preferences. Applies to informational product recommendations; it does not open or modify an account.
---

# Business Checking Recommendation

Use this Skill to turn a customer's stated must-haves into one defensible business-checking recommendation. Treat explicit customer constraints as hard requirements. Do not describe an account as the "easiest" or as having the "most perks" unless the available product facts establish a comparison criterion.

## Workflow

1. Extract only explicit, material requirements from the conversation. Examples include a maximum overdraft fee, a minimum monthly ATM-rebate amount, company age, monthly-fee tolerance, and support needs.
2. Distinguish facts from unknowns. Do not infer that a product satisfies a requirement merely because its documentation is silent.
3. Run the deterministic evaluator:

   ```sh
   python3 scripts/recommend_business_checking.py <<'JSON'
   {"requirements":{"company_age_years":5,"max_overdraft_fee":0,"minimum_atm_rebate_per_month":15},"as_of":"2025-11-14"}
   JSON
   ```

   The executor supplies the actual conversation-derived values; the example values are illustrative only.
4. If `selected` is present, recommend that one account and explain only the matching facts in `customer_summary`. Mention material tradeoffs returned in `caveats`.
5. If `selected` is null, do not force a recommendation. Use `needed_clarifications` to ask a narrowly targeted question, or explain that no documented candidate meets every hard requirement.
6. When the evaluator reports a promotion was applied, use its resulting order only after confirming each candidate already meets every hard requirement. Never use promotional priority to override eligibility or a customer constraint.

## Output to the customer

Give a concise single-account recommendation, followed by the facts that establish the match and any material fee/balance caveat. For example, state the documented ATM-rebate cap and overdraft fee rather than implying that every ATM or every third-party surcharge is covered. Do not claim approval, account-opening eligibility, or waived fees unless those facts have been verified.

For the known product facts in this package, an ATM-rebate cap is a cap on eligible out-of-network ATM fees. Foreign ATM fees may use a separate percentage-and-minimum calculation. A rebate cap does not establish that an ATM operator will not charge an additional surcharge.

## Date-sensitive promotion

The bundled evaluator applies the documented business-checking promotional ordering only from 2025-11-01 through 2025-11-30 inclusive, and only when an `as_of` date is supplied. During that period, it orders otherwise qualifying candidates as Sky Blue first and Lime Green second. Outside that period, or without a date, it does not invent a general product ranking; if more than one candidate qualifies, it returns no selection and requests a tie-breaker preference.

## Account-opening boundary

A recommendation is informational and does not require a banking action. If the customer asks to open the recommended account, switch to the account-opening workflow and do not perform or imply an opening until all prerequisites are verified.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For business-checking opening, verify: customer identity; at least one existing personal checking account with status OPEN; fewer than six business checking accounts; no accounts with status CLOSED; an existing checking-account balance of at least $500; and the customer's account-class selection. Once verified, use the authorized `open_bank_account_4821` workflow available to the execution agent. If any prerequisite, tool access, or confirmation is missing, stop and obtain it rather than guessing or taking an account action.

## Script interface

`scripts/recommend_business_checking.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

- `requirements` (object, required): any of:
  - `company_age_years` (number), or `company_within_four_years` (boolean)
  - `max_overdraft_fee` (number), or `requires_zero_overdraft_fee` (boolean)
  - `minimum_atm_rebate_per_month` (number)
  - `requires_dedicated_manager` (boolean)
- `as_of` (optional string): ISO date or timestamp used exclusively for the dated promotion.

Output schema:

- `selected`: selected product object or `null`.
- `qualifying`: all products documented to meet every supplied hard requirement.
- `disqualified`: candidate-specific reasons a hard requirement was not met or was undocumented.
- `promotion`: whether the dated ordering was applied.
- `needed_clarifications`: constraints needed to break a non-promotional tie or resolve insufficient input.
- `customer_summary` and `caveats`: safe facts for the final customer-facing response.

## Validation

Before using the result, ensure that every supplied hard requirement is represented in the selected product's documented facts. A non-null `selected` is valid only when it appears in `qualifying`. If a required property is undocumented, treat that candidate as non-qualifying. Preserve currency values as decimal strings in any customer-facing response; do not round percentage-based foreign-ATM fees yourself unless the customer asks for a calculation.
