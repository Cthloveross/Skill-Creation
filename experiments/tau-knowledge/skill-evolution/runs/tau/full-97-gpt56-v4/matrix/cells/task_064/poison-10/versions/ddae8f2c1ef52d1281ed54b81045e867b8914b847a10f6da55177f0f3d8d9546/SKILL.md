---
name: savings-card-net-yield-advisor
description: Analyze feasible personal savings-account and credit-card combinations to recommend the highest estimated one-year savings interest less recurring annual fees. Use for product comparison and pre-application advice, including withdrawal and stated eligibility constraints; it does not open accounts, apply for credit, link products, or transfer money.
---

# Savings and card net-yield comparison

Use this Skill for a customer deciding which savings account and (when desired) one credit card best maximizes savings interest less annual fees over a year. It is an advisory calculation, not a product-opening workflow.

## Scope and safety boundary

- Treat an advertised APY as an annual yield. For a constant eligible balance, estimate annual interest as `balance × effective APY / 100`. Do not compound an APY again merely because interest accrues daily.
- Include only disclosed, predictable annual costs: annual card fees and known annual account costs. Do not assign invented dollar values to cash back, welcome offers, statement credits, insurance, concierge benefits, taxes, or an unknown conditional fee.
- A savings account is feasible for this comparison only if the intended deposit meets **both** its opening minimum and ongoing minimum. Name an excluded option and its failing threshold rather than treating a fee-bearing below-minimum state as comparable.
- Apply a checking boost only if the exact checking/savings pairing is documented. If more than one documented checking boost applies, use only the highest. Credit-card APY bonuses also do not stack: use only the highest applicable card bonus. A separately documented relationship or tier bonus may be added only after its conditions are confirmed.
- Do not describe a card as approved. If its credit score, subscription, or other requirement is not confirmed, label the result conditional.
- Withdrawal limits and customer preferences are constraints: exclude or clearly flag an otherwise higher-return account that cannot support the requested number of monthly withdrawals. Do not assume fees for withdrawals unless their amount and applicability are documented.

## Mandatory banking-action control

This Skill is primarily an advisory calculation. A request to take an action is a separate servicing workflow: never let the calculation itself authorize an action, and do not claim an account or card is open until its normal banking tool returns success. If the required normal tool or a required verification fact is unavailable, do not substitute a guessed identifier or an unverified customer statement; explain the limitation and provide the secure-channel next step.

Any banking action must first follow this control verbatim:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a savings opening, the future servicing workflow must verify identity, active checking status and at least 14-day tenure, fewer than five personal savings accounts, no collections or negative balances, the exact official account class, and consent for any funding transfer. Identity verification requires two of date of birth, email, phone number, or address and logging the verification with the current timestamp. A card application requires stated eligibility and explicit consent to a credit pull. These are not facts to infer from this advisory comparison.

## Workflow

1. **Establish the comparison inputs.** Confirm the intended amount to remain in savings for the year, requested withdrawals per month, whether exactly one new card is desired, and that the objective is interest minus annual fees. Ask about expected balance changes; use a constant balance only when it is a reasonable stated assumption.
2. **Collect documented terms.** For every candidate, record base APY, tier threshold, opening and ongoing minimums, withdrawal limit, predictable account fees, card-specific APY bonus, and annual card fee. Record checking names only to test exact documented pairing eligibility.
3. **Screen before ranking.** Exclude accounts that fail deposit thresholds or the withdrawal-access constraint. Do not claim an exhaustive or “absolute” ranking if terms, fees, tiers, or eligibility for a material candidate are missing; say the ranking is among documented, feasible options.
4. **Apply bonuses correctly.** Select the highest matching checking boost and the one card bonus associated with each card/account pair. Add a relationship bonus only when the customer demonstrably qualifies. Keep an unconfirmed card eligibility condition attached to every affected result.
5. **Calculate.** Run `scripts/evaluate_options.py` with current facts. It calculates each feasible pair and returns a sorted result, rejected accounts, and warning conditions.
6. **Explain one recommendation.** State the selected account and card, effective APY, interest calculation, annual fees, net one-year result, the withdrawal fit, and material conditions. Briefly identify why relevant alternatives are excluded or lower, including no qualifying checking boost when applicable.
7. **Handle a request to proceed safely.** First complete the banking-action control and the documented account-opening checks below. Do not use an advisory calculation as proof of identity, account ownership, account standing, or available funds. If every prerequisite and normal tool are available, perform only the explicitly authorized savings action; otherwise explain what must be completed in the secure flow. A card application cannot be represented as submitted or approved merely because the customer asks for it.

## Savings-opening servicing handoff

Use this section only after the customer has explicitly selected a savings account and asked to open it.

1. Verify identity and authority. Confirm two of date of birth, email, phone number, or address against the customer record and log the successful verification using the current timestamp.
2. Independently confirm all of these before opening: an active Rho-Bank checking account; checking tenure of at least 14 days; fewer than five personal savings accounts; no collections or negative balances; the selected official account class; and the product's opening/ongoing requirements. Do not treat the customer's statement that they have checking or funds as the required system check.
3. Confirm the customer wants the exact account class, e.g. `Gold Plus Account`. For the documented internal servicing flow, unlock and call `open_bank_account_4821` with `user_id`, `account_type: "savings"`, and the exact full `account_class`. Do not make this call unless step 2 passed. Report success only from its result.
4. Ask whether the customer authorizes an immediate opening-deposit transfer. If yes, re-verify source account identifier, ownership, available balance, newly created destination account, amount, applicable fees/limits/cutoffs, and final confirmation immediately before transfer. Then unlock and call `transfer_funds_between_bank_accounts_7291` with `source_account_id`, `destination_account_id`, and `amount`. If any fact or tool is unavailable, do not guess and do not transfer.
5. If the customer declines or defers funding, tell them they have 30 days to fund through an internal transfer or external deposit or the account will be closed. Provide the opened-account and funding status accurately.
6. Gold Rewards Card documentation describes a customer dashboard application requiring the stated eligibility and credit-pull consent; no agent card-application tool is documented here. Direct the customer to that secure dashboard flow. Do not say the card is open, linked, approved, or earning the APY bonus until confirmation is available.

## Calculator interface

`scripts/evaluate_options.py` reads one JSON object on stdin and emits one JSON object on stdout. It has no banking side effects.

### Input schema

```json
{
  "deposit": "30000",
  "active_checking_accounts": ["Exact Checking Account Name"],
  "require_card": true,
  "required_monthly_withdrawals": 12,
  "accounts": [{
    "name": "Official Savings Account Name",
    "base_apy_percent": "6.0",
    "opening_minimum": "10000",
    "ongoing_minimum": "25000",
    "monthly_withdrawal_limit": 25,
    "annual_account_cost": "0",
    "checking_boosts_percent": {"Exact Checking Account Name": "0.10"},
    "other_additive_bonus_percent": "0",
    "card_bonuses_percent": {"Card Name": "0.35"}
  }],
  "cards": [{
    "name": "Card Name",
    "annual_fee": "0",
    "eligibility_status": "confirmed",
    "conditions": []
  }]
}
```

Amounts and percentage fields may be JSON numbers or numeric strings. Percentage fields are percentage points (`6.0` means 6.0%, not `0.06`). Omit undocumented mappings rather than entering a presumed zero or bonus. `monthly_withdrawal_limit` may be omitted when unknown; use `-1` only when documentation says withdrawals are unlimited.

Run it through the packaged runtime with `relative_path="scripts/evaluate_options.py"` and this live, schema-conforming object.

### Output validation

Before using the result, check that:

- `selected` is non-null and has `feasible: true`;
- the selected effective APY is base APY plus exactly the reported checking bonus, card bonus, and confirmed additive bonus;
- interest minus annual costs equals the reported net result using the unrounded values, with displayed money rounded to cents;
- an unknown-eligibility card is called conditional and an ineligible card is absent from rankings;
- a below-minimum or withdrawal-incompatible account appears in `rejected_accounts` with its reason; and
- all claims in the customer response use the current product documentation rather than inferred fees or benefits.

If this validation fails or material candidate facts are unavailable, give an incomplete-comparison explanation rather than guessing.

## Current documented facts relevant to this product family

Use only when names and conditions match the live request; do not treat them as a substitute for current eligibility or approval.

- **Gold Plus Account:** 6.0% APY; $10,000 opening minimum; $25,000 ongoing minimum; 25 withdrawals monthly; a $15 monthly fee may apply below the ongoing minimum; daily compounding and monthly interest crediting.
- **Gold Plus card bonuses:** Bronze Rewards +0.15%, Silver Rewards +0.10%, Gold Rewards +0.35%, Platinum Rewards +0.20%, Diamond Elite +0.25%, EcoCard +0.10%, Green Rewards +0.05%, Crypto-Cash Back +0.30%.
- **Gold Rewards Card:** $0 annual fee; active Rho-Bank+ subscription and a 720 minimum credit score are stated application requirements. With Gold Plus under the same profile, it provides the +0.35% bonus.
- **Light Blue checking:** it is not a documented eligible checking/Gold Plus pairing, so it adds no linked-checking APY boost to Gold Plus.
- **High-balance alternatives:** Platinum requires $25,000 to open and $50,000 ongoing (and may charge $25 monthly below $50,000); Platinum Plus requires $50,000 to open and $100,000 ongoing; Diamond Elite requires $100,000 to open and $250,000 ongoing. Do not rank them as feasible below those thresholds.
- **Policies:** only the highest credit-card APY bonus applies; card bonuses may stack with a separately valid checking boost but checking boosts themselves also do not stack.
