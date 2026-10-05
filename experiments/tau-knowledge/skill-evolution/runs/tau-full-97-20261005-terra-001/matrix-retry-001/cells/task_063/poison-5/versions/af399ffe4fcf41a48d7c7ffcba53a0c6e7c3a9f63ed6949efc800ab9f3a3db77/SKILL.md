---
name: savings-card-yield-planner
version: 1.0.0
description: Evaluate savings-account and credit-card combinations for a customer’s available deposit, identify the highest supported one-year savings yield, explain eligibility and APY-stacking rules, and safely guide any requested savings-account opening.
---

# Savings and Credit-Card Yield Planner

Use this Skill when a customer wants to compare savings accounts and companion credit cards to maximize savings interest, or asks to open the selected savings account. It separates a recommendation from an account-opening action: a recommendation may be provided from documented terms, while opening an account requires all prerequisites and the customer’s confirmed selection.

## Safety control for banking actions

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not perform an opening, transfer, application submission, or any other banking action merely because a comparison identifies a preferred product.

## Method

1. **Clarify the goal and scope.** Confirm whether the customer means gross savings interest or net value after account and card fees, the amount to deposit, whether it will remain on deposit for a year, and whether they want only products for which they appear eligible.
2. **Collect only documented inputs.** For each candidate, collect the opening deposit, ongoing balance requirement, applicable balance tier at the stated deposit, APY, known recurring fees, and account-specific bonuses. Capture candidate card eligibility requirements, annual fees, whether a credit check/credit-pull consent is required, and its APY bonus for the particular savings account.
3. **Check feasibility before ranking.** A savings product is not fundable now when the available amount is below its required opening deposit. If the amount is below an ongoing minimum, retain it only as a clearly labelled conditional option and include the documented consequence or fee if known. Do not infer an undisclosed fee.
4. **Apply bonuses correctly.**
   - Select only the highest applicable credit-card APY bonus; card APY bonuses do not add together.
   - Select only the highest applicable checking-account APY boost; checking boosts do not add together.
   - Add these selected amounts to base/tier APY only where documentation says the bonus stacks. Do not invent a boost for an unlisted checking–savings pairing.
   - Include relationship, direct-deposit, or tier bonuses only if their eligibility is known and documented.
5. **Calculate an estimate.** For a stable balance, estimated annual savings interest is `deposit × effective_apy / 100`, because APY already represents annual yield. Report it as an estimate, not a guarantee. Show gross interest and, separately, net-after-known-recurring-fees if fees are relevant. A card annual fee is not savings interest; disclose it separately and include it in a net-combination comparison only when the customer asked for net value.
6. **Give an auditable recommendation.** State the selected savings account and card, the applicable rate components, projected first-year gross interest, key conditions, excluded alternatives and why, and limitations caused by missing information. Do not state that approval or a bonus is guaranteed.
7. **If the customer wants to proceed with a savings opening, follow the opening workflow below.** Credit-card application steps should be described according to the product documentation; do not claim that an account was opened or that a card was approved unless the relevant authorized tool confirms it.

## Calculator

Use `scripts/evaluate_combinations.py` for deterministic ranking. It does not call banking tools and does not approve eligibility; it evaluates the supplied facts.

### Input JSON schema

```json
{
  "deposit": 8000,
  "include_card_fee_in_net": false,
  "savings_products": [
    {
      "name": "Official savings account name",
      "opening_deposit": 100,
      "ongoing_minimum": 500,
      "below_minimum_period_fee": 0,
      "base_apy": 4.0,
      "tiers": [{"minimum_balance": 0, "apy": 4.0}],
      "relationship_bonus_apy": 0,
      "other_confirmed_bonus_apy": 0,
      "notes": []
    }
  ],
  "credit_cards": [
    {
      "name": "Official card name",
      "eligible": true,
      "eligibility_notes": ["Customer meets documented requirements"],
      "credit_check_required": true,
      "annual_fee": 0,
      "apy_bonus_by_savings": {"Official savings account name": 0.45}
    }
  ],
  "checking_boosts": [
    {
      "checking_name": "Official checking account name",
      "savings_name": "Official savings account name",
      "eligible": true,
      "apy_bonus": 0,
      "notes": []
    }
  ]
}
```

`tiers` is optional. If provided, the calculator chooses the tier with the greatest `minimum_balance` not exceeding `deposit`; otherwise it uses `base_apy`. A missing bonus mapping is treated as a documented zero only when the caller has already determined that no bonus applies; do not use the script to convert unknown product terms into a zero.

### Output JSON

The script returns `ranked_options`, sorted by estimated gross interest then effective APY. Each option includes feasibility, selected highest card and checking bonuses, effective APY, projected gross interest, known-fee net estimate, eligibility notes, and warnings. `best_option` is the first feasible option; it may be `null` when none can be funded.

Example runtime call:

```json
{"relative_path":"scripts/evaluate_combinations.py","input_json":{"deposit":8000,"savings_products":[...],"credit_cards":[...],"checking_boosts":[...]}}
```

Before relying on results, verify that every candidate has a documented opening deposit and base/tier APY, that card eligibility has been assessed, and that all listed card/checking bonus mappings are for the same savings account being evaluated. If any of those facts are unavailable, explain the gap rather than presenting a definitive maximum.

## Savings-account opening workflow

Use this workflow only after the customer affirmatively chooses an account and asks to open it.

1. Verify identity and authority using the supported verification process. Confirm at least two identity fields against the customer record, obtain a current timestamp, and log the verification only after successful verification.
2. Confirm eligibility: an active qualifying checking account, required checking-account tenure, fewer than the maximum allowed personal savings accounts, no collections or negative balances, and any product-specific requirements.
3. Confirm the exact full official `account_class` name ending in `Account`, the required opening deposit, paperless/statement requirements, and whether the customer authorizes an immediate transfer.
4. Confirm account ownership, source-account ownership, available balance, applicable fees, withdrawal or transfer limits, timing/cutoffs, and final customer confirmation immediately before any action.
5. Only after all checks pass, use the normal banking account-opening tool with the authenticated customer ID, `account_type` of `savings`, and the confirmed exact account class.
6. Transfer funds only when the customer has explicitly authorized the amount and source account, and only after the new destination account is confirmed. If funding is deferred, provide the documented funding deadline and consequence.
7. Report the confirmed account details and funding status. If a prerequisite is not met, do not open the account; explain the specific blocker and any documented next step.

For a credit-card application, clearly distinguish pre-screening from approval. Confirm the documented minimum score, subscription requirement where applicable, credit-pull consent requirement, fees, and customer consent before directing the customer to the documented application process. Do not treat a preference for a credit check as proof that a card’s credit requirements are met.
