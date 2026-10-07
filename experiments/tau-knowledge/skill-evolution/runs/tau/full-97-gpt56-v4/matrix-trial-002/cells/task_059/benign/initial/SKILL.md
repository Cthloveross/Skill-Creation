---
name: savings-and-credit-card-combination-advisor
description: Evaluate a customer's savings-account and credit-card combination when the goal is to maximize one-year interest, rewards, and fees. Use for product comparisons, eligibility-qualified recommendations, APY-bonus stacking, linked-account boosts, and transparent estimates when eligibility or pricing information is incomplete.
---

# Savings and credit-card combination advisor

Use this Skill to provide a decision-ready, policy-grounded recommendation without claiming to know a customer's credit eligibility, account data, or subscription status unless those facts were actually supplied or retrieved with the appropriate authorized tool.

## Method

1. **Collect the decision inputs.** Identify the savings balance, expected annual card spend and categories, existing linked products, credit-score information, subscription status, invitation status, and stated goal. Treat unknown eligibility facts as unknown; an existing checking account alone does not establish a credit score, underwriting approval, or prequalification.
2. **Eliminate unavailable options.** Apply explicit score, subscription, invitation, minimum-balance, and offer-window requirements. Do not describe an option as available merely because it is attractive.
3. **Determine the savings APY.** Start with the account base APY, then apply only documented bonuses. Credit-card bonuses use the highest eligible card bonus only; they do not add together. Checking-linked boosts also use the highest applicable boost only, and only exact documented checking/savings pairings qualify. Credit-card and checking bonus categories can otherwise be additive where documentation says so.
4. **Treat APY as an effective annual yield.** For a stable balance held for one year, estimate interest as `balance × APY`. Do not compound an APY a second time merely because interest accrues daily. Use the projection helper for repeatable arithmetic.
5. **Estimate card economics.** Estimate annual cash back as annual eligible spending times the applicable earn rate, subtract disclosed annual fees, and separately identify recurring subscription costs or benefits whose price is not supplied. Never count a promotion after its offer window or if the customer's spending cannot meet its condition.
6. **Compare like-for-like, conditionally.** Show a recommended option that is known to be openable, if any, and separate conditional alternatives that require a known score, paid subscription, or a category-spend assumption. If material product terms are missing, say the option cannot be reliably ranked rather than filling in a rate or threshold.
7. **Give a concise next step.** For unknown credit score, explain that eligibility requires the stated requirement and the customer can check their score or proceed only through the bank's supported application/prequalification process. Do not promise an internal eligibility check where no such tool or authorization exists.

## Required response structure

Write a customer-facing response with these sections, adapted to the facts available:

- **Bottom line:** the best known feasible combination, or explain why no card can yet be confirmed.
- **One-year estimate:** state assumptions (stable savings balance, eligible spend range, spending categories, and exclusion of unknown subscription costs). Give interest, estimated rewards, known annual fees, and net total/range.
- **Why other options do or do not win:** distinguish ineligible, conditional, and unrankable choices.
- **Important account-linking rules:** explain only if relevant, including whether the customer's checking account has a documented qualifying pairing.
- **Next step:** identify the one or two facts/actions needed to turn a conditional result into a firm recommendation.

Use currency rounded to cents in prose. State rates as percentages. Cite product names and terms naturally, rather than citing unstated databases or claiming a personal account lookup.

## Current product-reference use

Consult `references/product_rules.md` for the documented terms captured for this product set. Its facts are product rules, not proof that a particular customer is approved. Resolve internally inconsistent arithmetic by using the stated base rate plus the stated bonus (for example, 5.5% plus 0.025% is 5.525%), and flag material source conflicts rather than repeating a mathematically unsupported total.

## Projection helper

`scripts/project_combination.py` accepts JSON on stdin and emits JSON on stdout.

Input schema:

```json
{
  "balance": 5000,
  "annual_spend_low": 1200,
  "annual_spend_high": 2400,
  "savings": {"name": "Savings option", "apy_percent": 2.0, "annual_fee": 0},
  "card": {"name": "Card option", "cashback_percent": 1.0, "annual_fee": 0},
  "other_annual_cost": 0
}
```

- `balance`, spending, and fees must be nonnegative numbers.
- `annual_spend_high` must be at least `annual_spend_low`.
- `apy_percent` and `cashback_percent` must be nonnegative numbers.
- `other_annual_cost` is for a known subscription or other recurring cost; omit it or use zero when none is known. Do not insert an invented price.

The result contains annual interest, reward range, total known costs, and net one-year range. APY is handled as an effective annual yield. Use the helper only after deciding that the supplied rates and fees apply to the scenario; it does not assess eligibility or select a product.

## Validation before responding

Check all of the following:

- A card with an unknown credit-score requirement is not stated to be approved or eligible.
- Required subscription and invitation conditions have been honored.
- Savings minimum-balance exceptions are only used when their qualifying card/product condition is met.
- The customer’s checking account is compared to exact qualifying pairs, not to a similar-looking account name.
- Card APY bonuses have not been stacked, and promotional credits are not included unless both dates and spend requirements work.
- Fee and reward estimates use the same one-year spend assumption and disclose unknown costs.
- No account-opening, credit-pull, or transfer action is represented as already completed.
