---
name: audit-november-atm-fees-and-correct-eligible-checking-accounts
description: Review a verified customer's checking-account ATM activity for a requested calendar month, calculate documented Bluest and Light Green ATM fee/rebate corrections, and safely apply at most one eligible combined checking credit per account.
---

# ATM fee and rebate audit

Use this Skill when a verified customer asks to review ATM fees or missing ATM rebates on Bluest and/or Light Green checking accounts. It supports review and calculation; it does not itself call banking tools or apply credits.

## Policy rules encoded by this Skill

- Retrieve the customer's accounts first, then retrieve transaction history for **each checking account**. Transaction history is reverse chronological, so sort it chronologically before applying monthly-count rules.
- Credits are permitted only to checking accounts, only for a documented fee mischarge or a missing documented rebate, and only for the exact net correction. The credit tool accepts a positive amount and only `fee_refund` or `rebate_credit`.
- Only one credit call may be made for a checking account in the interaction; the account then has a 14-day cooldown. Combine all established corrections for that account before calling it.
- Bluest: a Rho foreign-ATM fee should be $0; a Rho out-of-network ATM withdrawal fee is $2 per withdrawal; eligible third-party ATM fees are rebated up to a $50 monthly cap. Third-party/operator fees are distinct from Rho fees.
- Light Green: the first four out-of-network withdrawals in the month are free and later out-of-network withdrawals cost $1.50 each. Foreign Rho fees are per withdrawal: $2.00 at or below $100, $3.50 over $100 through $300, and $5.00 above $300. Foreign/operator classification must be established from activity details; do not assume that every ATM fee has one classification.

## Required operational procedure

1. **Verify identity before account-specific disclosure or any credit.** Obtain and match two of date of birth, email, phone number, and address to the customer record. Once verified, call `get_current_time` and `log_verification` with all fields returned by the user lookup and that timestamp. Do not treat a name alone as an identity factor.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Retain only accounts whose type is checking. Report any non-checking account as ineligible for a credit.
3. Unlock and call `get_bank_account_transactions_9173` once for every checking `account_id`. Preserve all transaction fields, including pending items. For a correction calculation, use posted entries; list relevant pending entries separately and do not credit them as established mischarges or missed rebates.
4. Set the review month from the customer's request (for example, November 2025), not from an assumed statement-cycle date. Inspect descriptions and transaction types to establish each ATM withdrawal, fee, and rebate. Determine whether a fee is Rho/third-party, foreign/out-of-network, and which withdrawal it belongs to only when the activity provides support.
5. Create the JSON input for `scripts/audit_atm_fees.py` and run it. The script sorts dates, uses exact decimal cents, calculates only supported corrections, and identifies missing facts that block an account-level credit recommendation.
6. Review the script output with the transaction history. It is safe to explain all activity, including ordinary correctly charged fees. Never infer a fee's network, foreign, operator, or withdrawal linkage merely because an entry says “ATM.” If material classification, withdrawal linkage, earlier-month withdrawal count, or rebate linkage is not supported, explain the limitation and obtain the needed transaction detail rather than applying a credit.
7. For an account with `ready_for_credit: true`, verify again that it is a checking account and that the correction components exactly match the activity. Unlock `apply_checking_account_credit_5829` and make exactly one call using the script's positive `credit_amount` and `credit_type`. Do not call it for `manual_review`, `no_correction`, a zero amount, a savings account, or a tie in correction types.
8. Explain the reviewed transactions, any correction applied, its reason, and the updated balance returned by the banking tool. If a tool fails or the tool indicates the cooldown, do not retry the credit call; explain that no additional credit was applied.

## Handling correction types

The script counts established correction components by type. If one type is the majority, use it for the one combined credit. If the counts are tied, the provided policy supplies no tie-breaking credit type. Do not guess or make the credit; obtain authoritative handling before any action. A fee refund component is a charged Rho fee above its documented amount. A rebate credit component is the supported shortfall between eligible Bluest third-party fees (capped at $50) and supported ATM rebate credits already posted for the month.

## Script interface

Run:

```text
python scripts/audit_atm_fees.py <<'JSON'
{
  "review_year": 2025,
  "review_month": 11,
  "accounts": [{"account_id": "...", "account_type": "checking", "account_class": "Bluest Account"}],
  "transactions_by_account": {"...": [{"transaction_id": "...", "date": "11/03/2025", "description": "...", "amount": -2.0, "type": "atm_fee", "status": "posted"}]},
  "annotations": [{"account_id": "...", "transaction_id": "...", "kind": "bluest_out_of_network_rho_fee", "withdrawal_id": "..."}]
}
JSON
```

Input is a JSON object on stdin. `accounts` is the account lookup result subset; `transactions_by_account` maps each account ID to its transaction records. `annotations` supplies only facts supported by descriptions/records when raw fields cannot distinguish fee ownership or location. Accepted annotation kinds are:

- `out_of_network_withdrawal`, `foreign_withdrawal` (on an ATM withdrawal)
- `light_domestic_oon_rho_fee`, `light_foreign_rho_fee` (on an ATM fee; include `withdrawal_id`)
- `bluest_foreign_rho_fee`, `bluest_out_of_network_rho_fee`, `bluest_third_party_atm_fee` (on an ATM fee)
- `bluest_atm_rebate` (on a posted rebate transaction)

The script emits one JSON object on stdout containing account findings, established components, unresolved facts, and a credit recommendation only where safe. Dates must be `MM/DD/YYYY`; amounts may be numbers or decimal strings. For reproducibility, validate that every referenced annotation transaction ID is in the corresponding account, each linked withdrawal ID is an in-month posted ATM withdrawal, all selected fee/rebate entries are posted, every expected/actual/difference amount is in cents, and `credit_amount` equals the sum of components. Treat any script `errors` or `manual_review` result as a stop condition for credit application.

The annotations are evidence labels, not assumptions. If records cannot support an annotation, omit it; the script will preserve the uncertainty rather than manufacture a correction.
