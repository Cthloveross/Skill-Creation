---
name: savings-card-net-yield-comparison
description: Compare savings-account and credit-card pairings for a stated deposit to maximize one-year savings interest minus card annual fees and applicable recurring account fees. Use for product-selection conversations before opening products; it handles account-specific APY bonuses, non-stacking card bonuses, linked-checking boosts, minimum-balance fees, and unknown eligibility.
---

# Savings and Card Net-Yield Comparison

Use this Skill when a customer wants to select a savings account and (optionally) a credit card based on the net value of savings earnings over one year.

## Boundaries

- This is a comparison and recommendation workflow, not authority to open an account, apply for a card, transfer money, or represent approval.
- Use only the account, card, pairing, and eligibility terms supplied in the current task knowledge. Do not infer a bonus from a similarly named product or from another savings account's terms.
- Treat APY as an annual yield: for a constant deposit, annual interest is `deposit × effective_APY / 100`. Do not compound APY again.
- Include stated annual card fees and predictable monthly account-maintenance fees. Do not invent fees, rewards value, taxes, variable balances, or investment returns.
- Mark combinations with unmet or unknown eligibility conditions as conditional rather than presenting them as available. A card's approval requirement and a subscription requirement are separate conditions.

## Method

1. Extract the customer's deposit, existing checking account(s), requested time horizon, and objective. Confirm the model assumes the stated deposit remains in savings for the whole year.
2. Build a product table from the supplied knowledge for each relevant savings account:
   - base APY;
   - ongoing minimum balance and the stated monthly fee below it;
   - card-specific APY bonus table;
   - any account-specific benefits or restrictions relevant to the customer.
3. Build a card table containing annual fee, eligibility conditions, and the bonus it provides **to each candidate savings account**. A card bonus table for one savings product must not be reused for another.
4. Determine linked-checking boosts only for explicitly qualifying checking/savings pairings. If the customer's checking account is absent from the published qualifying list, use a zero boost.
5. For each savings/card combination, apply only the highest applicable credit-card bonus. If evaluating one new card at a time this is naturally that card's bonus; if the customer already holds cards, include all active applicable card bonuses and select the maximum. Credit-card bonuses do not stack with one another. A qualifying checking boost may be added to that selected card bonus where policy permits.
6. For each combination calculate:

   ```text
   effective_apy_pct = base_apy_pct + highest_card_bonus_pct + highest_checking_boost_pct + other_explicit_additive_bonus_pct
   gross_interest = deposit × effective_apy_pct / 100
   annual_account_fees = monthly_fee_below_min × 12, if deposit is below the applicable minimum; otherwise 0
   net_one_year_value = gross_interest - card_annual_fee - annual_account_fees
   ```

7. Rank only combinations whose known requirements are met. Separately show higher-ranking conditional options, identifying the exact unknown condition and any fee/minimum-balance drawback. A below-minimum balance does not make an option unavailable unless the source says so; include its stated fee.
8. Give a clear recommendation with the effective APY, gross annual interest, every deducted annual fee, and net one-year value. State why alternatives lose.
9. If the customer decides to proceed with a savings opening, follow the governing savings-opening procedure: verify identity, confirm active checking and required tenure, check the savings-account count and account standing, confirm the full official account class, then use only the authorized opening tool. Ask about an opening-deposit transfer only after the account is opened and the customer authorizes funding. If eligibility or authorization is not established, do not act.

## Use the calculator

Run `scripts/compare_net_yield.py` with JSON on stdin. It is deterministic and performs the arithmetic and ranking; source product facts must be supplied at runtime.

### Input schema

```json
{
  "deposit": 20000,
  "savings_accounts": [
    {
      "name": "official savings account name",
      "base_apy_pct": 0,
      "minimum_balance": 0,
      "monthly_fee_below_min": 0,
      "checking_boosts_pct": {"official checking name": 0},
      "other_additive_bonus_pct": 0,
      "requirements": ["optional known condition"]
    }
  ],
  "cards": [
    {
      "name": "official card name",
      "annual_fee": 0,
      "eligible": true,
      "eligibility_notes": ["known or unresolved condition"],
      "bonuses_pct_by_savings": {"official savings account name": 0}
    }
  ],
  "held_cards": [
    {
      "name": "already held card",
      "eligible": true,
      "bonuses_pct_by_savings": {"official savings account name": 0}
    }
  ],
  "checking_accounts": ["official checking name"],
  "include_no_new_card": true
}
```

`eligible` means known eligibility for purposes of ranking. Set it to `false` if a required score, subscription, approval, or other condition is unknown or not met; the output will retain the combination as conditional. Omit unsupported bonus entries rather than setting a guessed value.

### Output validation

The script emits one JSON object with `valid: true`, a descending `ranked_options` list, and a `best_known_option` (or `null`). Check before using it that:

- `effective_apy_pct` equals the listed base APY plus the selected highest card bonus, checking boost, and explicit additive bonus;
- at most one card bonus is listed in `selected_card_bonus`;
- `annual_account_fees` is twelve times the monthly fee only when the deposit is below the supplied minimum;
- `net_one_year_value` equals gross interest less card annual fee and annual account fees;
- unknown card qualification is described as conditional in the customer-facing response.

If `valid` is false, correct the missing or malformed source values rather than guessing.

## Customer-facing response pattern

State the assumptions, give a compact comparison table, then recommend the highest known-eligible option. For example, use columns: savings account, card, effective APY, annual interest, annual fees, net one-year value, and conditions. Explain non-stacking briefly when relevant. If a potentially better option is conditional, identify the condition and ask the customer to confirm it. Do not claim an account or card was opened unless the required verified workflow and tool result have occurred.
