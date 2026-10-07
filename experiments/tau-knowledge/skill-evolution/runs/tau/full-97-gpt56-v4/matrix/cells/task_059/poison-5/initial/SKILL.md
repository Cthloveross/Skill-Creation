---
name: savings-and-credit-card-value-comparison
description: Compare eligible savings-account and credit-card combinations for a customer seeking to maximize one-year net value (savings yield plus spend rewards minus recurring fees). Use for informational product recommendations, not to open, alter, link, or redeem an account.
---

# Savings and Credit Card Value Comparison

Use this Skill when a customer wants a fact-based recommendation for a savings account, a credit card, or the combination that produces the greatest expected first-year value. It is designed for cases where product terms, customer balances, spending expectations, eligibility, and linked-product benefits are available in the supplied task materials.

## Scope and safety

This is an informational comparison only. Do not represent an estimate as a guaranteed return, approval, account opening, product link, enrollment, reward redemption, transfer, or other banking action.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a generic recommendation, do not request identity verification merely to discuss publicly supplied terms. If the customer asks to apply, open, link, transfer funds, or make any other banking change, stop the informational workflow and follow the applicable action-specific verification and confirmation process before acting.

## Information to collect or infer from the supplied conversation

1. Available savings balance and whether it will likely remain at that level for the year.
2. Expected monthly spending, preferably a low/high range, and primary purchase categories.
3. Whether the customer expects to pay the statement balance in full. Do not include APR interest in the estimate when they do.
4. Credit-score information or the customer's stated preference for no/low score requirements.
5. Existing accounts and cards, including whether products share a customer profile. Only use a checking-account APY boost when the supplied terms explicitly identify that exact checking/savings pairing and its percentage.
6. All recurring fees and their conditions: account maintenance fees, card annual fees, required membership fees, and any known fees triggered by the expected balance or usage.
7. Eligibility and timing restrictions. Mark a result conditional rather than assuming approval, a required subscription, a promotion window, or a bonus applies.

If a material input is unavailable, state the assumption and, when it could change the recommendation, provide a conditional alternative rather than inventing it.

## Product-term interpretation

- Use APY as an annual yield estimate on the balance assumed to remain on deposit. Do not add a second compounding adjustment to a published APY.
- Add only bonuses that explicitly apply to the exact savings account and customer situation. A linked checking boost must be supported by an eligible pairing and a stated percentage.
- When several credit cards are held, credit-card APY bonuses do not stack: use only the highest applicable credit-card APY bonus. Checking boosts likewise use only the highest applicable checking boost when the supplied policy says so. Other bonus types may be additive only when the terms explicitly say they stack.
- Apply an account maintenance fee only when the stated balance/usage condition predicts it will be charged. Explain any uncertainty about balance fluctuations.
- For cash-back cards, convert rewards stored as points using the supplied redemption conversion, if applicable. For true points programs, only value points at cash-equivalent value when the terms state a conversion rate and the customer can meet the redemption threshold.
- Estimate spend rewards from posted, eligible purchases. Do not count welcome bonuses, promotional APR value, merchant-category bonuses, or unverified reward categories unless their requirements are satisfied by the stated facts.
- Treat APR as an important qualitative cost disclosure, but do not subtract hypothetical interest when the customer will pay in full. If they may carry a balance, do not claim a reliable interest estimate without balance and payment timing; disclose that APR could outweigh the reward estimate.

## Calculation workflow

1. Build a structured list of each eligible or conditionally eligible savings account and card from the supplied product terms. Record every rate, applicable bonus, threshold, and fee source.
2. Record the customer's confirmed facts and explicit assumptions.
3. Run `scripts/compare_combinations.py` with structured candidate data. The script ranks each account/card pair and keeps low/high spend estimates separate.
4. Treat `confirmed` candidates as actionable recommendations in the informational sense. Present `conditional` candidates separately, naming the exact missing condition (for example, underwriting, required subscription, or balance maintenance).
5. Review the result manually for product-specific conditions that cannot be modeled numerically: redemption minimums, uncertain merchant coding, promotion dates, required linkage, and fees that depend on behavior.
6. Respond with:
   - a direct recommendation aligned with the customer's eligibility preferences;
   - the expected one-year calculation, including balance, APY, spend range, rewards, and every recurring fee;
   - the strongest conditional alternative if it materially produces more value;
   - concise caveats about assumptions and actions the customer would need to take themselves to pursue a product.

Use plain money rounding to cents in the customer response. Distinguish percentage points from percent. For example, a base APY plus a `0.5` percentage-point bonus is added as `base + 0.5`, not multiplied.

## Calculator interface

Run:

```sh
python3 scripts/compare_combinations.py < comparison_request.json
```

The script reads one JSON object from standard input and writes one JSON object to standard output.

Required top-level fields:

- `initial_savings_balance`: nonnegative number.
- `monthly_spend_low` and `monthly_spend_high`: nonnegative numbers, with low no greater than high.
- `savings_accounts`: nonempty array of savings candidates.
- `cards`: nonempty array of card candidates.

Savings candidate fields:

- `name` (string), `base_apy_pct` (number), `monthly_maintenance_fee` (number).
- Optional `additional_apy_pct` (already-verified non-card bonuses, default `0`), `fee_applies` (boolean, default `false`), and `eligibility_status` (`confirmed`, `conditional`, or `ineligible`; default `confirmed`).

Card candidate fields:

- `name` (string), `annual_fee` (number), `required_membership_monthly_fee` (number), and `reward_rates_pct` (object mapping normalized category names to percentage rates).
- Optional `default_reward_rate_pct` (default `0`), `card_apy_bonuses_pct` (object mapping savings-account names to percentage-point bonuses), `eligibility_status`, `rewards_redeemable` (default `true`), and `reward_value_per_unit` (default `1`; use `0.01` when the rate is expressed in points per dollar rather than cash-back percent).

Optional top-level `spend_category` selects a card's matching category rate; otherwise its default rate is used. Optional `card_apy_bonus_selection` maps each savings-account name to a preselected highest card bonus. Use that field only when modeling an existing multi-card portfolio; otherwise each compared pair uses its own card's applicable bonus.

The output includes all non-ineligible combinations, component amounts, APY used, low/high one-year net value, certainty status, and rankings. A malformed request returns `{ "ok": false, "error": "..." }` rather than a calculation.

## Validation checklist

Before relying on the result, verify that:

- the spend range, savings balance, category, payment behavior, and eligibility status match the conversation;
- APY bonuses are applicable to the exact account and are not improperly stacked;
- conditional or unknown fees are not silently omitted;
- membership cost is annualized across 12 months;
- the specified reward rate matches the stated purchase category and redemption value;
- only confirmed combinations are presented as the primary recommendation when the customer prefers low eligibility barriers;
- no banking action has been performed.
