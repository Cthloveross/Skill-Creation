---
name: savings-apy-benefit-reconciliation
description: Explain applicable savings APY components and benefits when a customer has multiple linked checking accounts and credit cards, reconcile an interest credit only to the extent supported by available balance-period data, and identify information needed for an exact review.
---

# Savings APY and interest-credit reconciliation

Use this Skill for a customer asking why a Bronze or Gold Plus Savings interest credit appears low, especially when they hold several Rho checking accounts and credit cards.

## Method

1. Identify each savings account, its base APY, and the checking accounts and credit cards held under the same profile.
2. For each savings account, retain only qualifying linked checking pairings. Select the **highest** applicable checking boost; never add checking boosts together.
3. Find the applicable card bonuses for that savings type and select the **highest** card bonus; never add card bonuses together.
4. Add the base APY, one selected checking boost, and one selected card bonus. Checking and card components may stack with each other.
5. Explain that interest compounds daily and is credited monthly. An exact credit needs the statement dates and daily eligible balance history, including deposits, withdrawals, account opening, and—for Gold Plus—any investment sweep activity.
6. Do not claim that a posted credit is wrong merely from approximate current balances. Do not promise or apply an interest correction without transaction/system review.

Use `scripts/rate_reconciler.py` to make the selection deterministically. It supports the account types and policy data evidenced by this task. Do not use it to infer card eligibility or account ownership: the supplied account list must already be confirmed as same-profile, active accounts.

## Script interface

Send one JSON object on stdin and receive one JSON object on stdout.

Required input:

```json
{
  "savings_accounts": [
    {
      "type": "Bronze",
      "checking_accounts": ["Bluest Account"],
      "credit_cards": ["Crypto-Cash Back Card"]
    }
  ]
}
```

Optional fields per savings account:

- `approximate_balance`: numeric balance used only for an illustrative estimate.
- `days_in_period`: positive integer used for an illustrative daily-compounded estimate.
- `daily_balances`: array of numeric end-of-day eligible balances. When supplied, the script estimates interest from these balances and ignores `approximate_balance`/`days_in_period` for calculation.

The output provides selected and ignored qualifying benefits, total APY, and an estimate only when sufficient values were supplied. An estimate uses the disclosed APY as an effective annual rate and daily compounding: `balance * ((1 + APY)^(1/365) - 1)` for each eligible day. It is not an exact posting reconciliation and does not model undisclosed ledger timing, taxes, holds, rounding, or transaction eligibility.

## Customer-facing response checklist

- State each account's base rate, selected checking boost, selected card bonus, and resulting rate.
- Name lower qualifying benefits as not additive, rather than implying they were denied.
- State which apparent benefits do not apply because the pairing is not qualifying.
- For Gold Plus, note that benefits require the $25,000 minimum balance and that end-of-day balances above $50,000 may sweep to linked investments under the customer’s sweep settings.
- Relate the posted interest to the statement-period daily balance, not just the customer’s approximate balance today.
- Ask for the statement start/end dates and transaction/balance history if the customer wants an exact calculation. Mention opening dates and Gold Plus sweep transfers specifically when relevant.

## Validation

Before relying on a script result, verify that every requested savings type is marked `supported`, that the selected checking and card bonuses are each the maximum of their corresponding qualifying lists, and that no total includes more than one checking or more than one card bonus. If account type, active/same-profile status, dates, or balances are unavailable, provide a rate explanation and clearly limit the result to a non-exact reconciliation.
