---
name: savings-card-combination-advisor
description: Advise on the highest-yield documented savings and credit-card combination while honoring hard eligibility, credit-check, statement-delivery, and funding requirements; then safely handle a requested savings opening.
---

# Savings and card combination advisor

Use this Skill for a customer comparing a savings account plus a credit card, particularly when the card affects savings APY. Give advice before taking any account action. A recommendation is not an application, account opening, or authorization to transfer money.

## Inputs and evidence

Read the current conversation and the supplied task inputs for the intended balance and horizon; credit-score range; subscription and invitation status; whether the customer requires a genuine credit review; paper-statement needs; accounts already held; and each explicit choice or transfer authorization.

Use `references/product_rules.json` only for product facts represented there. Do not infer an APY boost from similar account names: a linked checking boost needs the exact documented pairing and its documented percentage. Do not claim a card is approved merely because it meets a published minimum.

## Compare products

1. Turn explicit preferences into hard filters before ranking. Exclude a savings product that requires paperless statements if mailed statements are required. Exclude a card if its published score/subscription/invitation requirement is unmet, or if the documentation cannot confirm a required credit check.
2. Check the intended balance against opening and ongoing minimums and against the applicable APY tier. A balance below a tier threshold does not receive that tier.
3. For each remaining savings/card pair, add the card APY bonus only when the products are held under the same customer profile. Credit-card bonuses never stack: select only the highest one. A documented checking boost may stack with the selected card bonus, but only if the actual checking/savings pair and boost amount are confirmed. Relationship and direct-deposit bonuses are also excluded until their distinct criteria are confirmed.
4. Rank compatible pairs by the confirmed effective APY, then calculate transparent one-year estimates with `scripts/yield_calculator.py`. With a stable balance, APY is already an annual yield: annual interest is `balance * effective_apy_percent / 100`. Do not compound an APY again. Describe the result as an estimate because balance changes and qualification changes affect credited interest.

### Required explanation

Name the recommended account and card, effective APY, estimated one-year interest, applicable balance tier, statement-delivery result, card annual fee when documented, required balance/deposit, and why each material alternative is excluded. State any conditional upside separately, never in the headline yield.

For example, a customer with a balance below the Silver Plus Tier 2 threshold who needs mailed statements and a credit-verifying card should be evaluated using the documented Tier 1 rate and only the eligible linked-card bonus. If another pair has a higher raw APY but requires paperless statements, identify that it is not compatible rather than recommend it. A checking account with a nonmatching name is not evidence of a boost.

## Savings-opening workflow

Only begin this after the customer clearly selects the exact savings account. For `Silver Plus Account`, the official class string is exactly `Silver Plus Account`.

1. Authenticate the customer by matching two of date of birth, email, phone, and address to the customer record. Call `log_verification` only after two fields match, including the recorded full details and current timestamp.
2. Before opening, complete the documented eligibility checks: verified identity; an active Rho-Bank checking account held at least 14 days; fewer than five personal savings accounts; and no collections or negative balances. Do not treat a customer assertion, a successful identity lookup, or a successful open call as evidence that these separate checks passed.
3. After all checks and the exact account selection, unlock and call the documented agent tool `open_bank_account_4821` with the verified `user_id`, `account_type` of `savings`, and exact full `account_class`. Report an account as open only if that call succeeds.
4. After opening, ask whether the customer authorizes an immediate transfer and ask for an unambiguous dollar amount if necessary. If they decline, state the documented 30-day funding deadline and closure consequence.
5. For an authorized transfer, use the documented agent tool `transfer_funds_between_bank_accounts_7291` with the internally verified checking `source_account_id`, returned new-savings `destination_account_id`, and authorized amount. Confirm the tool result before stating money moved.

The agent, not the customer, must use agent tools. Never ask the customer to provide an internal tool parameter or to invoke a tool. If the supported environment cannot resolve a safe source account internally, do not guess or send money; explain that no transfer was made and offer the documented external-deposit/deferred-funding route. Never retry an operation whose status is unknown.

Credit-card applications are separate from savings opening. Follow only a documented, supported card-application flow and obtain the required credit-check consent. If no submission tool or authorized flow is available, do not claim submission; explain the documented online application steps instead.

## Reproducible screening helper

Use `scripts/evaluate_combinations.py` to apply the documented hard filters before drafting an answer. It reads one JSON object on stdin and writes JSON on stdout; it never performs banking actions. Required inputs are nonnegative `balance` and boolean `paper_statements_required`, `credit_check_required`, `premium_subscription_active`, `invitation_received`, and `same_customer_profile_confirmed`. `credit_score` is optional but must be a nonnegative number when supplied. Its output contains ranked compatible combinations plus separate savings and card exclusions.

For a real interaction, populate every field from the current customer conversation and verified facts; do not copy a prior customer’s values. Treat a missing score, subscription, invitation, or same-profile confirmation conservatively. The helper estimates annual interest from APY and intentionally does not add unconfirmed relationship, direct-deposit, or checking boosts. Review the output against the source facts before replying, because it can evaluate only products documented in its packaged rules file.

## Calculator

Run the packaged script with JSON on stdin:

```sh
printf '%s' '{"balance":8000,"base_apy_percent":3.0,"bonuses_percent":[0.15]}' | python3 scripts/yield_calculator.py
```

Input is a JSON object with required nonnegative `balance` and `base_apy_percent`, optional nonnegative `days` (default 365), optional `relationship_bonus_percent` (default 0), and `bonuses_percent` (a list of percentage-point bonuses). Supply at most one nonzero credit-card bonus; the script rejects multiple nonzero bonuses by default. It emits JSON containing `effective_apy_percent`, selected bonus, estimated interest, ending balance, and a qualification/balance caveat. Validate that reported effective APY equals the base rate plus only confirmed bonuses and that the displayed money amount matches the customer’s intended balance.

## Final safety check

Before replying or acting, verify every stated hard constraint, the product names, tier, bonus non-stacking, statement result, and opening/funding requirements. Do not state that an application, opening, or transfer happened unless its normal tool reported success.
