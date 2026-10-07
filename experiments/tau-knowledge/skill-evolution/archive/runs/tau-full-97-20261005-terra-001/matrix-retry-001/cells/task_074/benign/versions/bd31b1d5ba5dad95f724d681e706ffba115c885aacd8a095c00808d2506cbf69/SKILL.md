---
name: reconcile-november-atm-fees
version: 1.1.0
description: Review a verified customer's checking-account ATM activity for a requested month, reconcile Rho-Bank ATM fees and Purple ATM-operator-fee rebates against the applicable Purple, Light Blue, Dark Green, and Evergreen policies, and apply one exact supported checking-account credit per account.
---

# ATM Fee Reconciliation

Use this Skill when a customer asks to review ATM fees, believes ATM fees or ATM rebates are wrong, or requests a fee correction for Purple, Light Blue, Dark Green, or Evergreen checking accounts. It supports a review and any authorized fee-refund/rebate credit; it does **not** file a debit-card dispute unless the customer subsequently elects to dispute a particular transaction.

## Preconditions and boundaries

1. Identify the customer and verify identity before accessing or acting on account-specific information. An email or name supplied by the customer is one field; obtain and confirm one additional profile field among date of birth, phone number, or address.
2. Retrieve the profile with `get_user_information_by_email`, `get_user_information_by_name`, or `get_user_information_by_id`; compare the two customer-confirmed fields with the returned profile; obtain the time with `get_current_time`; and call `log_verification` with the complete returned profile and timestamp.
3. This Skill evaluates **posted** ATM fees, operator surcharges, and rebates. Explain pending entries, but do not credit them.
4. A third-party ATM operator surcharge is separate from a Rho-Bank ATM fee. Do not refund an operator surcharge merely because it exists. Purple has a separate eligible operator-fee rebate benefit, subject to its monthly cap.
5. Do not infer an ATM's foreign/domestic status, network status, or operator-fee coding from an ambiguous description. Use clear transaction evidence, ATM location/network information, receipts, or ask the customer. Mark that particular question unresolved.
6. A credit may be applied only to an OPEN checking account, only for a confirmed fee mischarge or missing eligible rebate, and only once per account in this customer interaction. The credit must be a positive exact amount. Respect the tool's 14-day cooldown. If the tool rejects the credit, do not retry or substitute an estimate.

## Runtime procedure

### 1. Retrieve accounts and transactions

After verification:

1. Unlock `get_all_user_accounts_by_user_id_3847` and call it with the verified `user_id`.
2. Locate OPEN checking accounts whose product/account class is Purple, Light Blue, Dark Green, or Evergreen. Preserve each returned `account_id`, status, account type, and product/class. Do not assume every named product exists.
3. Unlock `get_bank_account_transactions_9173` and retrieve the full transaction history for each in-scope checking account.
4. Set the requested review month explicitly. If the customer says “November,” use the year supported by the conversation and current time. Do not silently treat a partial current month as a completed statement month.
5. For every relevant withdrawal in the month, reconcile the withdrawal with separately posted `atm_fee` entries, operator surcharges, and `fee_rebate`, `rebate_credit`, or `fee_refund` entries. Histories are reverse chronological, so sort underlying withdrawals chronologically before applying monthly allowances.

Where a fee posts on a nearby date, match it carefully using transaction IDs, dates, amounts, ATM description/location, and settlement information. Include all withdrawals that consume a relevant monthly allowance, including withdrawals with no bank fee.

### 2. Apply the policy

Use `references/atm_fee_policies.md` as the policy source.

- Purple: $2.50 per domestic out-of-network withdrawal; no Rho-Bank foreign ATM withdrawal fee; eligible posted ATM-operator-fee rebates up to $30 monthly.
- Light Blue: domestic out-of-network withdrawals: first two monthly are free, later ones are $2.50; foreign withdrawals: first two monthly are free, later ones are $4.00.
- Dark Green: domestic out-of-network fee is 1% with a $1.50 minimum; foreign ATM fee is 2.5%, capped at $6 per transaction.
- Evergreen: domestic out-of-network fee is 1%, capped at $2.50; foreign ATM fee is 2%, with a $3 minimum per transaction.

For Purple, reconcile Rho-Bank fees independently from optional operator-surcharge rebate evidence. A confirmed Rho-Bank fee mischarge—such as a fee on a foreign withdrawal where Purple's Rho-Bank fee is $0, or an excess over the domestic $2.50 fee—must be included in a `fee_refund` even if an operator surcharge cannot yet be receipt-matched or its rebate eligibility is unresolved. Posted `fee_rebate` transactions are already credits; they do not make independently matched Rho-Bank fee errors ambiguous.

Never credit an uncertain *operator surcharge* or a speculative missing rebate. However, uncertainty about such a separate rebate must not block an exact, independently established bank-fee refund. Because only one credit is available per account per interaction, combine a confirmed missing Purple rebate with confirmed fee refunds only when both components are fully supported; otherwise issue the exact supported bank-fee correction and document the unresolved rebate question.

Do not make a credit decision for an account if a bank-fee item is unclassified, cannot be confidently matched, or a percentage calculation requires an unspecified fractional-cent rounding rule. Use the helper for deterministic allowance and fee calculations.

### 3. Run the helper

`scripts/reconcile_atm_fees.py` reads one JSON object from stdin and writes one JSON object to stdout. It performs no bank actions.

Input schema:

- `account_product`: `Purple`, `Light Blue`, `Dark Green`, or `Evergreen` (`Account` suffix accepted).
- `month`: review month as `YYYY-MM`.
- `account_status`: status returned by the account tool.
- `is_checking`, `identity_verified`, `review_complete`, `one_credit_call_available`: booleans supplied by the executor.
- `events`: one object for each relevant ATM withdrawal occurring in `month`; input order is unrestricted. Each object contains:
  - `withdrawal_date`: `MM/DD/YYYY` or `YYYY-MM-DD`;
  - `amount`: nonnegative cash-withdrawal amount as a decimal string or number;
  - `region`: `domestic`, `foreign`, or `unknown`;
  - `network`: `in_network`, `out_of_network`, or `unknown`;
  - `bank_fee_charged`: total posted, confidently matched Rho-Bank ATM fee, or `null` when matching is unresolved. Use `0` when known absent;
  - `operator_surcharge`: matched third-party surcharge, `0` when known absent, or `null` when unresolved;
  - `operator_fee_eligible`: `true` or `false` when the Purple surcharge's coding and eligibility are known; otherwise `null` or omit;
  - `rebate_received`: posted Purple operator-fee rebate confidently attributable to this surcharge/withdrawal, `0` when known absent, or `null` when unresolved.

All event dates must be in `month`. `review_complete` is true only after relevant posted fee records and allowance-consuming withdrawals have been examined. The helper's output is a recommendation only: retain transaction IDs and reasoning for the customer-facing explanation.

A minimal runnable invocation with no activity is:

```bash
printf '%s' '{"account_product":"Purple","month":"2025-11","account_status":"OPEN","is_checking":true,"identity_verified":true,"review_complete":true,"one_credit_call_available":true,"events":[]}' | python3 scripts/reconcile_atm_fees.py
```

Validate before acting:

- `credit.eligible` must be true.
- `blocking_unresolved` must be empty. `nonblocking_unresolved` may contain only separate Purple operator-surcharge/rebate questions when the recommended credit is a confirmed bank-fee refund.
- `credit.amount` must equal the exact supported sum of bank-fee overcharges and, only when established, missing eligible Purple rebates. It must never be an estimate.
- Zero or negative discrepancies, a non-OPEN/non-checking account, incomplete review, failed verification, unavailable one-call status, or a type tie must not produce a credit.

### 4. Apply a supported correction

Only after validation:

1. Unlock `apply_checking_account_credit_5829`.
2. Make at most one call for that `account_id` during this interaction, with the helper's positive exact `credit.amount` and `credit.credit_type`.
   - Use `fee_refund` when fee-mischarge corrections are the majority of correction items.
   - Use `rebate_credit` when missing-rebate corrections are the majority.
   - If correction types tie, do not guess; document the tie and obtain an authorized determination.
3. If both correction types are confirmed on the same account, combine their exact amounts in this one call as required by the one-call rule.
4. Use the tool result to tell the customer the applied amount and updated balance. State which bank fees or rebates were corrected and distinguish them from third-party operator charges.

If there is no supported discrepancy, explain the applicable allowance, fee, cap, and posted rebate history. If an item cannot be classified or matched, explain what information is needed. Do not defer an independently supported fee refund solely because an unrelated Purple operator-rebate item remains unresolved.

### 5. Disputes

A customer asking for a fee review may only want an explanation or correction. Do not file a dispute unless they elect to dispute a specific identified transaction. If they do, follow the debit-card-dispute requirements separately: obtain the transaction ID, linked OPEN checking account and debit card, timing and customer-information prerequisites, proper category, and all required dispute fields. Do not use this Skill's credit calculation as a substitute for that process.
