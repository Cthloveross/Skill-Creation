---
name: review-checking-atm-fees
version: 1.0.0
description: Verify a customer, retrieve their checking accounts and transaction history, review ATM-fee and rebate activity under Bluest and Light Green terms, and apply one exact eligible checking-account correction when supported by records.
---

# Review checking ATM fees and rebates

Use this Skill when a verified customer asks why ATM fees or ATM rebates on a Bluest Account or Light Green Account appear incorrect. It supports a transaction-based review and, only where the evidence establishes an eligible correction, a single checking-account credit.

## Policy facts used by this Skill

- **Bluest:** Third-party ATM fees are eligible for rebates up to an aggregate **$50 per monthly statement cycle**. Rebates stop at the cap. Bluest benefits must be active; maintaining the required daily balance of $112,500 is a condition for benefits. A foreign ATM may still charge a third-party operator fee.
- **Light Green domestic out-of-network:** Four withdrawals per month are free; each later out-of-network withdrawal carries a $1.50 bank fee.
- **Light Green foreign:** The bank fee is assessed per individual withdrawal: $2.00 through $100, $3.50 above $100 through $300, and $5.00 above $300. This is separate from an ATM-operator fee. Threshold amounts belong to the lower tier.
- A credit may be made only to a checking account and only for a confirmed missing eligible rebate or confirmed fee mischarge. It must equal the exact correction; do not estimate or round.

## Required agent procedure

1. **Identify and verify the customer before accessing account activity.**
   - Use a customer-provided lookup value to find the user record if needed.
   - Ask the customer to actively confirm at least two of the following four fields: date of birth, email, phone number, and address. Compare their answers with the user record. Do not treat facts merely found in a lookup as customer verification.
   - On successful comparison, get the current timestamp and call `log_verification` with every required field from the matched user record and that timestamp. Do not disclose unconfirmed sensitive fields.
   - If two fields cannot be confirmed, do not retrieve or discuss account-specific transaction activity.

2. **Retrieve the eligible accounts.**
   - Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
   - Limit this review to the customer’s checking accounts that are represented as Bluest or Light Green. Record each account ID, account type/class, status, balance, and opening date returned by the tool.
   - Do not assume an account is checking, active, or a particular product from the customer’s statement alone. Exclude non-checking accounts from any credit.

3. **Retrieve the requested statement-cycle activity.**
   - Unlock and call `get_bank_account_transactions_9173` once for each selected account ID. It returns reverse-chronological records, including dates, descriptions, amounts, types, and posted/pending status.
   - Review the requested month’s posted ATM withdrawals, `atm_fee` entries, and any `fee_rebate`, `rebate_credit`, or `fee_refund` entries. Pending items are not a final fee assessment and should be clearly identified as pending.
   - Use descriptions and transaction relationships to distinguish ATM-operator fees from Rho-Bank fees, domestic from foreign activity, and whether a fee belongs to a particular withdrawal. Never infer a foreign location solely from a dollar amount.

4. **Make a product-specific calculation.**
   - For Bluest, identify the actual third-party ATM fees incurred in the statement cycle and eligible rebate credits already posted. If the daily-balance benefit condition cannot be established for that cycle, explain that eligibility cannot be confirmed and do not call the credit tool. Otherwise, the maximum eligible rebate is the lesser of total confirmed third-party ATM fees and $50. A shortfall after confirmed posted rebates is a candidate missing rebate.
   - For Light Green, calculate domestic out-of-network fees by withdrawal sequence within the cycle: no bank fee for the first four, then $1.50 each. Separately calculate every confirmed foreign withdrawal by its individual cash amount using the three foreign tiers. Compare only linked Rho-Bank fee entries with those expected fees; ATM-operator charges are not an error under these terms.
   - `scripts/analyze_atm_fees.py` can perform the deterministic arithmetic when you provide explicit classifications and links. It intentionally leaves ambiguous transactions unresolved rather than guessing.

5. **Apply a correction only if authorized by evidence.**
   - Before a credit, confirm from the account record that the target is a checking account and from the transaction history that the needed rebate/refund has not already posted.
   - Add all confirmed corrections for the same account into one exact positive total. The credit tool may be called only once per checking account in this interaction and has a 14-day cooldown. Do not retry after a successful call or an uncertain/unknown result.
   - Unlock `apply_checking_account_credit_5829` only after these checks. Call it with the account ID, exact positive amount, and `rebate_credit` for a missing rebate or `fee_refund` for mischarged fees. If both kinds must be combined, use the type corresponding to the majority of the confirmed corrections, as required by policy.
   - If evidence is incomplete, the account is not checking, the issue is not one of these two allowed circumstances, or the applicable benefit eligibility cannot be proven, do not apply a credit. Explain what record or review is still needed. If the customer wants further dispute handling that cannot be resolved from available records, transfer using `complex_billing_dispute`.

6. **Close clearly.** State the account/product reviewed, date range, relevant withdrawals and fee/rebate totals, the governing rule, and whether a correction was applied. If a credit was applied, give its exact amount, reason, and the updated balance returned by the banking tool. Never claim a credit, a fee reversal, or benefit eligibility unless confirmed by the tool records.

## Analyzer interface

Run `scripts/analyze_atm_fees.py` with one JSON object on stdin. It emits one JSON object on stdout.

Input fields:

- `month` (required): statement month in `YYYY-MM` form.
- `accounts` (required): account records containing `account_id` and a product indicator such as `product` or `account_class`.
- `transactions_by_account` (required): object keyed by account ID, with raw transaction arrays from the transaction-history tool.
- `context_by_account` (optional): for a Bluest account, set `bluest_benefits_active` to `true` only when the cycle’s benefit eligibility has been independently established.
- `classifications_by_account` (optional): object keyed by account ID. Under each account supply explicit `withdrawals`, `fee_links`, and `credits` mappings. A withdrawal classification contains `network` (`out_of_network` or `other`) and `location` (`domestic` or `foreign`). `fee_links` maps an ATM-fee transaction ID to its withdrawal transaction ID and optional `fee_scope` (`rho_bank` or `operator`). `credits` maps a credit transaction ID to `atm_rebate` when it is a confirmed ATM rebate. Omit uncertain items.

The output contains per-account evidence totals, expected charges or rebate ceiling where determinable, possible shortfalls/overcharges, and warnings. It is an arithmetic aid, not authority to credit: the agent must still apply the verification, account-type, status, transaction-confirmation, and one-credit safeguards above.
