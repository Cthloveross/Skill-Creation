---
name: savings-interest-credit-explainer
description: Explain and reconcile apparently low monthly interest credits for Bronze Savings and Gold Plus Savings using documented APYs, qualifying checking and card boosts, daily compounding, and statement-period balance information. Use when a customer asks why a savings interest credit differs from a rough annual-rate estimate.
---

# Savings interest credit explainer

Use this Skill for an informational explanation of posted monthly interest. It does not access accounts, statements, or make account changes.

## Product facts to apply

Consult `references/rate_rules.md` for the supported account rates, qualifying linked-checking boosts, and Gold Plus card bonuses.

Key interpretation rules:

1. Interest compounds daily and is credited as one monthly transaction.
2. A posted credit depends on the statement's number of accrual days and the actual eligible daily balances, not merely an approximate current balance.
3. A qualifying checking boost requires the specified checking/savings pairing under the same customer profile. Do not claim a boost applied merely because the customer owns both products; confirm linkage/eligibility when it is unknown.
4. Linked-checking boosts are additive to base APY and applicable card bonuses. The supplied material does not establish whether more than one checking boost can be combined for one savings account. Do not add multiple checking boosts unless account documentation or the statement establishes that result.
5. Gold Plus card bonuses require an eligible named card under the same customer profile. Do not guess the card type or bonus.

## End-to-end response method

1. Restate the relevant posted amount, approximate balance, and account type.
2. Identify the supported base APY and the *possible* qualifying boosts based on the account types the customer reports. Clearly separate known facts from unconfirmed linkage/card eligibility.
3. Explain daily compounding and monthly crediting. State that a one-month credit is not the annual APY multiplied by the balance.
4. If the period length and a balance or daily-balance series are available, calculate a transparent estimate with `scripts/interest_projection.py`. Use the total APY only when each component is confirmed. Otherwise, present a conditional estimate or a rate range, labeled as an estimate.
5. Compare the estimate to the credit without asserting an error where statement dates, daily balances, product linkage, or eligible cards are absent.
6. Ask only for the missing information needed for an exact reconciliation: statement start/end dates, daily balance history or all deposits/withdrawals, which qualifying checking account is linked, and the names of any eligible cards. Suggest reviewing the monthly interest entry and balance history.

For the supplied conversation, an appropriate explanation should note that a Bluest–Bronze pairing can provide +0.7%, a Green Fee-Free–Bronze pairing can provide +0.4%, and a Gold Years–Gold Plus pairing can provide +0.5%, subject to linkage and same-profile eligibility. A Gold Plus credit near the result of 6.0% plus 0.5% for a full monthly period may therefore be unsurprising; do not present this as confirmation without the statement/linkage details. The customer's unspecified credit cards must not be assigned a bonus.

## Calculator

Run `scripts/interest_projection.py` with JSON on stdin. It emits JSON on stdout.

### Input schema

```json
{
  "accounts": [
    {
      "name": "optional label",
      "base_apy_pct": 6.0,
      "checking_boost_pct": 0.5,
      "card_boost_pct": 0.0,
      "days": 31,
      "balance": 60000
    }
  ]
}
```

Each account must provide non-negative numeric APY components. Provide either:

- `balance` and positive integer `days` for a constant-balance projection; or
- `daily_balances`, a nonempty array of non-negative daily principal balances. In this form, the array length is the accrual-day count and `days`/`balance` are not needed.

The script treats the stated total APY as an effective annual yield and derives the daily rate as `(1 + APY)^(1/365) - 1`. With daily balances, it accrues interest daily on each supplied principal balance plus previously accrued interest. It returns unrounded interest and a two-decimal display amount. This is a transparent estimate; use a statement's actual calculation convention if it differs.

Example runnable call:

```sh
printf '%s' '{"accounts":[{"name":"Gold Plus","base_apy_pct":6.0,"checking_boost_pct":0.5,"card_boost_pct":0,"balance":60000,"days":31}]}' | python3 scripts/interest_projection.py
```

### Validation

Before relying on a result, confirm that every APY component is supported and confirmed, days match the statement period, and daily balances cover every accrual day when used. The script returns `ok: false` with a list of validation errors rather than silently calculating incomplete or invalid inputs. Compare the displayed estimate—not an annualized balance-times-APY figure—to the posted net interest, while allowing for unknown balance movements and statement conventions.

## Boundaries

Do not request identity verification or use account lookup tools for this general explanation. Do not promise an adjustment, claim a missing bonus, or state that the credit is erroneous without account and statement evidence. If the customer requests a transaction investigation that cannot be resolved from the statement and documented rates, explain the missing evidence and follow the available support/escalation process.
