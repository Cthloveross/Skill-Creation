---
name: savings-interest-credit-reconciliation
description: Reconcile or explain a monthly savings-interest credit when the customer reports balances, linked checking accounts, and credit cards. Use for Bronze Savings and Gold Plus Savings APY, linked-account boost, card-bonus, daily-compounding, and potential sweep questions. It produces a conditional, evidence-based explanation and identifies the information needed for an exact reconciliation.
---

# Savings Interest Credit Reconciliation

Use this Skill for a read-only explanation of an interest credit or a rate discrepancy. Do not treat an approximate balance, possession of a product, or a reported interest credit as proof that an account was linked, eligible, active, or maintained at that balance throughout a statement period.

## Safety and access boundaries

- A general explanation based on information the customer volunteers does not require account lookup.
- Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes. Apply the prerequisites relevant to the requested action and do not claim an unavailable check was completed.
- Before accessing customer-specific accounts, cards, transactions, or making any banking change, verify identity and authority using two of date of birth, email, phone number, and address. Match both fields to one customer record, obtain the current timestamp, and create the required verification log before the lookup or conclusion. Verify ownership, product eligibility, linkage, applicable balances, statement dates, fees, limits, and any required confirmation before an account-specific conclusion or banking action.
- After verification, use only a declared tool that actually exposes the needed account information. Do not infer checking-to-savings linkage or Gold Plus sweep status from product ownership, balances, or interest credits. If no supported tool exposes linkage or sweep settings/history, explain that limitation and transfer the verified customer to the appropriate specialist using `specialized_department_required`; include the requested review items in the transfer summary.
- Do not change an account, post a correction, or promise one. This Skill calculates an estimate only. If a system review or correction is needed and no supported tool exists, explain the limitation and use the supported escalation path only if appropriate.
- Do not request full account numbers or unredacted sensitive documents. A redacted statement is sufficient when a statement is needed.

## Method

1. Extract separately for each savings account: product, approximate or daily eligible balances, credited interest, statement-cycle dates or day count, and whether the balance was constant. Treat runtime clarification answers as facts reported by the customer; do not ask for them again, but do not treat them as proof of eligibility or linkage.
2. Identify the reported checking accounts and cards. Consult `references/product_apy_rules.md` for only the documented product-specific boosts and bonuses.
3. Test qualifying relationships rather than assuming them. A checking boost needs the documented checking/savings pairing and a confirmed active linkage. A card bonus needs a documented eligible card under the same active customer profile.
4. Select only the largest confirmed checking boost and only the largest confirmed card bonus. Never add multiple checking boosts together or multiple card bonuses together. Add the selected checking boost and selected card bonus to the savings base APY.
5. If exact dates and daily balances are unavailable, do not present a single estimate as a reconciliation. Give a conditional explanation, or (when useful) label a constant-balance illustration with an explicit assumed day count. Explain how the answer changes if a documented boost or bonus is not confirmed.
6. If a calculation is useful, run `scripts/interest_reconcile.py`. Pass only confirmed, applicable boosts and bonuses. Use the actual daily eligible balances if available; otherwise pass a clearly labelled constant-balance estimate and the actual number of accrual days.
7. Compare the estimated credit with the posted credit without calling it exact unless the statement dates, daily eligible balances, linkage/eligibility, and the institution's applied rate are all known. Explain that daily compounding accrues on eligible daily balances and that interest is credited monthly.
8. For Gold Plus, specifically investigate whether an automatic investment sweep reduced daily eligible savings balances above the documented threshold.
9. Give a concise customer-facing result: applicable conditional rate, why bonuses do or do not stack, whether the observed amount could be plausible, and the smallest set of facts required to complete a precise reconciliation.

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

Optional fields are `credited_interest` (a nonnegative posted credit) and `daily_rate_method`, which is either `nominal_365` or `apy_effective_365`. The default is `apy_effective_365`: it converts a stated APY to the daily compounded rate that yields that APY over 365 days. Use `nominal_365` only if the institution confirms it accrues the disclosed annual percentage as an annual nominal rate divided by 365. State the selected method in the response and do not represent an estimate as the ledger calculation without the statement details.

The script returns JSON. A successful result has `ok: true` and, per account, base APY, selected boosts, selected bonus, combined APY, daily rate, estimated gross interest, calculation days, and (when supplied) the difference from the posted credit. When a posted credit and an explicitly constant balance are supplied, it also returns a conditional `posted_implied_apy_percent_constant_balance`; do not use that diagnostic for changing balances or as proof of the actual applied rate. Invalid or incomplete calculation inputs return `ok: false` with actionable errors. Monetary estimates are rounded half-up to cents only after daily accrual is calculated.

## Validation before responding

- Confirm each cited base APY, checking boost, and card bonus appears in the reference and applies to the stated savings product.
- Confirm that maxima were selected within each bonus category independently.
- Clearly distinguish confirmed facts from conditional assumptions, especially linkage and active-card status.
- Do not infer a full cycle from “last month”; ask for cycle start/end dates or the accrual day count. Do not re-ask a fact already supplied in the current conversation or runtime input.
- Do not use the posted credit alone to infer a rate. Balance changes, mid-cycle openings, ineligible funds, and Gold Plus sweep activity can change the result.
- When inputs are incomplete, provide a useful conditional explanation and request the statement cycle, daily balance history, linkage status, and statement interest-rate/transaction details needed for exact reconciliation.
