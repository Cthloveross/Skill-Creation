---
name: savings-card-net-yield-recommendation
description: Recommend a savings-account and credit-card combination when a customer wants to maximize one-year savings interest minus annual card fees. Use for informational product comparisons; do not use it to open accounts, apply for cards, transfer funds, or make other banking changes.
---

# Savings and Card Net-Yield Recommendation

Use this Skill to make a transparent, constraint-aware product recommendation. It compares published APYs, applicable card APY bonuses, annual fees, balance requirements, withdrawal limits, and stated eligibility requirements.

## Scope and safety

This is an informational comparison only. Do **not** apply for a card, open an account, move funds, change profile data, or imply that approval is guaranteed.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

If a later request changes from advice to an action, stop the comparison workflow and follow the applicable authorized banking procedure. Obtain the required verification and explicit confirmation before any irreversible action.

## Inputs to collect

Use only supplied product documentation and read-only customer observations. Capture:

- Savings balance intended to remain on deposit for the year.
- Expected monthly withdrawal count.
- Existing checking accounts and cards, only where documentation establishes a relevant boost.
- Customer eligibility preferences or constraints, especially whether the customer does not want a recommendation contingent on a credit-score threshold.
- Savings-account base APY, minimum opening deposit, ongoing minimum balance, and withdrawal limit.
- Each candidate card's annual fee, stated credit-score requirement, and the APY bonus for the specific savings account.
- Any published stacking/selection rule for bonuses.

Do not treat missing facts as satisfied. State unknowns and exclude a candidate when a mandatory customer constraint cannot be confirmed.

## Method

1. Identify feasible savings accounts.
   - Exclude accounts whose opening or ongoing minimum exceeds the stated balance.
   - Exclude accounts whose withdrawal allowance is below the expected monthly withdrawals.
   - Mention a fee that can apply below a minimum, even if the stated balance currently clears it.
2. Identify feasible cards.
   - Exclude a card if its stated eligibility conflicts with the customer's expressed preference (for example, the customer requests no credit-score-dependent recommendation and the card requires a score threshold).
   - Do not invent approval criteria from the absence of a stated requirement.
3. For every feasible account/card pair, find the documented card APY bonus for that account type.
   - If a card bonus is not documented for the selected savings account, do not assume a bonus.
   - If more than one card is held, apply only the highest card bonus when the policy says card bonuses do not stack.
   - Add card bonuses to the base APY only when the product documentation says they are additive. Handle checking-account boosts separately; include one only if the customer holds a documented qualifying checking/savings pairing and its percentage is known.
4. Calculate an estimated one-year comparison using the APY supplied in the documentation:

   `estimated_interest = balance × (effective_apy_percent / 100)`

   `net_one_year_value = estimated_interest − annual_card_fee − known_account_fees`

   This is an APY-based estimate, not a promise of exact daily-balance interest. Do not subtract a conditional maintenance fee when the stated balance is at or above the stated requirement; clearly disclose the condition.
5. Select the highest net result. If results tie, recommend the option with the more favorable stated operational fit (lower minimum balance, greater withdrawal flexibility, or fewer restrictive conditions), and disclose that it ties financially.
6. Give a concise customer-facing explanation: recommendation, effective APY, interest estimate, annual fee, net estimate, withdrawal fit, eligibility caveat, and a brief runner-up/tie comparison.

## Deterministic helper

Use `scripts/compare_options.py` for arithmetic, feasibility filtering, and ranking. It receives JSON on stdin and emits JSON on stdout.

### Input schema

```json
{
  "balance": 30000,
  "monthly_withdrawals": 12,
  "avoid_credit_score_requirement": true,
  "options": [
    {
      "savings_account": "Official Account Name",
      "card": "Official Card Name",
      "base_apy_percent": 0,
      "card_apy_bonus_percent": 0,
      "annual_card_fee": 0,
      "opening_deposit_minimum": 0,
      "ongoing_minimum_balance": 0,
      "monthly_withdrawal_limit": 0,
      "credit_score_required": false,
      "notes": ["optional documented caveat"]
    }
  ]
}
```

All monetary values are dollars and all APY values are percentage points (for example, `5.5`, not `0.055`). Use `null` for an unknown numeric fact. Include only values supported by current task documentation.

### Output schema

The helper returns `ranked_options`, `feasible_options`, and `ineligible_options`. Each ranked item includes effective APY, estimated interest, annual fee, net one-year value, feasibility, and reasons. Monetary results are rounded to cents only for presentation.

### Runnable call example

```sh
python3 scripts/compare_options.py <<'JSON'
{"balance":30000,"monthly_withdrawals":12,"avoid_credit_score_requirement":true,"options":[{"savings_account":"Example Savings Account","card":"Example Card","base_apy_percent":5.5,"card_apy_bonus_percent":0.6,"annual_card_fee":50,"opening_deposit_minimum":10000,"ongoing_minimum_balance":10000,"monthly_withdrawal_limit":20,"credit_score_required":false}]}
JSON
```

The example is illustrative only; replace every product and value with documented runtime inputs.

## Validation before responding

- Ensure the recommended option is feasible for the supplied balance and withdrawal count.
- Check that APY is added in percentage points and that annual fees are subtracted once, not converted into an APY.
- Confirm each bonus belongs to the selected savings-account type.
- Confirm no prohibited eligibility condition was used to recommend a product.
- If two options have the same rounded net result, compare unrounded values first; identify an exact tie rather than claiming a false winner.
- Never claim a checking boost unless both the qualifying pairing and its boost amount are documented.
- Use “estimated” for all calculated annual earnings and do not overstate account-opening or approval status.

## Handling insufficient information

If the balance, withdrawal need, relevant account-specific bonus, annual fee, or eligibility constraint is missing, explain exactly what is needed to complete a reliable comparison. You may provide a conditional comparison, but label it as conditional and do not claim it is the best option.
