---
name: reconcile-november-atm-fees
version: 1.0.0
description: Review a verified customer's checking-account ATM activity for a requested month, reconcile Rho-Bank ATM fees and Purple ATM-operator-fee rebates against the applicable Purple, Light Blue, Dark Green, and Evergreen policies, and safely apply one exact eligible checking-account credit per account when supported.
---

# ATM Fee Reconciliation

Use this Skill when a customer asks to review ATM fees, believes ATM fees or ATM rebates are wrong, or requests a fee correction for Purple, Light Blue, Dark Green, or Evergreen checking accounts. It supports a review and any authorized fee-refund/rebate credit; it does **not** file a debit-card dispute unless the customer subsequently elects to dispute a particular transaction.

## Preconditions and boundaries

1. Identify the customer, then verify identity before accessing or acting on account-specific information. Confirmation of the email supplied by the customer is one verification field; obtain and confirm one additional profile field among date of birth, phone number, or address.
2. Retrieve the profile with `get_user_information_by_email`, `get_user_information_by_name`, or `get_user_information_by_id`, compare the two customer-confirmed fields with the returned profile, obtain the time with `get_current_time`, and call `log_verification` with the complete returned profile and timestamp.
3. This Skill only evaluates **posted** ATM fees, operator surcharges, and rebates. Explain pending entries, but do not credit them.
4. A third-party ATM operator surcharge is separate from a Rho-Bank ATM fee. Do not refund an operator surcharge merely because it exists. Purple has a separate eligible operator-fee rebate benefit, subject to its monthly cap.
5. Do not infer whether an ATM was foreign, in-network, out-of-network, or whether a fee was an operator fee solely from an ambiguous description. Use clear transaction evidence, ATM location/network information, receipts, or ask the customer. Mark an ambiguous item unresolved.
6. A credit may be applied only to an OPEN checking account, only for a confirmed fee mischarge or missing eligible rebate, and only once per account in this customer interaction. The credit must be a positive exact amount. The credit tool's 14-day cooldown must be respected; if the tool rejects the credit because of cooldown or another error, do not retry or substitute an estimate.

## Runtime procedure

### 1. Retrieve accounts and transactions

After verification, unlock and use the account and transaction tools:

1. Unlock `get_all_user_accounts_by_user_id_3847`, then call it with the verified `user_id`.
2. Locate OPEN checking accounts whose product/account class is Purple, Light Blue, Dark Green, or Evergreen. Preserve each returned `account_id`, status, account type, and product/class. Do not assume the customer has every product named.
3. Unlock `get_bank_account_transactions_9173` and retrieve the full transaction history for each in-scope checking `account_id`.
4. Set the requested review month explicitly. If the customer says “November,” use the year supported by the conversation/current date; do not silently treat a partial current month as a completed statement month.
5. For every relevant withdrawal in that month, reconcile the ATM withdrawal with its separately posted `atm_fee` entry, any separately posted operator surcharge, and any `fee_rebate`, `rebate_credit`, or `fee_refund` entry. Transaction history is reverse chronological, so sort underlying withdrawals chronologically before applying monthly free-withdrawal allowances.

If records show a fee posted in the review month for a withdrawal on a nearby date, match it carefully using the transaction IDs, dates, amounts, ATM description/location, and settlement information. Include all withdrawals that consume the relevant monthly allowance, even when no bank fee was charged.

### 2. Apply the policy

Use `references/atm_fee_policies.md` as the policy source. In brief:

- Purple: $2.50 for each domestic out-of-network withdrawal; no Rho-Bank foreign ATM withdrawal fee; eligible ATM-operator-fee rebates up to $30 per month.
- Light Blue: domestic out-of-network withdrawals: first two monthly are free, later ones are $2.50; foreign withdrawals: first two monthly are free, later ones are $4.00.
- Dark Green: domestic out-of-network fee is 1% with a $1.50 minimum; foreign ATM fee is 2.5%, capped at $6.00.
- Evergreen: domestic out-of-network fee is 1%, capped at $2.50; foreign ATM fee is 2%, with a $3.00 minimum.

Use the supplied helper to make the repeated chronological allowance and fee calculations deterministic. Do not make a credit decision if the review is incomplete, an ATM classification is unknown, a charged fee is not confidently matched, or a percentage calculation would require an unspecified fractional-cent rounding rule.

### 3. Run the helper

`scripts/reconcile_atm_fees.py` reads one JSON object from stdin and writes one JSON object to stdout. It performs no bank actions.

Input schema:

- `account_product`: `Purple`, `Light Blue`, `Dark Green`, or `Evergreen` (the word `Account` is accepted).
- `month`: review month as `YYYY-MM`.
- `account_status`: account status returned by the account tool.
- `is_checking`, `identity_verified`, `review_complete`, `one_credit_call_available`: booleans supplied by the executor.
- `events`: chronological order is not required. Each event represents one ATM withdrawal occurring in `month` and contains:
  - `withdrawal_date`: `MM/DD/YYYY` or `YYYY-MM-DD`;
  - `amount`: cash withdrawal amount as a nonnegative decimal string/number;
  - `region`: `domestic`, `foreign`, or `unknown`;
  - `network`: `in_network`, `out_of_network`, or `unknown`;
  - `bank_fee_charged`: total posted Rho-Bank ATM fee confidently matched to that withdrawal, or `null` if unresolved;
  - `operator_surcharge`: total posted third-party surcharge matched to the withdrawal. Use `0` when known absent; use `null` when unresolved;
  - `operator_fee_eligible`: whether that surcharge is confirmed eligible for Purple's rebate benefit;
  - `rebate_received`: posted Purple ATM-operator-fee rebates confidently attributable to this surcharge/withdrawal. Use `0` when known absent; use `null` when rebate matching is unresolved.

All event dates must be in `month`. `review_complete` is true only after all relevant posted items and allowance-consuming withdrawals have been examined. The helper's `credit` output is a recommendation only; the executor must independently preserve transaction IDs and reasoning for the customer-facing explanation.

A minimal runnable invocation with no activity is:

```bash
printf '%s' '{"account_product":"Purple","month":"2025-11","account_status":"OPEN","is_checking":true,"identity_verified":true,"review_complete":true,"one_credit_call_available":true,"events":[]}' | python3 scripts/reconcile_atm_fees.py
```

Validate before acting:

- `unresolved` must be empty.
- `credit.eligible` must be true before considering a credit.
- The returned `credit.amount` must equal the sum of confirmed overcharged bank fees plus confirmed missing eligible Purple rebate(s), never an estimate.
- A result with zero, a negative discrepancy, an account that is not OPEN checking, incomplete review, failed verification, or unavailable one-call status must not produce a credit.

### 4. Apply a supported correction

Only after the above validation:

1. Unlock `apply_checking_account_credit_5829`.
2. Make at most one call for that `account_id` during this interaction, with the helper's positive exact `credit.amount` and its appropriate `credit.credit_type`.
   - Use `fee_refund` when fee-mischarge corrections are the majority of the correction items.
   - Use `rebate_credit` when missing-rebate corrections are the majority.
   - If there is a tie between correction types, do not guess; document the tie and select the type only after an authorized determination.
3. If both kinds occur on the same account, combine the exact amounts into that one call, as required by the one-call rule.
4. Use the tool result to tell the customer the applied amount and updated balance. State which fees/rebates were corrected and distinguish bank fees from third-party operator charges.

If there is no supported discrepancy, explain the applicable allowance, fee, cap, and posted rebate history. If an entry cannot be classified or matched, explain what information is needed rather than issuing credit.

### 5. Disputes

The customer in a fee-review interaction may only want an explanation or correction. Do not file a dispute unless they elect to dispute a specific identified transaction. If they do, follow the debit-card-dispute requirements separately: obtain the transaction ID, linked OPEN checking account and debit card, timing and customer-information prerequisites, proper category, and all required dispute fields. Do not use this Skill's credit calculation as a substitute for that process.
