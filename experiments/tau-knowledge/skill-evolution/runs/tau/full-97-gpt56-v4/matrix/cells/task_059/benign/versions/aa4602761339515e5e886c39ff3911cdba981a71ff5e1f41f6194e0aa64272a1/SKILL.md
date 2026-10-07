---
name: savings-and-card-first-year-value-advisor
description: Advise a Rho-Bank customer who wants a savings account and credit card by comparing first-year interest, rewards, bonuses, and annual fees; then safely open a selected personal savings account when the required identity verification, eligibility checks, and funding authorization are complete. Use for product-comparison and savings-opening conversations, not for unsupported credit-card issuance.
---

# Savings and credit-card first-year value advisor

## Purpose and boundaries

Use this Skill to turn a customer's balance, expected card spend, category mix, eligibility facts, and the applicable product disclosures into a transparent first-year comparison. It also covers the documented internal process for opening a personal savings account.

Do not treat a recommendation as an account-opening authorization. Do not state that a credit-card application is approved, issue a credit card, or call an account-opening tool until verification and every required savings-opening eligibility check have succeeded. Credit-card application steps that the disclosures assign to the customer must be presented as customer-facing online application steps; no available banking tool should be improvised to submit one.

Do not promise a bonus whose spend, date window, new-customer, good-standing, or other requirements are not met. Treat an unknown credit score or subscription status as an unresolved eligibility condition, not as approval or denial.

## Inputs to collect or establish

1. The amount intended for savings, whether it will remain for a full year, and whether it must remain liquid.
2. Estimated monthly/annual card spend and category split. If only a monthly range is known, annualize both endpoints.
3. Whether spend is likely to be at the merchants/categories needed for elevated rewards.
4. Credit-score, subscription, and new-customer facts required by candidate cards.
5. The current date before determining whether an offer window is active.
6. The exact savings account and card the customer wants after receiving the comparison.
7. Before opening savings: authenticated customer identity, customer identifier, all savings-opening eligibility results, and a clear decision on immediate opening-deposit funding.

If the user has already answered a question, use that answer rather than asking it again. Ask only for information that would materially change the recommendation or is mandatory for an action.

## Comparison method

Use APY directly for a full-year, stable-balance estimate; do not add an extra daily-compounding calculation because APY already represents annual yield. Keep all rates in percentage points until converting them to decimal form for money calculations.

For each feasible savings/card combination:

1. Determine the savings account's applicable balance tier and whether the balance meets its published ongoing minimum. Do not infer an undocumented maintenance fee or account closure outcome.
2. Determine the base APY for that tier.
3. Gather bonuses separately:
   - Among credit-card APY bonuses, use **only the highest applicable active linked-card bonus**. Do not sum them.
   - Among qualifying linked-checking boosts, use **only the highest applicable boost**. Do not sum them.
   - Add the resulting card bonus and checking boost to base APY only where the disclosures say these bonus types stack with the base/other permitted bonuses.
   - Add a relationship bonus only when the product's stated relationship criteria are actually confirmed.
4. Estimate annual interest as `balance * effective_apy / 100` for a stable one-year estimate.
5. Estimate rewards only from eligible posted purchases. Use a low/high range when the category mix is unknown. Convert stored points only at the documented redemption conversion rate; do not confuse a number of points with dollars.
6. Include a sign-up bonus only when the projected spend can satisfy it, the current date is in the offer window, and every other published condition is met. State qualifying spend required separately from reward value.
7. Calculate: `first_year_value = estimated_interest + estimated_rewards + eligible_signup_bonus_value - annual_card_fee - known_account_fees`.
8. Present exact conditions, uncertainty, and non-monetary tradeoffs next to the ranking.

Use `scripts/rank_combinations.py` for deterministic arithmetic once applicable product facts have been extracted from the public disclosures. The script ranks supplied scenarios; it does not determine legal/product eligibility, search records, or perform bank actions.

### Handling inconsistent disclosures

Quote the underlying components and show the arithmetic. If a document's stated total conflicts with its stated base rate plus stated bonus, do not repeat the inconsistent total as a calculated result. Explain briefly that the displayed components imply the arithmetic total and that the customer should review account disclosures before acting. Never silently “fix” an unrelated rate or generalize a discrepancy to other accounts.

### Communicating a recommendation

Make a recommendation conditional when necessary. For example, distinguish:

- a no-annual-fee card that is better for ordinary low spend if its credit requirement is met;
- a paid card whose higher rewards may outweigh its fee only if a sufficiently large share of spend qualifies for the elevated rate; and
- a savings account that is best only if the customer's balance meets its tier/minimum requirements.

Give a small comparison table with effective APY, approximate interest, estimated rewards range, known fees, first-year range, and eligibility caveats. Avoid claiming precision where the customer's spend categories, balance movements, card approval, or linked-account status remain unknown.

## Savings-account opening workflow

This workflow applies only after the customer chooses a personal savings account.

1. **Verify identity.** Obtain and compare two of the four identity fields (date of birth, email, telephone number, address) against the authenticated customer's record using the permitted customer lookup method. Obtain the current timestamp and call `log_verification` with the complete required record fields and timestamp only after two fields match. Do not disclose unmatched fields.
2. **Check every prerequisite before opening.** Confirm that the customer is verified; has at least one active Rho-Bank checking account; has held checking for at least 14 days; has fewer than five personal savings accounts; and has no account in collections or with a negative balance. The customer saying they have checking is not sufficient to claim all checks passed.
3. **Confirm selection.** Repeat the exact official savings `account_class` ending in `Account`, plus the published required opening deposit.
4. **Open only after steps 1–3 pass.** Unlock and use the documented internal agent tool `open_bank_account_4821` with the authenticated user ID, `account_type: "savings"`, and the exact confirmed `account_class`. Do not substitute a generic or guessed tool.
5. **Handle funding only with explicit authorization.** Ask whether the customer wants an immediate transfer from a specified eligible checking account. If yes, unlock and use `transfer_funds_between_bank_accounts_7291` with the selected source account, the newly created savings account, and the required opening-deposit amount. Confirm the transfer result before saying the account is funded.
6. **If funding is declined or deferred,** tell the customer that the account must be funded within 30 days by internal transfer or external deposit or it will be closed. Confirm the account details and funding status.

If any prerequisite cannot be verified or fails, do not open the account. Clearly state the unmet prerequisite or that it still must be checked, and continue only when it is resolved. If an actual tool outcome is `UNKNOWN`, do not repeat that operation; explain that the status needs resolution.

## Runtime script

Run:

```text
run_skill_script(relative_path="scripts/rank_combinations.py", input_json=<scenario JSON>)
```

Input JSON schema:

```json
{
  "balance": 5000,
  "annual_spend_low": 1200,
  "annual_spend_high": 2400,
  "combinations": [
    {
      "name": "Savings + card",
      "eligible": true,
      "eligibility_notes": ["conditions already checked"],
      "base_apy_pct": 4.0,
      "checking_bonus_apy_pct": 0.0,
      "card_bonus_apy_pcts": [0.45],
      "relationship_bonus_apy_pct": 0.0,
      "known_annual_account_fees": 0.0,
      "card_annual_fee": 0.0,
      "reward_rate_low_pct": 1.0,
      "reward_rate_high_pct": 4.0,
      "signup_bonus_value": 0.0,
      "signup_bonus_eligible": false
    }
  ]
}
```

All currency inputs are dollar amounts and APY/reward values are percentage points. `card_bonus_apy_pcts` may contain multiple values; the script deliberately selects only the maximum. Set `eligible` to `false` for known-ineligible combinations. Use `true` only for confirmed eligibility; if an important condition is unknown, keep the scenario out of a definitive ranking or label it conditional in `eligibility_notes`.

The script emits JSON with ranked combinations, per-combination calculations, and a validation section. Check that `effective_apy_pct` equals base plus checking plus maximum card bonus plus relationship bonus, and that all annual spend/reward values are nonnegative before using its results in a customer response.

## Completion standard

A successful advisory response states the recommended combination, estimated first-year value/range, assumptions, important eligibility requirements, and the next action needed. A successful opening response additionally reports only confirmed tool outcomes, the new account details returned by the tool, and whether the opening deposit was transferred or the 30-day funding deadline was explained.
