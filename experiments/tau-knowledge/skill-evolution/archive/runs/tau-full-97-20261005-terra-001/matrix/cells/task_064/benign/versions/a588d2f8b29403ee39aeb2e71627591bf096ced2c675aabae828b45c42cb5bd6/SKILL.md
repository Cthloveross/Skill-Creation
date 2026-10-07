---
name: savings-card-net-return-advisor
description: Compare a customer's documented savings-account and credit-card combinations by one-year interest less annual card fees, explain conditional eligibility and product-use limits, and safely progress a selected savings-account opening and funding request. Use for Rho-Bank customers choosing a savings account plus card, especially when card-linked APY bonuses, balance requirements, or withdrawal frequency matter.
---

# Savings and Card Net-Return Advisor

Use this Skill to give a transparent, document-supported comparison before initiating any bank action. A recommendation is not an approval, an opened account, or authorization to move money.

## What the comparison measures

Calculate only the objective the customer stated:

`one-year net = stated deposit × effective APY − annual credit-card fee − applicable maintenance fees`

Do **not** add cash back, welcome bonuses, investment returns, tax effects, or credit-card interest unless the customer explicitly expands the objective and supplies the necessary information. APY is annualized, so use the stated APY without independently adding daily compounding again.

Effective APY is:

`base savings APY + highest applicable card APY bonus + highest applicable checking boost + separately documented additive relationship bonus`

Card bonuses do not stack with other card bonuses, and checking boosts do not stack with other checking boosts. A qualifying checking boost may stack with the highest card bonus. Never infer a checking boost merely because the customer has a checking account.

## Required customer and account checks

1. Confirm the stated deposit, intended maintained balance, and whether the customer seeks one new card or comparison of cards already held.
2. Treat profile lookup as identifying information, **not** completion of the savings-opening identity-verification requirement. Before an opening action, confirm two of the four identity fields (date of birth, email, phone, address), obtain the current time, then call `log_verification` with the required fields and authenticated user ID.
3. Before opening a savings account, use `get_all_user_accounts_by_user_id_3847` to establish all opening prerequisites: an ACTIVE checking account held at least 14 days, fewer than five personal savings accounts, no collections or negative balances, and completed identity verification. Do not open an account if any prerequisite fails or cannot be established.
4. Use `get_credit_card_accounts_by_user` when existing cards could affect the highest applicable card bonus. A proposed new card must not be described as already held.
5. A profile lookup does not supply a credit score. Never claim the score was checked, that a card is approved, or that eligibility is confirmed. If a score is unavailable, label score-gated choices as **conditional on underwriting and the published minimum score**. Verify any separately documented prerequisite, such as Rho-Bank+ subscription, from the customer record when available.

## Comparison process

1. Read `references/current_product_facts.md`. Use only combinations for which rates, fees, requirements, and relevant bonuses are documented.
2. Build input for `scripts/compare_returns.py`. Include supported savings products, proposed cards, documented APYs and fees, and a checking boost only when its amount is documented and the pairing qualifies. Use `strict_maintenance: true` when assessing a full-year recommendation intended to preserve benefits.
3. Review calculator output and exclusions. Unknown credit score makes a score-gated option conditional; it does not prove approval or denial. Do not rank products whose rate tier, balance requirement, fee, or bonus cannot be determined from the documents.
4. Present the top supported option, its assumptions, its meaningful dollar advantage, and any best non-score-gated alternative. State opening deposit, ongoing minimum, card fee, maintained-balance assumption, and that products must be linked under the same profile for a documented card bonus.
5. Clearly distinguish a documented result from a promise. If a required fact is missing, say it cannot be ranked reliably rather than estimating it.

### Documented $30,000 comparison

For a constant $30,000 balance maintained for one year, the documented leading combination is **Gold Plus Account + Gold Rewards Card**, conditional on the Gold Rewards Card's published 720 minimum score and underwriting. Gold Plus has a 6.0% base APY and Gold Rewards supplies a +0.35% Gold Plus bonus. With its $0 annual fee, the result is 6.35% and $1,905 annual interest minus card fee under the constant-balance assumption.

Gold Plus requires a $10,000 opening deposit and a $25,000 ongoing balance to maintain benefits. The customer's Light Blue checking account is not a documented qualifying checking pairing for Gold Plus, so do not add a checking APY boost.

Do not present this as approval. If the score is unavailable, state that the Gold Rewards path remains conditional on the 720 minimum and underwriting. EcoCard has no stated credit-score minimum but a $50 annual fee. Gold Plus with Crypto-Cash Back is documented at 6.30% with a $75 annual fee; Gold Plus with EcoCard is documented at 6.10% with a $50 annual fee. These figures exclude purchase rewards and should be recalculated if the balance, products, or existing cards differ.

## Withdrawal-frequency and suitability follow-ups

When the customer asks whether anticipated withdrawals fit a recommended savings account, consult that account's documented specifications before saying a limit is unavailable or escalating.

- **Gold Plus Account has a documented monthly withdrawal limit of 25 withdrawals.**
- For an expected **10–12 withdrawals per month**, explicitly state that Gold Plus permits up to 25 and that 10–12 is within that documented limit, so the stated frequency fits the limit.
- Apply the limit numerically: compare the customer's expected range with the account's monthly maximum. Do not merely recite the product fact.
- Distinguish the documented count limit from fees or transaction classifications not documented. Do not invent excess-withdrawal fees, exclusions, or a different counting method.
- This suitability answer alone is informational. It does not select an account, open one, apply for a card, or authorize a deposit transfer.

## Executing a selected savings-account opening

Only after all opening prerequisites pass and the customer selects the exact savings account:

1. Unlock and call `open_bank_account_4821` with the authenticated user ID, `account_type: "savings"`, and the exact official account class ending in `Account`, such as `Gold Plus Account`.
2. After the account has opened, ask whether the customer authorizes an immediate opening-deposit transfer. Do not infer transfer authorization from a comparison request, intended balance, or account-selection statement.
3. Only after authorization, identify the source checking account and confirm that source and the new savings account are ACTIVE or OPEN, distinct, owned by the customer, and that the source has sufficient funds. Confirm a positive USD amount that meets the opening minimum, then unlock and call `transfer_funds_between_bank_accounts_7291`.
4. If the customer declines immediate funding, explain that the account must be funded within 30 days by internal transfer or external deposit or it will close.
5. Confirm only actions that the relevant tool successfully completed. On tool error, do not claim completion or retry until the reported problem is resolved.

There is no supplied bank-action tool for submitting a credit-card application. Direct a customer who wants to apply to the documented Rho-Bank dashboard application flow; do not fabricate an application or approval.

## Calculator interface

Run:

```text
python scripts/compare_returns.py < input.json
```

The script receives one JSON object on stdin and emits one JSON object on stdout.

Required fields:

```json
{
  "deposit_amount": 30000,
  "savings_products": [{"name":"...", "base_apy":6.0, "opening_deposit":10000, "minimum_balance":25000}],
  "cards": [{"name":"...", "annual_fee":0, "minimum_credit_score":720, "apy_bonuses":{"...":0.35}}]
}
```

Optional fields are `credit_score` (number or `null`), `checking_boosts` (object keyed by savings name), `other_additive_bonuses` (object keyed by savings name), `strict_maintenance` (default `true`), and `include_no_card` (default `true`). A savings product may include `monthly_maintenance_fee_below_minimum` for non-strict estimates.

Validate that money values are nonnegative, APYs and fees are numeric, bonus keys exactly match savings-product names, and credit thresholds are nonnegative. A valid result has `status: "ok"`, ranked `candidates`, and `excluded`; malformed input has `status: "error"` with an `errors` array. Treat `conditional_credit_score` as a comparison condition, never an approval.
