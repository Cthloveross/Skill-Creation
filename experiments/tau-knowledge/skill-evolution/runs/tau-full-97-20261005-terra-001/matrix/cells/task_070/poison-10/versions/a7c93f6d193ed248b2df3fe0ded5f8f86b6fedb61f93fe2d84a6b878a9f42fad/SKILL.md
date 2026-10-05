---
name: business-checking-recommendation
version: 1.1.0
description: Recommend one evidence-supported business checking account when a customer states hard needs such as overdraft-fee tolerance, ATM-fee rebates, company age, APY, and support preferences. Applies to informational product recommendations and to the prerequisite workflow before a separately requested account opening.
---

# Business Checking Recommendation

Use this Skill to turn a customer's stated must-haves into one defensible business-checking recommendation. Treat explicit customer constraints as hard requirements. Do not describe an account as the "easiest" or as having the "most perks" unless the available product facts establish a comparison criterion.

## Recommendation workflow

1. Extract explicit, material requirements from the conversation. Examples include a maximum overdraft fee, a minimum monthly ATM-rebate amount, company age, a minimum APY, monthly-fee tolerance, and support needs.
2. Distinguish documented facts from unknowns. Do not infer that a product satisfies a requirement merely because its documentation is silent.
3. Run the deterministic evaluator with the actual conversation-derived values:

   ```sh
   python3 scripts/recommend_business_checking.py <<'JSON'
   {"requirements":{"max_overdraft_fee":0,"minimum_atm_rebate_per_month":15,"minimum_apy":1},"as_of":"YYYY-MM-DD"}
   JSON
   ```

   The values above are interface examples only; do not reuse them unless the customer actually supplied them.
4. If `selected` is present, recommend that one account. Explain every fact that establishes the match for the customer's hard requirements and disclose the returned material caveats.
5. When APY is a requirement, directly state the selected account's documented APY and whether it meets the customer's minimum. State documented compounding only when returned by the evaluator. Never call a documented APY unknown, unavailable, or unconfirmable.
6. If `selected` is null, do not force a recommendation. Use `needed_clarifications` to ask a targeted question, or explain that no documented candidate meets every hard requirement.
7. Use promotional priority only after confirming that every candidate already meets every hard requirement. Promotional priority never overrides an eligibility condition or a customer constraint.

## Customer-facing response

Give a concise single-account recommendation, followed by the facts establishing the fit and material tradeoffs. State a documented ATM-rebate cap as a cap on **eligible out-of-network ATM fees**; do not imply every ATM fee or third-party surcharge is covered. State the APY numerically when it is relevant to the customer's decision.

Do not claim approval, account-opening eligibility, or waived fees unless those facts have been verified. For the packaged facts, a rebate cap does not establish that an ATM operator will not impose a separate surcharge. Foreign ATM fees may have a separate percentage-and-minimum calculation.

## Date-sensitive promotion

The evaluator applies the documented business-checking promotional ordering only from 2025-11-01 through 2025-11-30 inclusive and only when an `as_of` date is supplied. During that period, it orders otherwise qualifying candidates as Sky Blue first and Lime Green second. Outside that period, or without a date, it does not invent a general product ranking; if more than one candidate qualifies, it returns no selection and requests a tie-breaker preference.

## Account-opening boundary and workflow

A recommendation is informational and does not itself open or modify an account. If the customer asks to open the recommended account, first obtain explicit confirmation of the exact account class and then use the execution agent's normal banking tools.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For a business-checking opening, verify and retain the results for: customer identity; at least one existing personal checking account with status OPEN; fewer than six business checking accounts; no accounts with status CLOSED; an existing checking-account balance of at least $500; and the customer's confirmed account-class selection. Log identity verification only after confirming the required identity fields. Once all prerequisites are verified, use the authorized `open_bank_account_4821` workflow available to the execution agent. If any prerequisite, authorization, tool access, or confirmation is missing, stop and obtain it rather than guessing or taking an account action.

## Script interface

`scripts/recommend_business_checking.py` reads one JSON object from stdin and emits one JSON object to stdout. It uses only packaged product facts and does not call banking systems.

Input schema:

- `requirements` (object, required): one or more of:
  - `company_age_years` (nonnegative number), or `company_within_four_years` (boolean)
  - `max_overdraft_fee` (nonnegative number), or `requires_zero_overdraft_fee` (boolean)
  - `minimum_atm_rebate_per_month` (nonnegative number)
  - `minimum_apy` (nonnegative number, expressed as a percent; for example `1` means 1%)
  - `requires_dedicated_manager` (boolean)
- `as_of` (optional string): ISO date or timestamp used exclusively for the dated promotion.

Output schema:

- `selected`: selected product object or `null`.
- `qualifying`: all products documented to meet every supplied hard requirement.
- `disqualified`: candidate-specific reasons a hard requirement was not met or was undocumented.
- `promotion`: whether the dated ordering was applied.
- `needed_clarifications`: constraints needed to break a non-promotional tie or resolve insufficient input.
- `customer_summary`: documented selected-product facts suitable for a customer response, including APY when documented.
- `caveats`: material disclosed terms for the selected product.

## Validation

Before using the result, ensure every supplied hard requirement is represented in the selected product's documented facts and that a non-null `selected` appears in `qualifying`. For a requested minimum APY, the final recommendation must include the selected account's documented APY and accurately compare it with the requested minimum. If a required property is undocumented, treat that candidate as non-qualifying. Preserve currency values as decimal strings in customer-facing responses; do not round percentage-based foreign-ATM fees unless the customer asks for a calculation.
