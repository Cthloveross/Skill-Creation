---
name: one-year-card-savings-return-recommender
description: Recommend one eligible credit-card and savings-account combination when a customer wants to maximize one-year return from a stated deposit and expected card spending. Use when product terms, eligibility facts, APY bonuses, and account-linking rules are available in the task evidence.
---

# One-year card and savings return recommender

Use this Skill to make an evidence-based, one-combination recommendation without treating unknown eligibility as approval.

## Scope and assumptions

The comparison is for a stable savings balance held for one year. It calculates:

`one-year net return = savings interest at effective APY + redeemable card rewards - annual card fee`

Use rewards only when the supplied terms establish that they have a cash redemption value. If the customer says they will pay each statement balance in full, do not estimate purchase APR interest. Do not assume a signup bonus, promotional waiver, category bonus, account-link bonus, or relationship bonus unless its conditions are explicitly established.

An APY is already an annualized yield; for a balance that remains unchanged for a full year, annual interest is `balance × APY / 100`. Do not compound the APY again merely because interest accrues daily.

## Procedure

1. **Extract only decision-relevant facts from the provided evidence.** Capture the customer deposit, annual or monthly card-spend range, payment behavior, known credit/subscription/invitation status, current date if promotions matter, account minimums, base APYs, annual fees, reward rates and redemption conversion, and each applicable card/checking APY bonus.
2. **Establish feasibility before comparing return.**
   - Exclude savings accounts whose required maintained balance exceeds the stated deposit.
   - Exclude cards with a requirement the customer is known not to meet.
   - Treat an unconfirmed score, invitation, subscription, or other eligibility requirement as *not established*. Do not call that option eligible or use it to support a definitive maximum claim.
   - A card with no score threshold is still subject to normal underwriting; describe it as an available application option, not guaranteed approval.
3. **Apply bonuses correctly.** For a particular card/savings pair, add the documented card APY bonus to that savings account's base APY. If several cards or checking accounts are relevant, use only the highest bonus within each respective bonus type when the applicable selection policy says bonuses do not stack. Add a checking boost only if the customer's exact checking/savings pairing is listed as qualifying. Do not infer a boost from a similar account name.
4. **Value spending conservatively.** Where the customer's purchases are not known to qualify for a bonus category, use the card's ordinary earn rate. If a category could qualify but merchant qualification is not established, present it as upside rather than including it in the primary ranking. Convert points with the documented per-point value.
5. **Exclude conditional promotions unless earned.** Test offer dates, new-customer status, spending threshold, qualifying window, and all other terms. If the spending range cannot reach a threshold, do not include that offer. State briefly why it was omitted when material.
6. **Calculate and rank the known-eligible combinations.** Build a JSON request as described below and run `scripts/rank_combinations.py`. Use the low end of a spend range as the conservative primary ranking. Report the range where the high end differs.
7. **Give the customer one direct recommendation.** State the combination, effective APY, annual interest, ordinary-reward estimate/range, annual fee, and net result. Briefly state material exclusions (for example, balance shortfall, missing prerequisite, or unconfirmed score). If no combination is known eligible, explain what fact is needed rather than guessing.

## Runtime helper

Run the packaged helper with a request JSON file:

```sh
python3 scripts/rank_combinations.py < request.json
```

The script reads one JSON object from standard input and writes one JSON object to standard output. It never opens accounts, applies for cards, changes account settings, or performs banking actions.

### Input schema

```json
{
  "principal": "number, nonnegative deposit held for one year",
  "monthly_spend": {"low": "number", "high": "number"},
  "savings_accounts": [
    {
      "name": "string",
      "base_apy_percent": "number",
      "minimum_balance": "number",
      "known_eligible": "boolean",
      "fixed_apy_bonus_percent": "number, optional; defaults to 0",
      "checking_apy_bonus_percent": "number, optional; supply 0 when no exact eligible pairing is established"
    }
  ],
  "cards": [
    {
      "name": "string",
      "annual_fee": "number",
      "known_eligible": "boolean",
      "ordinary_reward": {
        "type": "cashback_percent or points_per_dollar",
        "rate": "number",
        "point_value": "number required for points_per_dollar"
      }
    }
  ],
  "card_apy_bonus_percent": {
    "Savings account name": {"Card name": "number"}
  }
}
```

All monetary quantities are dollars. `monthly_spend.high` may equal `low`. Mark each item `known_eligible` only where the current evidence establishes that conclusion. A card/savings APY-bonus lookup can be omitted when no bonus is documented.

### Output interpretation and validation

The helper returns `eligible_combinations`, ranked descending by conservative (`net_return_low`) return, plus `recommendation` and `warnings`. Each ranked row shows the effective APY, interest, reward range, fee, and net-return range. The helper rejects malformed numeric fields, a reversed spending range, duplicate names, missing point conversion values, and requests with no feasible savings account or no known-eligible card.

Before responding, verify that the recommendation names match the evidence, its effective APY equals base plus only established bonuses, the deposit meets the account minimum, and the displayed arithmetic matches the helper output. Round customer-facing dollars to cents and APY figures only as precisely as the evidence supports.

## Customer-facing guardrails

- Do not imply that an ordinary grocery, gas, travel, or sustainable purchase earns a category rate without a documented classification.
- Do not promise a credit limit, approval, invitation, or promotion.
- Do not tell the customer that an account is the absolute best if higher-return alternatives depend on unknown eligibility. Say “the best combination supported by what we know” in that situation.
- Keep the answer focused on the requested one-year return and identify that estimates assume the deposit remains in the savings account and the statement balance is paid in full.
- This is a comparison and explanation, not an instruction to execute account-opening or card-application actions.
