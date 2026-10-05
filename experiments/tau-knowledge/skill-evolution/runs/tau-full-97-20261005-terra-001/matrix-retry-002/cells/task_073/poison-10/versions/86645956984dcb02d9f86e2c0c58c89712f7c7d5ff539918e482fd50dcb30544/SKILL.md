---
name: audit-atm-fees-and-correct-checking-fee-mischarges
description: Review a verified customer's Blue, Green, and Light Green checking-account ATM fees for a requested month, calculate documented bank-fee expectations, identify supportable fee mischarges or missing Rho Bank Plus operator-fee reimbursements, and safely prepare one permitted combined checking-account credit when eligible.
---

# Audit ATM Fees and Correct Eligible Checking-Account Mischearges

Use this Skill when a customer asks why ATM fees look high or asks for a review of ATM fees on Blue, Green, or Light Green checking accounts. It supports a read-only investigation first. A credit is permitted only for a documented checking-account fee mischarge or a missing eligible rebate.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Apply the relevant prerequisites before each action. For transaction-history review, verify identity, authority, and ownership before disclosing activity. For a credit, additionally confirm the account is an eligible checking account, the exact correction, applicable fees and limits, account status and balance, and the required confirmation. Do not disclose an account's activity or make a credit merely because a name, email, or date of birth was supplied without completing verification.

## Required tools and sequence

1. **Verify identity and authority.** Compare at least two customer-provided identity fields among date of birth, email, phone number, and address to the customer record. A name alone is not sufficient. After successful comparison, obtain the current timestamp and call `log_verification` with the complete returned customer record and timestamp.
2. **Find the customer's bank accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified user ID. Confirm that each account under review belongs to this customer, is a checking account, and identify its account ID, account class/product, status, balance, and opening date. Do not assume that an account named by the customer exists or is owned by them.
3. **Retrieve account activity.** Unlock and call `get_bank_account_transactions_9173` for each verified checking account being reviewed. Records are reverse chronological and include posted and pending entries. Retain all transactions in the requested calendar month, including `atm_withdrawal`, `atm_fee`, `fee_rebate`, `rebate_credit`, and `fee_refund` records.
4. **Collect or infer only supported facts.** For every questioned fee, identify its matching withdrawal, date, cash amount (USD equivalent for foreign withdrawals), whether it was foreign or domestic out-of-network, and whether the line is the bank's ATM fee or an ATM-operator fee. Do not classify an ambiguous description as foreign, out-of-network, bank, or operator fee. Ask for a receipt/location or explain that the entry cannot be conclusively assessed when the history does not establish this.
5. **Run the packaged audit.** Normalize the transaction data and pass it to `scripts/atm_fee_audit.py`. The script is an arithmetic and consistency aid; it never accesses bank systems, verifies a customer, or performs a credit.
6. **Explain the result.** Explain the matching withdrawal, expected bank fee, actual bank fee, and any separately charged operator fee. Pending fees can be discussed but are not a basis for a correction until posted and fully supported.
7. **Only if a credit is supported, perform the credit procedure below.** Otherwise, do not call the credit tool. If records are ambiguous, operator fees are not demonstrably reimbursable, or a prior correction cannot be ruled out, state what information is needed rather than estimating.

## Fee rules used by the audit

Only the bank fee is evaluated against the checking-account fee rules. ATM-owner/operator fees are separate and must not be called bank-fee mischarges.

| Product | Withdrawal classification | Expected bank fee |
|---|---|---:|
| Blue Account | Domestic out-of-network | 1% of withdrawal, capped at $3.00 |
| Blue Account | Foreign | Greater of 3% of USD-equivalent withdrawal or $5.00 |
| Green Account | Domestic non-network | $3.00 per withdrawal |
| Green Account | Foreign | Greater of 3% of USD-equivalent withdrawal or $5.00 |
| Light Green Account | Domestic out-of-network | First four in a calendar month free; $1.50 each thereafter |
| Light Green Account | Foreign | $2.00 through $100; $3.50 over $100 through $300; $5.00 over $300, per withdrawal |

For Light Green domestic withdrawals, retrieve and include the whole calendar month's domestic out-of-network withdrawals so the first-four count is correct. A withdrawal exactly at a Light Green foreign tier threshold receives the lower tier. The evidence does not establish a bank charge for in-network withdrawals; do not infer one.

Rho Bank Plus may reimburse eligible **ATM-operator** fees up to $32 per month. It does not reimburse currency-conversion charges or other third-party charges. Treat a missing reimbursement as supportable only when active membership, fee eligibility, the actual operator-fee lines, the calendar-month cap, and applied reimbursements can all be verified from supplied records. Do not treat an unclassified `atm_fee` as an eligible operator fee.

## Script interface

Run `scripts/atm_fee_audit.py` with one JSON object on standard input. It writes one JSON object to standard output.

Input schema:

- `review_month` (required): calendar month as `YYYY-MM`.
- `accounts` (required): array of account objects with `account_id`, `account_type`, `account_class` or `product`, and optional `status` and `balance`.
- `transactions_by_account` (required): object mapping each account ID to its complete month transaction array. A transaction has at least `transaction_id`, `date` (`MM/DD/YYYY`), `amount`, `type`, and `status`.
- `fee_context` (optional): object keyed by ATM-fee transaction ID. Each supported assessment needs `withdrawal_transaction_id`, `withdrawal_classification` (`domestic_out_of_network` or `foreign`), and `fee_component` (`bank_fee` or `operator_fee`). For an operator-fee reimbursement review, add `operator_fee_eligible: true` only when eligibility is documented.
- `correction_by_fee_id` (optional): verified prior correction mapping keyed by fee ID. Values contain a nonnegative `amount` and a transaction identifier. Supply this only after confirming the prior credit actually corrected that fee.
- `rho_bank_plus` (optional): use `{ "active": true, "known_reimbursement_credits": [{"transaction_id": "...", "amount": "..."}] }` only when membership and the listed reimbursement credits are verified. Omit it if either is unknown.
- `as_of` (optional): `YYYY-MM-DD`, used to flag a recent account credit that may indicate the documented 14-day cooldown.

Example invocation structure (replace all placeholders with runtime data):

```sh
python3 scripts/atm_fee_audit.py <<'JSON'
{"review_month":"YYYY-MM","accounts":[...],"transactions_by_account":{"ACCOUNT_ID":[...]},"fee_context":{"FEE_TRANSACTION_ID":{"withdrawal_transaction_id":"WITHDRAWAL_TRANSACTION_ID","withdrawal_classification":"foreign","fee_component":"bank_fee"}}}
JSON
```

Validation behavior: malformed dates, invalid money, unsupported products, missing account transaction arrays, missing fee context, unmatched withdrawals, and ambiguous categories are returned in `validation_errors` or as an `unassessable` fee result. Such results must not be used to apply a credit. `credit_candidates` includes only posted, supported bank-fee overcharges not already mapped to a verified correction; it remains a recommendation requiring the operational checks below.

## Credit procedure and safeguards

The available tool is `apply_checking_account_credit_5829(account_id, amount, credit_type)`. It can be called only once per checking account per interaction and the system enforces a 14-day cooldown. It accepts a positive exact amount and only `fee_refund` or `rebate_credit`.

Before any call:

1. Reconfirm verified identity, authority, account ownership, checking account type, account status, balance, applicable product fee schedule, recipient/account details, limits, cooldown risk, and confirmation requirements.
2. Confirm every claimed discrepancy in transaction history, that it is posted, that its amount is exact, and that no prior fee refund, rebate, or other correction already resolved it. Review all corrections and rebates in the history; do not rely solely on a transaction type or the script's inference.
3. For a Rho Bank Plus reimbursement, confirm active membership, the operator fee (not a conversion/other third-party fee), its eligibility, all reimbursement credits already applied that month, and the $32 monthly cap.
4. Sum every unresolved eligible correction for the same account into one exact positive amount. If both correction categories are needed, choose the credit type that applies to the majority of the combined correction amount; if neither category is a majority, obtain supervisor guidance rather than guessing.
5. Obtain the customer's required confirmation immediately before the credit call. If the account has a recent credit, prior correction, uncertain cooldown, ineligible status, incomplete evidence, or any system rejection, do not retry or split the credit.
6. Call the credit tool once for that account. Report the returned transaction and updated balance if supplied. Document the reviewed entries, calculation, selected credit type, exact amount, and confirmation.

Never credit savings or other non-checking accounts. Never issue goodwill credits for fees that are merely surprising, estimates, ATM-operator charges that lack verified Plus eligibility, or anything outside a missing eligible rebate or fee mischarge.
