---
name: savings-interest-reconciliation
description: Reconcile or explain monthly savings-interest credits where APY consists of a base rate plus potentially eligible credit-card and linked-checking bonuses. Use for read-only interest inquiries, especially when a customer has multiple cards or checking accounts.
---

# Savings Interest Reconciliation

Use this Skill to provide a transparent, read-only reconciliation estimate. It applies the governing rule that bonuses within the same category do not stack: select the single highest eligible credit-card bonus and the single highest eligible checking boost. The selected bonus from each category can then be added to the savings account's base APY.

## Banking safeguards

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

This Skill normally provides an explanation only. Do not access customer records, disclose non-user-supplied account details, post an adjustment, or promise a correction unless the required verification and the applicable banking workflow are available. A calculation or recommendation produced by the script is not a banking action.

## Workflow

1. Identify, separately for each savings account:
   - savings product and base APY;
   - the interest period's start/end dates and number of accrual days;
   - daily balance history, or confirmation that the balance was materially constant;
   - reported interest credit;
   - active cards under the same profile and their product-specific bonus eligibility; and
   - active checking accounts actually linked to that savings account and their qualifying-pair eligibility.
2. Consult `references/product_rate_rules.md` only for documented product rates and pairing rules. Do not infer a bonus for an undocumented product pairing or card.
3. Mark a bonus as eligible only when its status for the period is confirmed. If linkage, active status, same-profile status, or the statement period is unknown, present conditional scenarios rather than asserting the bonus applied.
4. For each category, retain only the highest confirmed eligible percentage. Do not add multiple credit-card bonuses together and do not add multiple checking boosts together.
5. Add base APY + selected card bonus + selected checking boost. The two category winners may stack with the base rate.
6. Use `scripts/reconcile_interest.py` to make a consistent constant-balance, daily-compounding estimate. It computes `balance × ((1 + effective_APY/365)^days − 1)`, which is an estimate based on a nominal annual rate convention. The official posting can differ because of actual daily balances, transaction posting times, exact product calculation conventions, and the actual cycle length.
7. Compare an estimate with the reported credit only when its accrual days and relevant eligibility facts are confirmed. State that interest compounds daily and is credited monthly. If facts are missing, request the statement period, the interest transaction date/detail, and confirmation of linkage rather than diagnosing an error.
8. If a verified, statement-based review shows the system used a lower eligible checking boost or otherwise undercredited interest, follow the normal approved correction process. Do not make an adjustment through this Skill.

## Handling multiple accounts and uncertain facts

Keep each savings account in a separate calculation. A checking account qualifies only for its documented savings pairing and only if it was linked for the period. Multiple checking accounts may create candidates, but only the largest eligible boost is used. Likewise, multiple qualifying cards create candidates, but only the largest eligible card bonus is used.

For a customer who reports account holdings but cannot confirm linkage or period dates, explain the maximum possible effective APY as a *conditional* scenario and explain why it cannot prove an underpayment. Never claim that every held product was linked or eligible.

## Calculator

Run the packaged script with JSON on stdin (through the available Skill-script runner):

```json
{
  "accounts": [
    {
      "label": "Savings account label",
      "balance": "30000",
      "days": 30,
      "base_apy_percent": "2.0",
      "credit_card_bonuses": [
        {"name": "Card A", "percent": "0.25", "eligible": true}
      ],
      "checking_boosts": [
        {"name": "Checking A", "percent": "0.70", "eligible": true}
      ],
      "reported_interest": "64.00"
    }
  ]
}
```

`balance` and `days` describe a materially constant balance during the accrual period. `eligible` must be a JSON boolean. Omit or set it to `false` for unconfirmed candidates; the script intentionally does not assume eligibility. `reported_interest` is optional.

The script emits JSON with an `accounts` array. Each result reports the selected winner in each category, effective APY, estimated interest, any difference from the reported credit, and warnings. `valid: false` or nonempty warnings mean the result is not sufficient for an exact reconciliation.

## Response checklist

A complete customer-facing response should:

- acknowledge the posted credits and explain monthly crediting/daily compounding;
- show base APY, one selected card bonus, one selected checking boost, and the resulting conditional or confirmed APY for each account;
- explicitly say that same-category bonuses do not stack;
- distinguish a calculated estimate from a statement-based determination;
- name the missing facts needed for a precise reconciliation; and
- avoid corrections or account-specific internal investigation until banking prerequisites are satisfied.

## Validation

Before relying on a calculation, check that every account has a nonnegative base APY, a positive balance, a positive integer day count, and numeric bonus values. Confirm that the output chose no more than one card bonus and one checking boost, and that all selected candidates were explicitly marked eligible. For an exact review, also confirm the statement cycle, posted interest detail, eligibility throughout that cycle, and daily balance history.
