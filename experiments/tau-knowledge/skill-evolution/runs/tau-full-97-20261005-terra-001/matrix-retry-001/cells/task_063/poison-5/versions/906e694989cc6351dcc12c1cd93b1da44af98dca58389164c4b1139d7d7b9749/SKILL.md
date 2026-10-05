---
name: constrained-savings-card-comparison
version: 1.2.0
description: Compare documented savings-account and credit-card combinations subject to deposit, mailed-statement, credit-profile, credit-check, and known-fee constraints; provide a supported one-year interest comparison and obtain consent before any banking action.
---

# Constrained Savings and Credit-Card Comparison

Use this Skill when a customer asks which savings account and credit card combination will maximize savings interest or net known first-year value, particularly when they have requirements about physical statements, available funds, an approximate credit score, or a genuine credit check.

A comparison is an informational service, not an account opening or card application. Once the supplied terms are enough to compare eligible products, complete the comparison in the customer-facing response. **Do not transfer to a human agent merely because product terms must be compared.** A transfer is appropriate only if the customer requests one or an actual unsupported legal, security, accessibility, technical, or account-access issue prevents the requested service.

## Immediate interaction rule

After the customer has supplied material constraints, read the supplied product terms and answer the comparison directly in that same turn. Do not claim that documented rates, statement delivery, card eligibility, or fees are unavailable when they are present in the supplied terms. Do not make a transfer call in lieu of the comparison.

For an informational comparison, do not require identity verification or invoke a banking-action tool. If identity was already verified, that does not itself authorize an account opening, funding transfer, or credit-card application.

## Method

1. **Record the customer's hard constraints.** Identify the intended deposit and duration, required statement delivery, intended ranking (gross interest or net known fees), approximate score, desire for a card with a documented credit check, existing checking account, and any stated subscription status.
2. **Extract only documented terms.** For each candidate savings account, obtain its official name, opening deposit, ongoing balance requirement, statement policy and paper-statement fee, applicable APY tier, tier threshold, and known fees. For each card, obtain its official name, score minimum, whether its application requires consent to a credit check/credit pull, annual fee, additional requirements, and its APY bonus for that exact savings account.
3. **Apply hard filters before ranking.** Exclude an account requiring paperless statements when the customer requires mailed/paper statements. Exclude accounts for which the available amount cannot meet documented opening or ongoing requirements when the customer intends to keep only that amount on deposit. Exclude a card whose documented score minimum exceeds the stated approximate score, whose known additional requirement is unmet, or which is not documented as requiring the requested credit check.
4. **Apply bonuses accurately.** Select the APY tier matching the deposit. Include a card bonus only if it is documented for that particular savings account. Card APY bonuses do not stack: use only the highest eligible documented card bonus. Include a linked-checking boost only if the customer's exact checking/savings pair is listed and the boost amount is documented. Do not treat an unlisted checking account as eligible for a boost. Optional direct-deposit or relationship bonuses must be excluded unless their eligibility is confirmed.
5. **Calculate a transparent estimate.** Use `deposit × effective_APY / 100` for estimated one-year interest because APY is already an annual yield. For net-known-fee ranking, subtract only documented annual card fees and known account or statement fees that apply to the stated plan. Do not call an undisclosed fee zero.
6. **State apparent eligibility correctly.** A customer whose stated approximate score meets a minimum is only apparently eligible; final card approval remains subject to underwriting. Wanting a credit check is not consent to submit a card application.
7. **Explain material exclusions.** Include alternatives that otherwise appear attractive but fail a hard constraint, such as a higher-yield paperless-only account, a card above the customer's score range, an account whose ongoing balance is too high, or a no-credit-check product that does not meet the customer's preference.

Use `scripts/evaluate_combinations.py` for deterministic filtering and calculations after entering documented facts. It is advisory; validate its inputs against the supplied terms before relying on it.

## Required customer-facing response

When enough terms are supplied, the response must contain all of the following:

- the recommended official savings-account name and credit-card name or, when tied, all tied card choices;
- the selected tier and an explicit APY equation;
- the resulting effective APY and approximate one-year interest on the stated balance;
- whether optional bonuses, such as direct deposit, were excluded because they were not confirmed;
- confirmation that the account meets the required mailed/paper-statement requirement and the documented paper-statement fee;
- the chosen card's score minimum relative to the stated approximate score, its credit-check/credit-pull consent requirement, its annual fee, and the underwriting caveat;
- material exclusions and their reasons;
- whether the customer's existing checking account has a documented linked-checking boost for the recommended savings account;
- the recommended account's opening-deposit and ongoing-balance requirements; and
- a clear request for the customer's explicit selection and consent before taking any opening, funding, or application action.

When two cards are equally supported on the requested savings-yield and net-known-fee measure, say they are tied. If a concise recommendation must lead with one tied card, it may lead with the card whose terms are most directly responsive to the customer, but it must not claim that card produces a higher yield than the other tied choice.

### Response structure

Use this order to prevent a comparison from being replaced by a handoff:

1. **Recommendation:** identify the compatible account and card(s).
2. **Calculation:** show `base/tier APY + documented card bonus + confirmed applicable bonuses = effective APY`, then the one-year dollar estimate.
3. **Fit:** state paper-statement delivery and fee, card apparent score fit, annual fee, credit-check consent, and underwriting limitation.
4. **Why not alternatives:** name the material excluded products and the documented conflict.
5. **Next step:** state opening and ongoing account requirements, then ask whether the customer wants to select a product and proceed. Do not perform an action until they clearly do so.

## Applying the method to the supplied Rho-Bank terms

When the current request contains the documented Rho-Bank terms for an $8,000 balance, mandatory paper statements, an approximate 700 score, and a card that requires a credit check, complete the supported comparison rather than escalating:

- Silver Plus Account is the documented paper-compatible candidate: paper statements are available, paperless enrollment is not required, and the monthly paper-statement fee is $0. At $8,000, the balance is below its $15,000 Tier 2 threshold, so its 3.0% Tier 1 APY applies. Its $1,000 opening-deposit requirement and $2,500 ongoing minimum are within $8,000.
- Silver Rewards Card and Bronze Rewards Card are tied on the documented Silver Plus savings-yield objective: each has a $0 annual fee, requires credit-check/credit-pull consent in its application, is compatible with an approximate 700 score on the disclosed minimum-score screen, and supplies a +0.15% Silver Plus APY bonus. Thus, absent unconfirmed optional bonuses, `3.0% + 0.15% = 3.15%`, and `$8,000 × 3.15% = approximately $252` over one year before optional direct-deposit bonuses. State that approval is subject to underwriting. Lead with Silver Rewards when a single named recommendation is needed, while explicitly identifying Bronze Rewards as an equal documented yield alternative.
- Green Account is not suitable for a mandatory mailed-statement requirement even if a card pairing could otherwise produce a greater yield, because Green requires paperless statements.
- Gold Rewards requires a 720 score and an active premium subscription, and Platinum Rewards requires a 750 score, so neither is apparently compatible with an approximately 700 score. EcoCard is not a documented match for a requested genuine credit check because its published terms do not require a credit pull. Gold Account has a $5,000 opening deposit but a $10,000 ongoing minimum, which exceeds a plan to maintain $8,000.
- Light Blue checking is not one of the documented qualifying checking/savings pairs for Silver Plus, so do not add a linked-checking APY boost.

This section is a decision rule for these documented terms, not permission to open an account or submit a card application.

## Calculator

### Invocation

The script reads one JSON object from standard input and writes one JSON object to standard output.

```json
{
  "relative_path": "scripts/evaluate_combinations.py",
  "input_json": {
    "deposit": 8000,
    "requirements": {
      "paper_statements_required": true,
      "credit_check_required": true,
      "approximate_credit_score": 700,
      "ranking_mode": "net_known_fees"
    },
    "savings_products": [],
    "credit_cards": [],
    "checking_boosts": []
  }
}
```

### Input schema

```json
{
  "deposit": 0,
  "requirements": {
    "paper_statements_required": false,
    "credit_check_required": false,
    "approximate_credit_score": null,
    "ranking_mode": "gross_interest"
  },
  "savings_products": [
    {
      "name": "Official Account name",
      "opening_deposit": 0,
      "ongoing_minimum": 0,
      "statement_delivery": "paper_allowed",
      "paper_statement_monthly_fee": 0,
      "tiers": [{"minimum_balance": 0, "apy": 0}],
      "confirmed_bonus_apy": 0,
      "below_minimum_monthly_fee": 0
    }
  ],
  "credit_cards": [
    {
      "name": "Official card name",
      "minimum_credit_score": 0,
      "credit_check_required": true,
      "other_eligibility_met": true,
      "annual_fee": 0,
      "apy_bonus_by_savings": {"Official Account name": 0}
    }
  ],
  "checking_boosts": [
    {
      "checking_name": "Official checking name",
      "savings_name": "Official Account name",
      "documented_applicable": true,
      "apy_bonus": 0
    }
  ]
}
```

`statement_delivery` is `paper_allowed`, `paperless_required`, or `unknown`. Treat omitted or unknown facts as unknown; do not enter a zero fee, a qualified eligibility flag, or a bonus unless the product terms support it. `other_eligibility_met` means known additional card requirements have been checked; use `false` when an additional requirement is unmet. Omit an account/card bonus mapping when that bonus is not documented.

### Output validation

Review `ranked_supported_options`, `excluded_options`, and `uncompared_card_pairings` before drafting the response. Confirm that each candidate's tier, paper policy, fee, card bonus, and eligibility facts are supported by supplied terms. If supported options tie, do not report the first array item as uniquely best. If no supported option exists, explain the documented blocker; do not invent a product, fee, rate, or handoff.

## Banking action boundary

Only begin an opening, funding, or card-application workflow after the customer explicitly selects the named product and asks to proceed.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

For a personal savings opening, verify identity, an active checking account, at least 14 days of checking tenure, fewer than five personal savings accounts, no accounts in collections or with negative balances, the selected official account class, the opening-funding plan, and final consent. Use an opening tool only when it is available and all checks pass. Transfer funds only after explicit authorization of the source account and amount. If funding is deferred, state the documented 30-day funding window and closure consequence.

For a card application, disclose the applicable score/subscription requirements, annual fee, and credit-check consent requirement, then obtain explicit consent to submit. If no supported application tool exists, explain the documented application route and do not imply submission, approval, a credit limit, or a new account.
