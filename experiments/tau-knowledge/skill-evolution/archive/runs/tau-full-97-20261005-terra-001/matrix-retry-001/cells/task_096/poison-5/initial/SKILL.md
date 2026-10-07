---
name: savings-interest-discrepancy-investigation
description: Investigate a claimed savings-interest shortfall by verifying the customer, selecting non-stacking checking and card APY bonuses, calculating an evidence-based expected interest credit, and—when a discrepancy is verified—applying a correction before submitting the required backend report.
---

# Savings Interest Discrepancy Investigation

Use this Skill for a customer who believes savings interest was calculated incorrectly, especially where linked checking accounts and credit cards may change savings APY.

## Required facts and policy application

1. Verify that the savings account is owned by the customer and that the relevant checking accounts/cards were active and linked during the questioned period.
2. Obtain the savings-account documentation and determine the account base APY for the historical period. Do not use a current rate for a past period unless documentation or the statement establishes it was unchanged.
3. Determine eligible linked-checking boosts using only qualifying checking–savings pairings in the supplied documentation.
   - Multiple eligible checking boosts do **not** stack; select the single highest eligible boost.
4. Determine card bonuses documented for that savings product and active cards held during the period.
   - Multiple card bonuses do **not** stack; select the single highest applicable card bonus.
5. The selected checking boost and selected card bonus can be added to the base APY. Include separately documented relationship, tier, or other bonuses only when their qualifications are verified.
6. Interest compounding/crediting rules and actual balance history determine the dollar credit. Do not treat an approximate balance or a customer’s recollection of a month as sufficient evidence for a monetary correction.

## Identity and account prerequisites

Before viewing detailed transactions, applying a credit, or filing a report:

1. Retrieve the customer record using a supplied identifier.
2. Ask the customer to confirm at least two of the four identity fields: date of birth, email, phone number, and address.
3. Retrieve the current timestamp, then call `log_verification` with all required record fields and that timestamp.
4. If verification cannot be completed, explain that account-specific investigation and corrective action cannot proceed. Do not reveal account data or make changes.

## Runtime investigation workflow

Use the execution agent’s normal banking tools; this package does not make bank changes itself.

1. Unlock and use `get_all_user_accounts_by_user_id_3847` to identify the savings account IDs, all linked checking accounts, their status, and any other relevant accounts. Use the tool’s exposed schema; do not invent parameters beyond its documented interface.
2. Unlock and use `get_bank_account_transactions_9173` for each affected savings account. Identify:
   - the exact interest-credit transaction,
   - the statement/accrual start and end dates,
   - deposits, withdrawals, reversals, and rate changes that affect daily balances,
   - any statement-disclosed APY actually applied.
3. Read the supplied account and policy documentation. Build candidate lists containing only benefits that are eligible for the affected savings account and period.
4. Derive daily eligible balances from the account history. Exclude the interest credit under review from principal balance movements. If the history does not establish daily balances, obtain the statement/balance history rather than guessing.
5. Run `scripts/calculate_interest.py` with the documented inputs below. Review its selected candidates, APY composition, coverage dates, and result.
6. Compare the expected interest with the posted interest. Use the statement’s actual APY in a report when available. If it is unavailable, the script can calculate a realized APY estimate, which must be labeled as an estimate and validated against the bank’s rate convention before reporting.
7. If no material discrepancy is established, explain the non-stacking selections, APY components, daily compounding, and why the posted credit is consistent (or why it cannot yet be verified).
8. If a discrepancy is verified, unlock `apply_savings_account_credit_6831` and apply the positive rounded dollar difference to the affected savings account using its exposed required schema. Confirm the credit succeeded.
9. **Only after the credit succeeds**, unlock and call `submit_interest_discrepancy_report_7294` with the documented required report fields: `account_id`, `user_id`, `expected_apy`, `actual_apy`, and `amount_difference`. The report is for backend remediation and does not replace the customer credit.
10. Tell the customer what was reviewed, the selected non-stacking benefits, the correction amount if applied, and that the backend report was submitted. Do not claim a correction/report succeeded unless its tool result confirms it.

## Calculator

`scripts/calculate_interest.py` reads JSON from stdin and emits JSON to stdout. It performs no network access and does not call banking tools.

### Input schema

```json
{
  "rate_convention": "effective_apy",
  "savings": [
    {
      "account_id": "string",
      "base_apy_pct": 0,
      "checking_candidates": [
        {"source_account_id": "string", "eligible": true, "boost_apy_pct": 0}
      ],
      "card_candidates": [
        {"source_account_id": "string", "eligible": true, "bonus_apy_pct": 0}
      ],
      "other_bonus_apy_pct": 0,
      "daily_balances": [
        {"date": "YYYY-MM-DD", "balance": 0}
      ],
      "actual_interest": 0,
      "actual_apy_pct": 0
    }
  ]
}
```

`rate_convention` is required and must be `effective_apy` (the stated APY is an annual effective yield) or `nominal_annual_rate` (daily rate is annual rate / 365). Supply only one closing eligible balance for every calendar day in the accrued period, in ascending consecutive date order. `actual_interest` and `actual_apy_pct` are optional; use the latter when the statement provides it.

The output gives the chosen checking/card candidates, component APYs, expected unrounded and rounded interest, comparison to posted interest, and a report-ready flag. The script rejects missing/duplicate/nonconsecutive dates, invalid values, missing rate convention, or a nonpositive total APY.

Example invocation by the execution runtime:

```text
run_skill_script(relative_path="scripts/calculate_interest.py", input_json=<assembled investigation JSON>)
```

### Validation before action

- Confirm the selected checking candidate is eligible for the specific savings product; an account name alone is not enough.
- Confirm inactive/closed cards and checking accounts are excluded for the disputed period.
- Confirm each candidate category uses a maximum, not a sum.
- Confirm account IDs, APY percentages, and daily dates in the output match the statement evidence.
- Use the calculator’s rounded `amount_difference` only after independently confirming its posted-interest input and rate convention. A zero or negative difference is not a credit.
- Do not submit a discrepancy report based solely on estimates, incomplete balance history, or unverified identity.

## Missing data and failure handling

If the customer has no statement period or interest date, use account history to identify it. If history cannot establish the accrual period, daily balances, linkage, historical rate, or actual applied APY, explain the limitation and request the relevant statement/history; do not estimate a correction. If a banking tool fails, do not proceed to the next dependent step and do not state that it completed.
