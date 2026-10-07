---
name: savings-card-net-return-comparison
description: Compare documented savings-account and credit-card combinations for a customer with a fixed deposit, recurring-access needs, and eligibility constraints. Use for advisory recommendations that maximize one-year savings interest minus disclosed annual fees; do not use it to open, modify, or apply for banking products.
---

# Savings and card net-return comparison

Use this Skill to produce a transparent, source-grounded recommendation for a customer considering one savings account and one credit card. It is designed for cases where a customer gives a deposit amount, expected monthly withdrawals, and eligibility information, and asks which combination maximizes annual savings interest net of annual fees.

## Scope and safety

This is an advisory workflow only. Do **not** submit an application, open an account, link products, enroll the customer, alter account settings, or make any other banking action while using it. Recommendations are not approval decisions.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

If the customer later asks to perform an action, stop the advisory workflow and follow the applicable operational procedure, including the prerequisite control above.

## Method

1. Read the supplied product documentation and conversation. Build a normalized catalog at runtime; do not reuse values from a prior customer or hardcode product facts into this Skill.
2. Record, with source citations, each candidate savings account's APY applicable to the stated balance, minimum opening/ongoing balance, required settings, annual fee, and monthly withdrawal allowance. Record each card's annual fee, known eligibility requirements, and APY bonus for each savings product.
3. Resolve eligibility conservatively:
   - Mark a product `eligible` only where all relevant requirements are known to be satisfied or no such requirement applies.
   - Mark it `ineligible` when a requirement is not met.
   - Mark it `unknown` when a required fact (such as a minimum credit score) is unavailable. If the customer says to treat an unknown requirement as unavailable, mark it `ineligible` for this comparison.
   - Never represent an eligible product as approved; applications can still require underwriting or documentation.
4. Select the base APY that applies at the customer's stated balance. Apply a direct-deposit bonus only if direct deposit is active or the customer confirms they will establish it. Do not assume it.
5. Enter a documented card APY bonus as a card-to-savings pairing. Card bonuses do not stack: for multiple held cards, use only the highest documented applicable card bonus. If evaluating one newly opened card per option, each option has only that card's bonus.
6. Treat conflicting or arithmetically inconsistent rate documentation as unresolved. Do not silently correct a published value. Exclude it from a definitive ranking unless an authoritative source establishes the applicable rate; otherwise show it as a conditional/range scenario and explain the conflict.
7. Treat a stated withdrawal number as a free-withdrawal threshold unless the source expressly calls it a hard maximum. For a customer who needs regular access, prefer options whose documented allowance covers the upper end of their stated monthly need. If their need exceeds a free threshold, flag possible fees and obtain the fee schedule rather than claiming access is impossible.
8. Run `scripts/rank_options.py` with the normalized catalog. It calculates annual interest as `deposit × effective APY`, where APY is already an annual yield, then subtracts disclosed annual savings and card fees. It does not monetize points, cash back, sign-up bonuses, unknown transaction fees, or credit-card interest.
9. Give the customer a concise comparison of qualifying options, the net one-year estimate, APY and fee components, access fit, key requirements, and cited sources. State that withdrawals or changes to the balance will change actual interest. If the customer says both that the principal will remain unchanged and that they will pay bills from savings, use the unchanged-balance assumption for the estimate and explicitly identify the inconsistency.

## Script interface

Run from the package root:

```sh
python scripts/rank_options.py < request.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output.

### Input schema

Required top-level fields:

- `customer`: object with `deposit_amount`, `monthly_withdrawals_required`, and `direct_deposit`.
- `savings_accounts`: array of normalized account objects.
- `credit_cards`: array of normalized card objects.
- `card_apy_bonuses`: array mapping a savings account and card to a documented APY bonus.

An account object requires `id`, `name`, `base_apy_percent`, `minimum_balance`, `annual_fee`, and `eligibility`. Its optional `withdrawal_limit` is `{ "count": number, "kind": "free" | "maximum" }`; optional `opening_deposit_minimum`, `direct_deposit_bonus_percent`, `required_paperless`, `paperless_confirmed`, `rate_status`, `sources`, and `notes` preserve decision context.

A card object requires `id`, `name`, `annual_fee`, and `eligibility`. A bonus object requires `savings_id`, `card_id`, and `apy_bonus_percent`; `source` is recommended. Eligibility values accepted as qualifying are `eligible`, `available`, and `not_required`. Use `unknown` or `ineligible` otherwise.

Optional `pair_benefits` records may provide a documented `withdrawal_limit` override for a particular savings/card pair. Optional `settings.strict_withdrawal_fit` defaults to `true`; with that default, options below the customer's needed withdrawal count are excluded. Set it to `false` only to display such options with a warning.

### Output and validation

The output contains `recommended`, `qualifying_options`, and `excluded_options`. Monetary output values are decimal strings rounded to cents. A qualifying option must have confirmed eligibility, enough funds for known minimums, a verified applicable rate, and a suitable withdrawal allowance under the selected strictness setting.

Before relying on the result, verify that every normalized APY, fee, eligibility decision, and pairing bonus has a source citation in the response. Review `excluded_options` rather than treating omitted products as nonexistent. If `recommended` is `null`, explain what prerequisite, source conflict, or missing fact prevents a reliable recommendation and request only the information needed to resolve it.
