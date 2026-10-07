---
name: savings-card-net-return-advisor
description: Compare a customer's eligible savings-account and credit-card combinations by one-year interest less annual card fees, explain conditional eligibility, and safely progress a selected savings-account opening and funding request. Use for Rho-Bank customers choosing a savings account plus card, especially when card-linked APY bonuses and balance requirements matter.
---

# Savings and Card Net-Return Advisor

Use this Skill to give a transparent, assumption-based comparison before initiating any bank action. It distinguishes a product recommendation from approval or account-opening eligibility.

## What the comparison measures

Calculate only the objective the customer stated:

`one-year net = stated deposit × effective APY − annual credit-card fee − applicable maintenance fees`

Do **not** add cash back, welcome bonuses, investment returns, tax effects, or credit-card interest unless the customer explicitly expands the objective and supplies the needed information. APY is already an annualized yield, so use the stated annual APY rather than independently adding daily compounding again.

Effective APY is:

`base savings APY + highest applicable card APY bonus + highest applicable checking boost + any separately documented additive relationship bonus`

Card bonuses never stack with other card bonuses, and checking boosts never stack with other checking boosts. A qualifying checking boost may stack with the selected card bonus. Do not invent a checking boost merely because a customer has a checking account.

## Required customer and account checks

1. Confirm the customer's stated amount, intended maintained balance, and whether they want one new card or are asking about cards they already hold.
2. Treat account information obtained from profile lookup as identifying information, **not** completion of the savings-opening identity-verification requirement. Before any opening action, obtain and confirm two of the four identity fields (date of birth, email, phone, address), call `get_current_time`, then call `log_verification` with all required fields and the authenticated user ID.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` to check the savings-opening prerequisites:
   - at least one ACTIVE checking account held for at least 14 days;
   - fewer than five personal savings accounts;
   - no account in collections and no negative balance;
   - identity verification completed.
   Do not open an account if any item fails or cannot be established.
4. Re-check current cards using `get_credit_card_accounts_by_user`. Existing cards may change the applicable highest card bonus, but a new-card comparison must not claim the customer already holds the new card.
5. A profile lookup does not provide a credit score in the supplied runtime. Never state that the score was checked or that a card is approved. Where the score is unavailable, label score-gated choices **conditional on underwriting and the published minimum score**. Confirm any other published product prerequisite, such as a premium subscription, from the customer record when available.

## Comparison process

1. Read `references/current_product_facts.md` and extract only combinations whose rate, fee, and required balance are documented.
2. Build a JSON input for `scripts/compare_returns.py`. Include a no-new-card row where useful, the proposed card rows, all known base APYs, documented card bonus rates by savings account, and any documented checking boost. Use `strict_maintenance: true` for a recommendation intended to preserve account benefits for the full year.
3. The script returns ranked supported candidates. It treats unknown credit score as conditional rather than failed, excludes accounts whose opening or ongoing balance requirement is not met in strict mode, and reports excluded rows. Review its assumptions before presenting figures.
4. Explain the top conditional option and the best option that does not require the unavailable credit threshold. State meaningful dollar differences, assumptions (constant balance for a full year, card/savings linked to the same profile, benefit eligibility maintained), opening deposit, ongoing balance requirement, and relevant fees.
5. If rate tiers, an account opening requirement, a boost percentage, or a fee is not documented, do not estimate it. Say it cannot be ranked reliably with the available documentation.

### Current $30,000 scenario guidance

For a customer maintaining $30,000 all year, the documented Gold Plus Account + Gold Rewards Card scenario is conditional on the card's 720 minimum-score/underwriting requirement. It has 6.0% base APY plus the Gold Rewards Card's +0.35% Gold Plus bonus and a $0 card annual fee: 6.35%, or $1,905 over one year under the stated assumptions. The customer must meet Gold Plus's $10,000 opening deposit and $25,000 ongoing balance requirements.

Gold Plus with Crypto-Cash Back is documented at 6.30%, but its $75 annual fee yields $1,815 before any non-annual fees (and it has a 660 score requirement). Gold Plus with EcoCard is 6.10%; after EcoCard's $50 annual fee, it yields $1,780. Gold Plus without a new card yields $1,800. These comparisons exclude rewards on purchases. Light Blue checking is not one of the documented qualifying checking pairings for Gold Plus, so it adds no checking-account APY boost.

Do not present these figures as a promise of approval. If the customer cannot provide a score, offer the Gold Rewards option as conditional and explain that EcoCard has no stated credit-score minimum but has a $50 annual fee. The calculator should be used if the balance, product set, or available card information differs.

## Executing a selected savings-account opening

Only after the prerequisite checks pass and the customer has selected the exact account:

1. Unlock `open_bank_account_4821` and call it with the authenticated user ID, `account_type: "savings"`, and the exact official class name ending in `Account` (for example, `Gold Plus Account`).
2. Ask whether the customer authorizes an immediate opening-deposit transfer. Do not infer authorization from a comparison request or from their intended balance.
3. If authorized, identify the source checking account and confirm it and the new account are ACTIVE or OPEN, distinct, owned by the customer, and that the source has sufficient funds. Confirm a positive USD amount that meets the selected account's documented opening minimum. Unlock and call `transfer_funds_between_bank_accounts_7291`.
4. If the customer declines immediate funding, state that the account must be funded within 30 days through an internal transfer or external deposit or it will close.
5. Confirm the created account and the funding result. If a tool reports an error, do not claim completion or retry without correcting the reported prerequisite.

There is no supplied bank-action tool for submitting a credit-card application. After giving the comparison, direct the customer to the Rho-Bank dashboard application flow and the relevant documented application requirements. Do not fabricate a card application or approval.

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

Validate that money values are nonnegative, APYs and fees are numeric, card bonus keys exactly match product names, and credit thresholds are nonnegative. A normal result has `status: "ok"`, ranked `candidates`, and `excluded`; malformed input has `status: "error"` and an explanatory `errors` array. Candidates show `eligibility` as `eligible` or `conditional_credit_score` rather than converting an unknown score into approval.
