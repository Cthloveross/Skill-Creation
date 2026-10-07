---
name: savings-interest-credit-reconciliation
description: Reconcile or explain a monthly savings-interest credit when the customer reports balances, linked checking accounts, and credit cards. Use for Bronze Savings and Gold Plus Savings APY, linked-account boost, card-bonus, daily-compounding, and potential sweep questions. It produces a conditional, evidence-based explanation and identifies the information needed for an exact reconciliation.
---

# Savings Interest Credit Reconciliation

Use this Skill for a read-only explanation of an interest credit or a rate discrepancy. Do not treat an approximate balance, possession of a product, or a reported interest credit as proof that an account was linked, eligible, active, or maintained at that balance throughout a statement period.

## Safety and access boundaries

- A general explanation based on information the customer volunteers does not require account lookup.
- Before accessing customer-specific accounts, cards, transactions, or making any banking change, verify identity and authority using two of date of birth, email, phone number, and address; obtain the current timestamp and create the required verification log. Verify ownership, product eligibility, linkage, applicable balances, statement dates, fees, limits, and any required confirmation before an account-specific conclusion or banking action.
- Do not change an account, post a correction, or promise one. This Skill calculates an estimate only. If a system review or correction is needed and no supported tool exists, explain the limitation and use the supported escalation path only if appropriate.
- Do not request full account numbers or unredacted sensitive documents. A redacted statement is sufficient when a statement is needed.

## Method

1. Extract separately for each savings account: product, approximate or daily eligible balances, credited interest, statement-cycle dates or day count, and whether the balance was constant.
2. Identify the reported checking accounts and cards. Consult `references/product_apy_rules.md` for only the documented product-specific boosts and bonuses.
3. Test qualifying relationships rather than assuming them. A checking boost needs the documented checking/savings pairing and a confirmed active linkage. A card bonus needs a documented eligible card under the same active customer profile.
4. Select only the largest confirmed checking boost and only the largest confirmed card bonus. Never add multiple checking boosts together or multiple card bonuses together. Add the selected checking boost and selected card bonus to the savings base APY.
5. If a calculation is useful, run `scripts/interest_reconcile.py`. Pass only confirmed, applicable boosts and bonuses. Use the actual daily eligible balances if available; otherwise pass a clearly labelled constant-balance estimate and the actual number of accrual days.
6. Compare the estimated credit with the posted credit without calling it exact unless the statement dates, daily eligible balances, linkage/eligibility, and the institution's applied rate are all known. Explain that daily compounding accrues on eligible daily balances and that interest is credited monthly.
7. For Gold Plus, specifically investigate whether an automatic investment sweep reduced daily eligible savings balances above the documented threshold.
8. Give a concise customer-facing result: applicable conditional rate, why bonuses do or do not stack, whether the observed amount could be plausible, and the smallest set of facts required to complete a precise reconciliation.

## Calculator interface

Run with JSON on standard input:

```text
python scripts/interest_reconcile.py < reconciliation_input.json
```

Input is an object with an `accounts` array. Each account requires:

- `name`: display label.
- `base_apy_percent`: nonnegative annual percentage rate expressed as a percentage.
- `linked_checking_boosts_percent`: array of already-confirmed, eligible checking boosts. Use `[]` when none are confirmed.
- `card_bonuses_percent`: array of already-confirmed, eligible card bonuses. Use `[]` when none are confirmed.
- Either `daily_eligible_balances`: a nonempty array of daily balances, or both `constant_eligible_balance` and positive integer `days`.

Optional fields are `credited_interest` (a nonnegative posted credit) and `daily_rate_method`, which is either `nominal_365` or `apy_effective_365`. The default is `nominal_365`, an estimate using annual rate divided by 365. Use `apy_effective_365` only when the institution confirms the published APY is converted to a daily rate as an effective annual yield. The supplied product documents do not establish which conversion an account ledger uses, so state the method in the response.

The script returns JSON. A successful result has `ok: true` and, per account, base APY, selected boosts, selected bonus, combined APY, daily rate, estimated gross interest, calculation days, and (when supplied) the difference from the posted credit. Invalid or incomplete calculation inputs return `ok: false` with actionable errors. Monetary estimates are rounded half-up to cents only after daily accrual is calculated.

## Validation before responding

- Confirm each cited base APY, checking boost, and card bonus appears in the reference and applies to the stated savings product.
- Confirm that maxima were selected within each bonus category independently.
- Clearly distinguish confirmed facts from conditional assumptions, especially linkage and active-card status.
- Do not infer a full cycle from “last month”; ask for cycle start/end dates or the accrual day count.
- Do not use the posted credit alone to infer a rate. Balance changes, mid-cycle openings, ineligible funds, and Gold Plus sweep activity can change the result.
- When inputs are incomplete, provide a useful conditional explanation and request the statement cycle, daily balance history, linkage status, and statement interest-rate/transaction details needed for exact reconciliation.
