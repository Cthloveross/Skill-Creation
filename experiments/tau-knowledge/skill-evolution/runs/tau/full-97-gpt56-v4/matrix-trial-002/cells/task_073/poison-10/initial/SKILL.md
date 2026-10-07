---
name: atm-fee-review-and-correction
version: 1.0.0
description: Review ATM fees on a customer's Blue, Green, or Light Green checking accounts using account and transaction-history tools; calculate documented bank fees, distinguish operator charges and conditional membership reimbursements, and apply a permitted exact correction only after all prerequisites are verified.
---

# ATM Fee Review and Correction

Use this Skill when a customer asks to explain or review ATM withdrawal fees, including a request to correct a fee on a Blue, Green, or Light Green checking account. It supports review and calculation; it does not itself execute banking actions.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Tool and identity workflow

1. Identify the customer using a supplied profile identifier, such as email or name, with the ordinary profile lookup tool.
2. Verify identity before retrieving account information or taking a correction action. Confirm at least two of the four profile fields (date of birth, email, phone number, address) with the customer and ensure they match the returned profile. Do not treat data merely displayed by a lookup as a customer confirmation.
3. Obtain the current timestamp and call `log_verification` with the complete returned profile and that timestamp after successful verification.
4. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Confirm each target account is owned by the verified customer, is an active checking account, and identify its product/class from the returned account information. Do not infer that an account belongs to the customer from a supplied account ID alone.
5. Unlock and call `get_bank_account_transactions_9173` once for each verified target account. It returns reverse-chronological transaction records containing date, description, amount, type, and status. Review all activity covering the requested calendar period, including ATM withdrawals, `atm_fee` records, fee rebates/refunds, and pending transactions. A fee can post separately from its withdrawal, so pair entries only when date, amount, description/location, and sequence reasonably support the pairing.
6. Do not call a correction tool merely because an ATM fee appears high. First classify the ATM transaction, determine whether the observed line is a bank fee or an ATM operator charge, identify any existing rebate/refund, and calculate the exact discrepancy. Keep ambiguous or unpaired entries as unresolved rather than guessing.

For a current, incomplete month, explain that the review is month-to-date and that pending items or later-settling fees can change the final result.

## Fee rules to use

Amounts below are U.S. dollar amounts. For a foreign withdrawal, use the USD-equivalent cash amount that settles, not an ATM terminal's local-currency figure.

| Product | Transaction classification | Expected bank fee |
|---|---|---:|
| Blue | Domestic out-of-network | 1% of withdrawal, capped at $3.00 |
| Blue | Foreign currency ATM | Greater of 3% of USD equivalent or $5.00 |
| Green checking | Domestic out-of-network | $3.00 per withdrawal |
| Green checking | Foreign currency ATM | Greater of 3% of USD equivalent or $5.00 |
| Light Green | Domestic out-of-network | First four in a calendar month free; $1.50 each after that |
| Light Green | Foreign ATM | $2.00 at or below $100; $3.50 above $100 through $300; $5.00 above $300 |
| Any listed product | In-network domestic ATM | No listed bank out-of-network fee |

The foreign-fee rules are assessed per successful withdrawal. For Light Green, thresholds are inclusive at $100 and $300. The documented daily ATM limits are not a substitute for a fee calculation; do not use them to infer that a fee was valid.

ATM owner/operator fees are separate from the bank's ATM fee. Do not label an operator surcharge as a mischarged bank fee. A Rho Bank Plus membership may reimburse eligible out-of-network ATM **operator** fees up to $32 per month, but does not establish that a product's bank fee was wrong. Confirm active membership, eligibility, qualifying operator charges, monthly reimbursement usage, and whether a rebate already posted before considering a missing-rebate correction. If membership status or operator-fee evidence is unavailable, complete the product-fee review but explicitly leave reimbursement eligibility unresolved.

## Calculation helper

Normalize each confidently paired withdrawal and bank-fee observation, then run:

```text
python3 scripts/calculate_atm_fees.py <<'JSON'
{
  "account_product": "blue",
  "transactions": [
    {
      "id": "withdrawal-reference",
      "date": "YYYY-MM-DD",
      "sequence": 1,
      "withdrawal_usd": "125.00",
      "category": "domestic_out_of_network",
      "bank_fee": "1.25"
    }
  ]
}
JSON
```

The script reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

- `account_product`: one of `blue`, `green`, or `light_green`.
- `transactions`: a list of normalized withdrawal records. `date` accepts `YYYY-MM-DD` or `MM/DD/YYYY`; `withdrawal_usd` is a positive USD amount; and `category` is `domestic_out_of_network`, `foreign`, or `in_network`.
- `id` is optional but should be the transaction ID or an internal pairing reference. `sequence` is optional, but provide it to order same-day withdrawals, particularly for Light Green's monthly free-withdrawal count.
- `bank_fee` is optional and must be the positive amount of the **bank's** fee for that withdrawal. Omit it when no confident pairing exists. Do not enter an operator surcharge here.

The result supplies the expected bank fee, supplied actual bank fee when available, and `overcharge` for each record. `recommended_fee_refund_total` is only the sum of confidently observed positive overcharges. A negative difference is an apparent undercharge and is never a reason to debit the customer. `ok: false` means correct the input rather than relying on a partial calculation.

Before relying on the result, validate that every transaction belongs to the reviewed period and account, that foreign amounts are settled USD equivalents, that all Light Green domestic out-of-network withdrawals in the calendar month were included, and that each supplied `bank_fee` is a bank fee rather than an operator charge.

## Correction procedure

A credit is permitted only for a verified missing eligible rebate or a verified fee mischarge, and only to a checking account.

1. Preserve the identity, authority, ownership, checking-product, fee, limit, available-balance/credit, recipient/card-detail, cutoff, and confirmation checks described in the mandatory banking control above.
2. Retain the account-history evidence for every discrepancy and calculate the exact net correction. Exclude unverified membership reimbursements, external operator charges, pending/ambiguous entries, and amounts already refunded.
3. Check all candidate corrections for the same checking account before acting. The credit tool can be called only once per checking account per customer interaction and creates a 14-day cooldown. Combine all confirmed corrections for that account into one exact positive amount.
4. Unlock `apply_checking_account_credit_5829` only after these conditions are satisfied. Call it with the verified checking `account_id`, the exact positive combined amount, and `credit_type` `fee_refund` for a fee correction or `rebate_credit` for a missing rebate. If both types are combined, use the type applying to the majority of the correction items, as required by policy.
5. If there is no confirmed positive discrepancy, do not apply a credit. Explain the fee calculation and any unresolved item instead.
6. After a successful credit, report the account reviewed, amount and credit type applied, reason, and resulting balance returned by the tool. Never promise a credit before the tool succeeds.

## Customer-facing review output

Give a concise account-by-account table containing the withdrawal date/reference, classification, withdrawal amount, observed bank fee (or “unpaired/unresolved”), expected bank fee, and result. State separately that third-party ATM operator fees are outside the product-fee comparison. Explain any conditional Plus reimbursement item without representing it as approved unless eligibility and missing-rebate evidence were verified. For accounts not found, inactive, not checking, or not owned by the verified customer, state that no review or credit was performed for that account.
