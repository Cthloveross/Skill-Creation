---
name: savings-card-net-yield-advisor
description: Compare a customer's documented savings-account and credit-card combinations when the goal is one-year net yield (savings interest less annual fees). Use for read-only recommendations, conditional eligibility analysis, APY-bonus stacking, withdrawal-limit checks, and—only when separately requested—safe preparation for opening a personal savings account.
---

# Savings and Card Net-Yield Advisor

Use this Skill when a customer wants to choose a savings account and optional credit card based on projected savings earnings, annual fees, APY bonuses, balance requirements, and access needs. It provides a recommendation; it does not itself open an account, apply for a card, transfer funds, or alter customer data.

## Inputs to collect and verify

Use the current task's supplied product documents and read-only observations. Extract only facts supported by those materials:

- Planned opening balance, expected maintained balance, and evaluation period.
- Expected withdrawal count per month and whether withdrawals change the modeled balance.
- Savings account base APY, tier threshold, opening and ongoing minimums, withdrawal limit, account fees, compounding/crediting schedule, and relevant relationship benefits.
- For each credit card being compared: annual fee, qualifying requirements, card-specific APY bonus for the savings account, and any offer window.
- Existing eligible cards and checking accounts under the same customer profile.
- Any known eligibility facts and every unknown prerequisite.

Do not treat a customer name, email lookup, or a stated account as completed identity verification. Never infer an unknown credit score, account tenure, balance, product linkage, card status, or waiver eligibility.

## Analysis procedure

1. **State the scope.** Confirm that the comparison is limited to interest earned minus annual fees. Exclude cash-back, sign-up bonuses, transaction fees, and maintenance/excess-withdrawal fees unless enough customer-specific facts establish their amount and applicability.
2. **Screen savings accounts.** Exclude or clearly mark an account as not currently suitable when the planned opening amount is below its opening minimum, the maintained balance is below its ongoing minimum, or the expected withdrawal count exceeds a documented cap. Interpret a documented limit of `-1` as unlimited only when the source explicitly defines it that way.
3. **Determine APY components.** Start with the applicable balance-tier base APY. Add only documented bonuses for which the customer is known to qualify. Card bonuses apply only when the card and savings account are active under the same customer profile.
4. **Apply non-stacking rules.** When multiple eligible credit cards provide a bonus to the same savings account, use the highest applicable card bonus only—not their sum. Likewise, use only the highest applicable linked-checking boost if multiple checking boosts are documented. Add distinct relationship or account-tier bonuses only when documentation says they stack.
5. **Treat uncertainty honestly.** Make a recommendation conditional when a material requirement is unknown (for example, a credit-score minimum). Do not report a conditional bonus as guaranteed. Assess card eligibility separately from savings-opening eligibility.
6. **Calculate comparable net yield.** Supply the selected, supported combinations to `scripts/compare_net_yield.py`. The script uses APY as an effective annual yield and models daily compounding over the requested period. It subtracts explicitly supplied annual fees proportionally to the modeled months. Review the script's exclusions and warnings.
7. **Explain the result.** Present the winning eligible combination, its effective APY, projected gross interest, known annual fees, and projected net result. Also present a practical fallback when the leading result is conditional or unavailable. Include meaningful dollar differences between close alternatives.
8. **Address access needs.** Explicitly compare the customer's expected monthly withdrawals with each selected account's documented monthly limit. If bills are replenished and the balance stays near the modeled amount, state that this is the calculation assumption.
9. **Give next steps without acting.** Identify remaining requirements and, if the customer asks to proceed, obtain explicit selection and authorization before any account-opening or funding operation. Do not apply for a credit card on the customer's behalf unless a supplied, authorized workflow expressly permits it.

### Calculation conventions

- APY is treated as the stated annual effective yield. For `d` modeled days, the balance growth factor is `(1 + APY / 100)^(d / 365)`.
- A full 12-month period therefore produces gross interest equal to principal times the effective APY, subject to currency rounding.
- The estimate assumes a stable eligible balance. If cash flows materially change the balance, do not use a single stable-balance estimate; obtain a dated balance schedule or label the estimate insufficient.
- Annual fees are subtracted only if documented and not known to be waived. Do not assume promotional conditions have been met.
- A no-fee card can still be ineligible; a card with an unknown annual fee should not be ranked as a confirmed net-yield option.

## Script interface

Run `scripts/compare_net_yield.py` with one JSON object on stdin. It emits one JSON object on stdout.

Input schema:

```json
{
  "balance": 0,
  "months": 12,
  "withdrawals_per_month": 0,
  "options": [
    {
      "savings_name": "official savings account name",
      "base_apy_pct": 0,
      "opening_minimum": 0,
      "ongoing_minimum": 0,
      "withdrawal_limit": null,
      "checking_boost_pct": 0,
      "relationship_bonus_pct": 0,
      "savings_annual_fee": 0,
      "savings_eligibility": "eligible",
      "cards": [
        {
          "card_name": "official card name or no-card option",
          "bonus_apy_pct": 0,
          "annual_fee": 0,
          "eligibility": "eligible"
        }
      ]
    }
  ]
}
```

All monetary amounts and percentages must be JSON numbers. `withdrawal_limit` may be `null` only where the documentation does not state a limit; the output then warns that access suitability cannot be confirmed. `eligibility` and `savings_eligibility` must be `eligible`, `conditional`, `unknown`, or `ineligible`. A card list may contain a no-card option with `bonus_apy_pct: 0` and `annual_fee: 0`.

Output schema:

```json
{
  "assumptions": ["..."],
  "results": [
    {
      "savings_name": "...",
      "card_name": "...",
      "status": "eligible|conditional|ineligible",
      "effective_apy_pct": 0,
      "gross_interest": 0,
      "annual_fees": 0,
      "net_earnings": 0,
      "warnings": ["..."]
    }
  ],
  "best_eligible": {},
  "best_conditional": {}
}
```

Validate that all selected products have official names, each amount is nonnegative, annual fees are not silently omitted, and the selected result's status matches the documented facts. The script rejects malformed numeric input and unsupported eligibility labels. It will not invent eligibility or undocumented boosts.

## Savings-opening procedure (only after a separate request to open)

Before describing or performing any banking action, preserve and satisfy this control verbatim:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a personal savings opening, additionally confirm all documented prerequisites before acting: verified customer identity, at least one active checking account, fewer than five personal savings accounts, no collections or negative balances, and checking-account tenure of at least 14 days. Confirm the exact official savings `account_class` selected by the customer.

Only after those checks and explicit customer confirmation may the execution agent use its normal banking tools to open the savings account. If the customer then explicitly authorizes immediate funding, verify the source checking account, ownership, available balance, amount, fees, limits, cutoff, destination account, and transfer confirmation requirements before using the normal transfer tool. If funding is deferred, communicate the documented funding deadline and closure consequence rather than moving funds. Stop and explain the unmet condition if any prerequisite cannot be verified.
