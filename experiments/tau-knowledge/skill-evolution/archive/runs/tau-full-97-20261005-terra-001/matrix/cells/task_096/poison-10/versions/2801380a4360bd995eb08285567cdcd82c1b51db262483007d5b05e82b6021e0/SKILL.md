---
name: investigate-savings-interest-discrepancy
description: Investigate a claimed interest-credit discrepancy on a personal Bronze or Gold Plus savings account. Use when a customer asks why posted monthly interest differs from expectations, including possible linked-checking and credit-card APY bonuses. Calculates only from verified account, linkage, transaction, and daily-balance data; performs the documented correction and report sequence only for a confirmed undercredit.
---

# Savings Interest Discrepancy Investigation

## Scope and rules captured in this package

Supported products are personal **Bronze** and **Gold Plus** savings accounts. Both compound interest daily and credit accrued interest monthly. Rates and documented bonus rules are in `references/interest_apy_rules.json`.

* Add the base APY, the single highest eligible active credit-card bonus, and the single highest applicable linked-checking boost.
* Credit-card bonuses do not stack with one another, but the selected card bonus stacks with a checking boost.
* Checking boosts do not stack with one another.
* A checking account must be a qualifying pairing and actually linked to the investigated savings account under the same customer profile. Merely owning a checking account does not establish linkage.
* Do not assume a bonus for a product/card/checking combination omitted from the packaged evidence. The resolver flags qualifying pairings whose percentage is unavailable.
* An approximate current balance or a rounded monthly credit is insufficient to prove a discrepancy. The exact interest period, posted interest entry, eligible daily balance history, and actual applied APY (or auditable equivalent) are needed.

### Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime script interfaces

Scripts receive one JSON object through standard input and emit one JSON object through standard output. They use only the Python standard library. Invoke them with the package runtime's `run_skill_script` capability.

### `scripts/resolve_apy.py`

Determine documented APY components after the account and relationships have been verified.

Input:
```json
{
  "savings_product": "Bronze Account or Gold Plus Account",
  "active_cards": ["verified active card product names"],
  "linked_checking_products": ["verified checking products linked to this savings account"]
}
```

Output includes base APY, every recognized candidate, the selected highest card and checking amounts, `expected_apy_percent`, and `unresolved_qualifying_checking_products`. Do not use `expected_apy_percent` operationally if `ready_for_rate_determination` is false.

A runnable invocation pattern is `run_skill_script` with `relative_path` `scripts/resolve_apy.py` and the verified runtime JSON object above. Empty card and checking arrays are valid when the account review confirms none.

### `scripts/calculate_daily_interest.py`

Calculate a credit from complete period daily eligible balances and a known APY.

Input:
```json
{
  "annual_apy_percent": "resolved APY percentage",
  "daily_balances": ["one eligible principal balance for every calendar day in the credit period"],
  "posted_interest": "optional posted credit amount",
  "day_count": 365,
  "rate_basis": "apy_effective"
}
```

`daily_balances` may instead contain objects with `balance` and optional ISO `date`. `rate_basis` is `apy_effective` by default, using daily rate `(1 + APY)^(1/365) - 1`; use `nominal_annual_rate` only if the account disclosure or ledger explicitly says the displayed rate is nominal. The script compounds accrued interest daily and rounds the final period credit to cents using half-up rounding. It returns `difference_expected_minus_posted` when a posted amount is supplied; a positive value is a potential undercredit.

Before relying on a result, confirm the history covers every day in the posting period, reflects eligible balances and effective transaction dates, uses the disclosed rate basis, and that ledger rounding has been considered. If any check fails, the result is an estimate only and no correction is authorized.

## End-to-end procedure

1. **Authenticate before account access or action.** Treat an email or account identifier used to locate a record as a lookup lead, not proof of identity. Obtain and independently match at least two of date of birth, email, phone number, and address against the user record without disclosing undisclosed values. Obtain the current timestamp and call `log_verification` with the complete required record only after the two-field match. Confirm the requester is the account holder or otherwise authorized.

2. **Locate and validate the accounts.** Unlock and use `get_all_user_accounts_by_user_id_3847` using the verified user ID. Identify the personal Bronze and/or Gold Plus savings account IDs, account status, ownership, product type, and all linkage fields. Exclude business products and closed/ineligible accounts. For each claimed linked checking account, verify the same-profile relationship and linkage to the particular savings account; do not infer it from a customer statement or common ownership.

3. **Collect card and posting evidence.** Obtain the customer's active credit-card accounts after authentication (using the available card-account lookup). Include only active same-profile cards. Unlock and use `get_bank_account_transactions_9173` according to its revealed schema for each investigated savings account. Identify the exact monthly interest-credit transaction, its amount, date, interest period, actual applied APY if present, and the complete balance/ledger history needed for each day of that period. Do not confuse maintenance fees or other transactions with interest.

4. **Resolve the expected APY.** Pass only verified active card product names and verified linked checking product names to `scripts/resolve_apy.py`. Review the returned candidates: select only the highest card amount and highest checking amount. Stop and seek the missing product documentation if the resolver reports an unresolved qualifying checking rate. Record the base rate, selected bonuses, expected APY, and source evidence.

5. **Calculate and establish whether there is a discrepancy.** Pass the resolved APY and the complete daily eligible balances to `scripts/calculate_daily_interest.py`. Compare its rounded expected credit with the exact posted interest transaction. Compare actual versus expected APY only when the actual APY is explicitly present in the statement/ledger or can be reproducibly derived from complete data. Consider account opening/closure, partial periods, balance changes, eligibility changes, transaction effective dates, and disclosed rounding before calling a difference an error.

6. **No proven discrepancy.** If data are incomplete, do not credit or report. Tell the customer explicitly: **“I cannot confirm an interest shortfall or calculation error from the available records.”** State that daily compounding and fluctuating balances can make a rough balance-based estimate differ from the monthly credit. Name the missing evidence: the credited interest period, daily eligible balance/ledger history, actual applied APY, and confirmation of the specific savings-to-checking linkage and selected boost. Do not say or imply that a qualifying checking boost was applied or omitted when linkage is unverified. If the calculation matches after rounding, explain the base APY, selected bonuses, daily compounding, and monthly crediting. Do not make a banking change.

7. **Confirmed undercredit remediation.** A confirmed undercredit requires all of: completed identity/authority verification; verified account ownership and product eligibility; target savings account ID; exact interest entry; complete period balances; resolved expected and actual APYs; a positive cent-rounded shortfall; and review of relevant account status, available balance/credit, fees, limits, cutoffs, recipient/card details, and confirmation requirements. For a savings credit, recipient/card details are not applicable, but explicitly record that assessment.

   Unlock `apply_savings_account_credit_6831` and inspect its schema. Apply the positive, cent-rounded credit to the verified savings account **before** reporting. Then unlock `submit_interest_discrepancy_report_7294` and submit the report using its documented fields: `account_id`, `user_id`, `expected_apy`, `actual_apy`, and `amount_difference`. Use the exact values established in the investigation, not approximations. Preserve the tool receipts/reference IDs in the case notes and tell the customer that the credit resolves the monetary shortfall while the report investigates the root cause.

8. **Unsupported or unsafe outcomes.** Do not debit an account, reverse an apparent overcredit, invent an APY, apply a guessed correction, or submit a report with fabricated actual APY or amount. If the required lookup/correction/report tool is unavailable, linkage/rate evidence cannot be obtained, or an overcredit needs handling outside the documented credit-and-report path, document the evidence and transfer/escalate under the available technical-system-error or specialized-department process. If the customer asks for specialist review, arrange the transfer and summarize the investigated accounts, posted credits, confirmed card findings, unresolved linkage, and the missing interest-period, daily-balance, and applied-APY evidence.

## Customer-facing explanation template

State the verified account product and interest-credit period; list the base APY, highest applied card bonus, and highest linked-checking boost only when each is verified; then explain that interest compounds daily and posts monthly. Distinguish a preliminary estimate from a confirmed calculation. When evidence is incomplete, use clear language such as: “I cannot confirm a shortfall or calculation error yet, so no adjustment was made. The specialist will review the daily eligible balances, credited period, applied APY, and savings-to-checking linkage.” Never expose card numbers, full identity attributes, internal user IDs, or unverified linkage details.
