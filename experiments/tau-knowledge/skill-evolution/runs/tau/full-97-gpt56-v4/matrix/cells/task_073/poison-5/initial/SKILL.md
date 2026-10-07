---
name: atm-fee-review-and-checking-credit
version: 1.0.0
description: Review reported ATM fees on Blue, Green, and Light Green checking accounts, distinguish bank fees from ATM-operator fees, identify exact documented fee mischarges or missing eligible Rho Bank Plus operator-fee reimbursements, and apply at most one authorized checking credit per account when all prerequisites are verified.
---

# ATM Fee Review and Checking Credit

Use this Skill when a customer asks to explain or challenge ATM fees on a checking account. It supports a historical review; it does not authorize speculative refunds, credits to savings, or reimbursement of third-party charges that are not documented as eligible.

## Guardrails and prerequisites

Before **any** account lookup, transaction lookup, or credit action:

1. Verify the caller's identity by having them confirm two of the four identity fields (date of birth, email, phone number, address) and compare them with the customer record. A name or an unverified identifier alone is not sufficient.
2. Obtain the current timestamp with `get_current_time` and call `log_verification` with the complete matching customer record and that timestamp.
3. Confirm the customer owns the account and is authorized to discuss it. Only active checking accounts owned by the verified customer may be reviewed for a credit.
4. Confirm the requested statement period. If “November” could refer to more than one year, ask which year; do not infer it solely from an account opening date.

The customer may be informed about general published fees without authentication, but do not disclose account-specific information or perform the review until the above checks are complete.

## Retrieve the records

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user's ID. Record account ID, account type, account class, status, balance, and opening date.
2. For every active customer-owned checking account relevant to the request, unlock and call `get_bank_account_transactions_9173(account_id)`.
3. Filter the requested period and preserve the source transaction IDs, dates, descriptions, amounts, types, and statuses. Review posted and pending records separately; do not treat a pending charge as settled or credit it unless the documented policy permits it.
4. Identify each successful ATM withdrawal and the associated bank ATM-fee entry, any ATM-operator fee, and any `rebate_credit` or `fee_refund`. Association must be supported by date, amount, description, and/or transaction identifiers. If entries cannot reliably be associated, explain the limitation and do not calculate or credit an assumed difference.
5. Establish the account class **at the time of each withdrawal**. Do not treat a current Blue/Green class as proof that a historical withdrawal used that product. In particular, a customer who has aged out of Light Green may have converted. If the available records do not establish the historical class, seek a reliable account-history record or leave that item unresolved.
6. If Rho Bank Plus reimbursement is raised, verify active membership for the review month and the relevant membership charge or account record. The available account and transaction tools do not themselves establish subscription status; do not assume membership from a customer's recollection.

## Fee rules to apply

Compare only the Rho-Bank bank fee with the rule for the verified product and transaction classification. ATM-owner/operator charges are separate.

| Product and transaction | Correct Rho-Bank fee |
|---|---:|
| Blue, domestic out-of-network ATM | 1% of withdrawal amount, capped at $3.00 |
| Blue, foreign-currency ATM | greater of 3% of USD-equivalent cash amount or $5.00 |
| Green, domestic out-of-network ATM | $3.00 per withdrawal |
| Green, foreign-currency ATM | greater of 3% of USD-equivalent cash amount or $5.00 |
| Light Green, domestic out-of-network ATM | First four such withdrawals in the calendar month are free; $1.50 each thereafter |
| Light Green, foreign ATM | $2.00 up to and including $100; $3.50 above $100 through and including $300; $5.00 above $300, per withdrawal |

For foreign withdrawals, use the USD-equivalent cash amount that settled. Do not add a domestic out-of-network fee to the applicable foreign-fee rule. Do not count an ATM operator's own fee as a bank fee mischarge.

Rho Bank Plus costs $4.99 monthly and can reimburse **eligible out-of-network ATM operator fees**, up to $32 for the month. It does not make the product's own ATM fee disappear. Currency conversion and other third-party charges may be ineligible. Verify membership, fee eligibility, prior reimbursements, and the remaining monthly cap before finding a missing rebate.

Use `scripts/assess_atm_fees.py` after manually normalizing the supported transaction associations. It performs deterministic arithmetic only and never calls banking tools or authorizes a credit.

## Credit decision and execution

A credit is permitted only for either:

- a documented bank-fee mischarge, or
- a documented missing rebate for which all eligibility conditions are met.

For each eligible checking account:

1. Review the full transaction history for already-applied rebates/refunds and any recent credit that would prevent another credit. The credit tool may be called only once per checking account in the interaction and imposes a 14-day cooldown.
2. Calculate every supported correction exactly to cents. A fee refund is only the positive overcharge (`actual bank fee - correct bank fee`). A missing rebate is only the eligible reimbursement less the associated amount already credited. Do not round, estimate, or credit undercharges.
3. If multiple supported corrections exist on the same account, combine their amounts into one credit. Select `fee_refund` or `rebate_credit` according to the type that applies to the majority of corrections, as required by policy. If there is no majority, do not guess a credit type; resolve through the authorized internal process before acting.
4. Confirm the account is a checking account immediately before action. Then unlock and call `apply_checking_account_credit_5829(account_id, amount, credit_type)` once, with a positive exact amount.
5. If the call fails or its outcome is unknown, do not retry. Report that the adjustment was not confirmed and follow the applicable internal escalation process.
6. On confirmed success, state the precise amount, reason, affected account, and resulting balance returned by the system. Do not claim an adjustment was made before the tool confirms it.

If the review shows all fees and rebates were correct, explain the applicable fee and distinguish bank and operator charges. If records, classification, membership status, or fee associations are missing, explain what prevented a determination and request the needed statement/account details; do not apply a courtesy credit.

## Script interface

Run:

```sh
python3 scripts/assess_atm_fees.py <<'JSON'
{"period":"YYYY-MM","membership":{"verified":true,"active":true,"cap":"32.00"},"accounts":[...],"withdrawals":[...]}
JSON
```

The script reads one JSON object from standard input and emits one JSON result to standard output. `accounts` must contain the reviewed account IDs and their historically verified product class. Each `withdrawals` item must contain `id`, `account_id`, `date`, `network`, `withdrawal_usd`, and `bank_fee_charged`; use `network` values `domestic_out_of_network` or `foreign`. Add `sequence` when multiple Light Green domestic withdrawals occur on the same day. For an operator-fee reimbursement review, also supply `operator_fee`, `operator_fee_eligible`, and `operator_reimbursement_applied`.

Validate that the output has no `errors` and no `review_required` entries before using any proposed correction. Preserve the source transaction IDs outside the script result for audit documentation. The script's `account_summaries` are recommendations, not bank actions.
