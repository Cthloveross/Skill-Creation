---
name: savings-card-yield-planner
version: 1.0.0
description: Recommend a documented savings-account and credit-card combination for a stated deposit and credit profile, calculate one-year APY earnings correctly, explain stacking and eligibility, and safely proceed with a personal-savings opening workflow only after all banking prerequisites and customer authorization are confirmed.
---

# Savings and Card Yield Planner

Use this Skill when a customer wants to compare savings accounts, associated credit-card APY benefits, linked-checking boosts, or expected one-year earnings. It is appropriate for advice alone and for the subsequent opening of a personal savings account. It does not approve or open credit cards unless an authorized card-application workflow/tool is explicitly available.

## Safety and banking controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Treat a comparison or explanation as advisory, not as authorization to open, link, fund, or transfer. Never infer authorization from a stated balance or a request for recommendations.

For a savings-opening action, confirm all of the following before calling a banking tool:

1. The customer is authenticated and identity verification is current.
2. The customer has at least one active Rho-Bank checking account that has been open for at least 14 days.
3. The customer has fewer than five personal savings accounts.
4. No account is in collections or has a negative balance.
5. The selected savings account and its exact official `account_class` name ending in `Account` are confirmed.
6. The customer explicitly authorizes opening the account.
7. Before an internal opening-deposit transfer, the source checking account, customer ownership, available balance, required amount, destination account, fees, limits, and explicit transfer authorization are confirmed.

If any prerequisite is unknown or fails, do not open or fund the account. Explain the missing condition or the reason the customer is not eligible.

## Inputs and source-of-truth handling

Use the current request, verified account records, and current product documentation. The bundled `references/rho_product_catalog.json` is a structured planning aid derived from the supplied product material; update the runtime input if a current disclosure differs. Do not treat an undocumented feature, an illustrative total, or a missing value as a confirmed benefit.

Collect or confirm:

- Deposit amount intended to remain in savings for the year.
- Credit score or a conservative score range, plus any card preferences such as a documented credit check.
- Existing eligible cards and checking accounts, if they affect the calculation.
- Savings account opening and maintenance minimums, fees, account-tier thresholds, and statement requirements.
- Card minimum-score, subscription, annual-fee, credit-check, and same-profile/linking requirements.
- Whether a qualifying linked checking pairing exists and its specific boost amount.

A card with no stated minimum score must not be described as a no-credit-check card or as a credit-check card unless the relevant documentation explicitly says so. When a customer requires a credit check, select only cards whose credit-check requirement is documented, or state that the requirement cannot be established from the available material.

## Calculation method

1. Build only feasible alternatives: the deposit must meet the account opening requirement and any required minimum balance for the proposed strategy. Flag, rather than conceal, recurring fees or qualification risk.
2. Choose the balance-tier APY corresponding to the planned maintained balance.
3. Add the highest applicable credit-card APY bonus only. Credit-card bonuses never stack with one another.
4. Add the highest applicable linked-checking boost only. Checking boosts never stack with one another. A boost applies only to a documented checking–savings pairing; do not assume that any checking account qualifies.
5. Add separately documented relationship, direct-deposit, or tier bonuses only if the customer is actually eligible. State each assumption.
6. Calculate expected annual interest as `maintained_balance × effective_apy / 100`. APY already reflects compounding; do not compound an APY again.
7. For a net comparison, subtract known annual card fees and expected account fees. Do not invent fees where the documents do not provide them.
8. Explain that daily compounding and monthly crediting affect posting and balance fluctuations, but a stable-balance one-year APY estimate is appropriately calculated from APY.

Use `scripts/plan_yield.py` for deterministic ranking. It accepts a normalized product catalog and emits all feasible combinations, assumptions, and rejection reasons. The executor must review the returned assumptions before presenting an answer.

### Script input/output schema

Run `scripts/plan_yield.py` with one JSON object on stdin:

```json
{
  "deposit": 0,
  "credit_score": 0,
  "requires_documented_credit_check": true,
  "checking_boosts": {"Savings Account Name": 0},
  "accounts": [],
  "cards": [],
  "existing_card_names": []
}
```

- `deposit` and all monetary amounts are nonnegative numbers.
- Each account supplies `name`, `base_apy` or `apy_tiers`, `min_opening_deposit`, `ongoing_min_balance`, optional `annual_account_cost`, and `card_apy_bonuses` keyed by card name.
- An `apy_tiers` entry has `min_balance` and `apy`; the highest qualifying tier is used.
- Each card supplies `name`, optional `min_credit_score`, `credit_check_required`, optional `annual_fee`, optional `subscription_required`, and optional `available`.
- `checking_boosts` must already reflect only verified, qualifying pairings; use `0` if none qualifies.
- `existing_card_names` lists active eligible cards already held. Existing cards are considered for the highest card bonus, but their historical fees are not charged again as part of a new-choice comparison.

The script emits either `{ "ok": true, "recommendations": [...], "rejections": [...], "assumptions": [...] }` or `{ "ok": false, "errors": [...] }`. Recommendation entries include the effective APY, estimated annual interest, known annual costs, and estimated net annual earnings. A nonempty `rejections` list is expected when products do not meet the deposit, score, documented-credit-check, or availability conditions.

## Rho-Bank interpretation notes

For the bundled Rho-Bank catalog, apply these facts only when they remain current and the relevant products are held under the same profile:

- Green Account (savings) has a 4.0% base APY, daily compounding, and monthly interest crediting. Its documented opening deposit is $100, ongoing minimum balance is $500, and paperless statements are required.
- For Green savings, the documented Silver Rewards Card bonus is +0.45%. The Silver Rewards Card has a documented minimum score of 680, a $0 annual fee, and an application credit check.
- Light Blue checking is not among the documented checking–savings pairings that provide an APY boost. Do not add a checking boost merely because the customer has that account.
- Green savings card bonuses use the highest applicable card bonus rather than a sum. Any displayed example that conflicts with the separately stated base rate plus bonus must be recomputed from the components.
- Silver savings is tiered and its high tier begins at $10,000. Do not quote its high-tier rate for a lower maintained balance.
- Gold savings ordinarily requires a $10,000 minimum balance. A documented Gold Rewards exception may reduce that balance requirement, but the Gold Rewards card has a 720 minimum score and requires an active premium subscription.

When the customer has a score estimate rather than a verified score, describe the result as an eligibility estimate rather than an approval promise.

## Presenting the recommendation

Give a compact, transparent comparison containing:

- recommended savings account and card, or a clear statement that no documented card qualifies;
- base APY, each actually applicable bonus, effective APY, and estimated one-year interest on the stated stable balance;
- comparison with the nearest realistic alternative and the approximate dollar difference;
- required account minimums, card score/subscription/credit-check conditions, fee assumptions, and paperless or linking conditions;
- a note that approval, account eligibility, and active-linked status still must be verified.

Do not let a credit-card promotional APR, sign-up bonus, cashback, or card purchase APR substitute for savings interest in the one-year savings-yield calculation unless the customer separately asks to compare those benefits.

## If the customer chooses to open savings

After the customer explicitly selects an account and authorizes account opening:

1. Complete identity verification using the normal banking flow and log verification when the runtime requires it.
2. Recheck every control listed above, including active-checking tenure, savings-account count, account standing, and the selected official account class.
3. Use the normal banking tool `open_bank_account_4821` with the authenticated customer ID, `account_type` set to `savings`, and the exact selected `account_class`.
4. After successful opening, ask whether the customer wants an immediate opening-deposit transfer. Do not transfer funds until they explicitly answer yes and the transfer controls have been reconfirmed.
5. If authorized, use `transfer_funds_between_bank_accounts_7291` from the confirmed owned checking account to the new savings account for the confirmed required amount.
6. If funding is deferred, state that the account must be funded within 30 days through an internal transfer or external deposit or it will be closed.
7. Confirm the new account details and whether it is funded or the funding deadline applies.

If a normal banking tool is unavailable, do not simulate its result. Provide the recommendation and explain that opening or funding cannot be completed in the present runtime.

For a card application, use only a documented, available card-application workflow after the customer explicitly requests it and required disclosures and consent are obtained. If no such tool/workflow is available, give the documented application steps and eligibility terms without claiming that a card was opened or approved.
