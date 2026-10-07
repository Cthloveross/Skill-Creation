---
name: savings-interest-reconciliation
version: 1.0.0
description: Reconciles or triages disputed monthly savings-interest credits for Silver, Silver Plus, Platinum, and Diamond Elite accounts. Use when a customer questions an interest credit, needs the applicable APY components explained, or needs to obtain the records required for a reconciliation.
---

# Savings Interest Reconciliation

Use this Skill to provide a careful, evidence-based explanation of savings interest and to reconcile it only when the required statement records are available. It supports product-rule calculations, but does not retrieve savings statements, savings balances, transaction histories, interest-credit entries, or checking-linkage status.

## Banking-control requirement

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This Skill is normally informational. Do not treat a name, email address, account number, or a prior lookup as sufficient authority for an account-specific action. Before any action such as changing an account, filing a dispute, requesting a statement, or disclosing non-public account information, complete the runtime's required identity verification and logging process and verify the applicable prerequisites above.

## What must be established

A defensible reconciliation needs all of the following for each disputed account and statement cycle:

1. Statement-period start and end dates.
2. The posted interest-credit date and exact amount.
3. Every daily/end-of-day balance, or complete dated deposits and withdrawals from which daily balances can be reconstructed.
4. Account type and the rate tier that applied each day.
5. Eligibility and effective dates for APY additions: the highest eligible active card bonus, qualifying checking linkage, relationship benefit, and direct-deposit status where applicable.
6. Confirmation that all products were held under the same customer profile where the product rule requires it.

Do not infer these facts from approximate balances, recalled amounts, a current card list, or the customer's list of checking accounts. In particular, a qualifying checking-and-savings *pairing* does not prove that the accounts were linked during the disputed cycle, and a current card list does not prove eligibility throughout a past cycle.

## Product rules covered

See `references/product_rules.json` for the documented base APY tiers, balance thresholds, account-specific card schedules, and the checking boosts whose amounts are documented. Apply only rules that are supported by the records for the relevant dates.

General rules:

- Silver: 2.5% below $10,000 and 4.0% at or above $10,000.
- Silver Plus: 3.0% below $15,000 and 4.5% at or above $15,000.
- Platinum: 6.5%.
- Diamond Elite: 7.5%.
- Interest is compounded daily and credited monthly.
- Card APY bonuses do **not** stack with other card bonuses. Only the highest applicable active card bonus applies.
- The selected card bonus may stack with verified checking-linkage and relationship bonuses. Silver Plus's direct-deposit bonus, if active, is also additive.
- A balance moving across a tier threshold changes the base tier for that day. The tiers described here are whole-balance tiers, not marginal bands.

The supplied records do not document every possible boost amount. If the relevant pairing is known to qualify but its numeric boost is absent, leave it unresolved rather than estimating it.

## Workflow

1. **Classify the request.** Determine whether the customer wants a general explanation, a calculation, copies of records, an investigation, or an account action. Only the first two are possible with this Skill's packaged calculator.
2. **Check capability before making claims.** Inspect the declared banking tools. If there is no tool for savings statements, savings activity, posted interest, or linkage, state that limitation plainly. Never claim that an investigation was performed when the necessary data is unavailable.
3. **Protect account information.** For an informational discussion, use customer-provided facts and public product rules. Complete identity verification, authority checks, ownership checks, and any required audit logging before an account-specific action or disclosure.
4. **Collect the minimum evidence.** Ask for statement PDFs or activity exports covering the complete disputed cycle, including the exact interest credit. If daily balances are unavailable, ask for all dated transactions plus the opening balance. Ask separately about direct deposit and the actual linked-account status during the cycle.
5. **Explain likely sources of differences without reaching a conclusion.** Mention daily balance changes, day count, tier crossings, unverified bonuses, the highest-card-only rule, activation/effective dates, and the fact that monthly crediting is not the same as applying an annual APY to one recalled balance.
6. **Calculate only from complete inputs.** Run `scripts/interest_reconcile.py` after converting verified statement data to its JSON schema. Treat its result as a documented estimate under its stated daily-rate convention, then compare it with the posted interest credit.
7. **Handle unavailable records.** If the customer cannot access records and the tools cannot retrieve them, do not manufacture a result or declare an error. Explain that the calculation cannot be verified from approximate balances alone. Advise the customer to use their authenticated banking channel's statements/documents area or request copies through an authenticated bank-support channel. If they need the bank to investigate or cannot obtain records, offer transfer to an appropriate savings/statement specialist; when transfer is appropriate, use the declared `specialized_department_required` reason and summarize the missing records and tool limitation.

## Customer-facing response structure

Use a concise response with these components:

- Acknowledge the discrepancy and clarify that an annual APY is accrued daily and credited monthly.
- State the account-specific base-tier rule and the highest-card-bonus rule relevant to the account, but identify all eligibility/linkage facts that remain unverified.
- State whether the available tools can access the required savings records. Do not imply that credit-card data proves historical savings eligibility.
- List the exact evidence required to reconcile each account.
- Tell the customer how to obtain statement/activity records through an authenticated channel or offer a specialist transfer if an investigation is needed.
- Do not promise a correction, credit, or reversal before the posted entries and eligibility are verified.

## Calculator

Run the calculator by passing a JSON object on standard input; it emits one JSON object on standard output:

```sh
python scripts/interest_reconcile.py < input.json
```

### Input schema

```json
{
  "account_type": "Silver Account | Silver Plus Account | Platinum Account | Diamond Elite Account",
  "balances_exclude_uncredited_interest": true,
  "daily_balances": [
    {
      "date": "YYYY-MM-DD",
      "balance": "decimal ledger balance",
      "card_bonus_percent": "optional verified daily card bonus",
      "checking_bonus_percent": "optional verified daily checking bonus",
      "relationship_bonus_percent": "optional verified daily relationship bonus",
      "direct_deposit_bonus_percent": "optional verified daily direct-deposit bonus"
    }
  ],
  "held_card_types": ["optional card names used only to select the documented highest card bonus"],
  "checking_bonus_percent": "optional verified cycle-wide numeric boost",
  "relationship_bonus_percent": "optional verified cycle-wide numeric boost",
  "direct_deposit_bonus_percent": "optional verified cycle-wide numeric boost",
  "posted_interest_credit": "optional exact posted interest amount"
}
```

`daily_balances` must cover consecutive calendar days exactly once. Use one daily record per calendar day. The balance must be the closing ledger balance **excluding interest that has accrued but has not yet been credited**, because the calculator separately compounds that accrual. Use explicit per-day bonus fields when eligibility changed within the cycle; per-day values override their cycle-wide counterparts. Supply `held_card_types` only if the selected highest card bonus is constant over the entire cycle.

### Output and validation

On success, output includes the calculated daily-compounded interest estimate, each date's selected base APY and bonus components, any documented card bonus selected, undocumented supplied card types, and—when supplied—the difference from the posted credit. Dollar values are rounded to cents only in output; daily accrual is retained at higher precision internally.

The script rejects unsupported account types, nonnumeric or negative balances, duplicate/nonconsecutive dates, missing daily records, conflicting same-day card sources, and a balance convention that would double-count accrued interest. Review rejected input rather than filling gaps with assumptions.

The calculation uses an APY-to-daily-rate convention of `(1 + APY / 100)^(1/365) - 1`. It is an aid to reconciliation, not evidence that the institution used that convention if an account agreement or statement specifies a different day-count method.
