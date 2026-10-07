---
name: savings-card-net-yield-comparison
description: Compare savings-account and credit-card combinations for a stated deposit by estimating one-year savings interest less recurring card fees. Use for informational product comparisons where rates, balance tiers, linked-account boosts, card bonuses, and eligibility constraints are available; it does not open products or take banking actions.
---

# Savings and Card Net-Yield Comparison

Use this Skill to provide a transparent, one-year comparison of eligible savings and credit-card pairings. It treats APY as an annual yield on a constant stated balance and subtracts recurring annual card fees. It is an informational workflow only: do not open accounts, submit a card application, alter customer records, or imply approval.

## Method

1. Extract the customer's proposed deposit, currently held linked products, and goal. Confirm whether the customer expects to keep the stated balance for the full year; otherwise explain that a balance-history calculation is needed.
2. From the supplied product documentation, build the runtime JSON described below. Include only rates and fees that are supported by the documentation.
3. Determine the savings APY tier at the proposed balance. Reject accounts whose opening or ongoing balance requirement exceeds the proposed deposit.
4. Add only bonuses whose conditions are established:
   - For card bonuses, retain only the highest applicable card bonus; do not sum card bonuses.
   - A qualifying checking boost and separately documented relationship or account bonuses may be added only when their requirements are met.
   - Do not invent a boost percentage when the documentation establishes a qualifying pairing but does not give its amount.
   - Do not treat an unrelated checking account as a qualifying linked-account pairing.
5. Run `scripts/compare_net_yield.py` with the assembled JSON. The script returns eligible combinations, their rate components, annual interest estimate, annual card fee, and net one-year estimate.
6. Present the leading result in customer-friendly terms, then summarize the material runner-up(s), assumptions, and application conditions. State monetary values rounded to cents in prose. Explain that card issuance remains subject to the documented application and approval process.

The estimate excludes card purchase rewards, sign-up bonuses, taxes, balance changes, maintenance fees not specified for the scenario, and any fees other than the supplied annual card fee. Do not compare those items unless the customer asks and their conditions and values are documented.

## Script interface

`scripts/compare_net_yield.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "deposit": "positive number",
  "require_card": true,
  "savings_accounts": [
    {
      "id": "stable savings identifier",
      "name": "display name",
      "minimum_opening_deposit": "number, optional",
      "minimum_ongoing_balance": "number, optional",
      "base_apy_percent": "number, or omit when tiers are supplied",
      "apy_tiers": [
        {"minimum_balance": "number", "apy_percent": "number"}
      ],
      "additional_apy_bonuses": [
        {"label": "documented qualified non-card bonus", "apy_percent": "number", "eligible": true}
      ]
    }
  ],
  "cards": [
    {
      "id": "stable card identifier",
      "name": "display name",
      "annual_fee": "number",
      "eligible_to_apply": true,
      "application_conditions": ["documented condition or approval caveat"],
      "bonus_apy_percent_by_savings": {"savings-id": "number"}
    }
  ],
  "checking_boosts": [
    {
      "savings_id": "savings identifier",
      "checking_id": "customer-held checking identifier",
      "label": "documented linked checking boost",
      "apy_percent": "number",
      "eligible": true
    }
  ]
}
```

`eligible_to_apply` may be `true`, `false`, or omitted. Omitted means eligibility is not established and the combination is labelled `conditional`, rather than silently represented as approved. Set `require_card` to `false` only when a savings-only comparison is within scope. `additional_apy_bonuses` and `checking_boosts` must contain only bonuses that the executor has already verified as qualified.

Output includes `results`, ordered by descending `net_one_year_estimate`, then descending APY, and `excluded`. Each result reports all applied components and a `status` of `eligible` or `conditional`. An `errors` array means the input was not evaluated; correct it rather than guessing.

Runnable invocation (with a scenario JSON assembled from current documentation):

```sh
python3 scripts/compare_net_yield.py < scenario.json
```

## Validation before answering

- Verify the proposed deposit satisfies both opening and ongoing requirements used in each result.
- Verify each selected tier threshold and every added APY component against the supplied documentation.
- Verify that no more than one card APY bonus is included for a savings result.
- Verify annual fees are subtracted once per selected prospective card and are not confused with APR, a late fee, or a promotion with unmet conditions.
- Check that all displayed dollar figures equal the script's unrounded calculation rounded to cents.
- If documentation conflicts or lacks a required rate, fee, threshold, or eligibility condition, identify the uncertainty and avoid a definitive best-combination claim.

## Banking control boundary

This Skill normally provides product information only. If a later request changes into an account, card, transfer, payment, profile, or other banking action, first verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements before taking or recommending that action. Do not use this comparison itself as evidence that an account or card has been approved.
