---
name: review-atm-fees-and-correct-eligible-checking-accounts
description: Review a verified customer's November (or other specified period) ATM withdrawals, bank ATM fees, and eligible ATM-operator-fee rebates across checking accounts. Use when a customer believes ATM fees or rebates were mischarged and an exact, documented checking-account credit may be warranted.
---

# Review ATM fees and eligible rebates

Use this workflow for a customer-requested review of ATM fee line items. It supports explanation and, only when the evidence establishes an exact correction, a single authorized checking-account credit. Keep a reconciliation worksheet for each account so every fee line and credit is counted once.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required prerequisites

1. Establish the period without silently combining years. If the customer names a month but not a year, after identity verification inspect the returned transaction dates: use that month-year only when the relevant returned records establish one unambiguous year; otherwise ask which year. Review every transaction in the selected calendar month that the account history returns. Do not exclude a posted record merely because its date is later than the clock time used to log verification.
2. Verify identity before retrieving account data or taking an account action. Have the customer provide and confirm two of: date of birth, email, phone number, or street address. Locate the candidate profile with the supplied identifier, compare both fields to the profile, then obtain the current time and call `log_verification` with the complete returned profile values and timestamp. A name, an account-product claim, or a single field alone is insufficient.
3. Confirm authority and ownership by retrieving the customer's account list and ensuring every reviewed account is returned for the verified user. Record account ID, type, class, status, balance, and opening date. Review only checking accounts; a savings or unknown account is never eligible for a credit.
4. Obtain the current account class from the account lookup rather than relying only on the customer's recollection. The product level and status returned for the account are the evidence of its current product. If that lookup says the account has transitioned or identifies a replacement product, identify the replacement/current product before evaluating fees; the Dark Green documentation does not establish a replacement product's fees. An age alone does not override an account lookup that still identifies the current product as Dark Green.
5. Before a credit, establish the exact fee/rebate event, the fee policy, posted status, relevant withdrawal amount and route, monthly usage order, existing credits/rebates, and the exact net amount. Confirm the credit has not already been posted. Check the available balance supplied by account lookup, although no minimum balance is specified for a corrective credit. There is no recipient, transfer cutoff, or card replacement action in this workflow; retain the transaction/card evidence needed to identify the withdrawal. The documented credit procedure has no additional customer confirmation requirement, but because the request may initially be only a review, obtain the customer's confirmation immediately before applying a credit.

## Tool sequence

The account and transaction tools are discoverable. Unlock and call only the tools needed, in this order:

1. `get_all_user_accounts_by_user_id_3847(user_id)` after identity verification to find the customer's accounts and their current product/status/balance.
2. `get_bank_account_transactions_9173(account_id)` for each in-scope checking account. The result is reverse chronological; normalize it to chronological order before counting monthly allowances.
3. Only after all conditions below are satisfied, unlock and call `apply_checking_account_credit_5829(account_id, amount, credit_type)` once for that checking account.

Transactions include date, description, amount, type, and posted/pending status. Treat a positive amount as a credit and a negative amount as a debit. Reconcile every posted `atm_fee` line in the selected month, including lines that do not visibly say “error”; an allowance, percentage, cap, or minimum can make an ordinary-looking amount wrong. Fees and their related cash withdrawals can post on different dates, so do not pair them solely because they occur on the same day. Use descriptions, transaction IDs, posted dates, withdrawal amounts, ATM location/network evidence, and any separately posted operator surcharge to make an auditable association. Treat an `atm_fee` record as a bank-fee candidate unless its description or other evidence identifies it as a separate operator surcharge. Do not reduce an established bank-fee correction merely because a distinct operator-fee rebate posted; instead, exclude only a rebate correction already posted for that same confirmed eligible operator-fee event. Pending transactions are not a final fee mischarge or posted rebate failure.

## Product rules to apply

Separate the bank's ATM fee from an ATM owner's/operator's surcharge. A third-party surcharge is not automatically a bank fee or refundable.

- **Purple Account**: foreign ATM withdrawal fee is $0.00. A domestic out-of-network cash withdrawal has a $2.50 bank fee per withdrawal. Eligible posted ATM-operator fees may be rebated after posting, up to a total of $30 in a month. Confirm eligibility and existing posted rebates; an ATM receipt can support review. Do not treat an operator surcharge as the $2.50 bank fee.
- **Light Blue Account**: two domestic out-of-network ATM withdrawals are free each month; each further domestic out-of-network withdrawal costs $2.50. Separately, two foreign ATM cash withdrawals are free each month; each further foreign withdrawal costs $4.00. Count each allowance chronologically within the relevant month. Operator surcharges remain separate.
- **Evergreen Account**: a domestic out-of-network ATM fee is 1% of the cash amount, capped at $2.50 per withdrawal. A foreign ATM withdrawal fee is 2% of the withdrawal amount with a $3.00 minimum. Operator fees are separate.
- **Dark Green Account**: while the current account lookup identifies the product as Dark Green, the domestic out-of-network fee is 1% of the withdrawal amount with a $1.50 minimum, and the foreign ATM fee is 2.5% of the withdrawal amount capped at $6.00. An in-network withdrawal has no out-of-network fee. The account is intended to transition after the eligibility age; if the lookup instead says it has transitioned or supplies a replacement product, do not apply these legacy terms because the replacement product's fees are not documented.

If route, network status, product class, posting status, fee association, monthly sequence, rebate eligibility, or replacement product is unknown, explain the gap and do not estimate a correction.

## Optional deterministic assessment helper

Use `scripts/assess_atm_fees.py` after normalizing transaction history into one record per established withdrawal/fee association. The script does not retrieve data and never applies a credit.

Run it as:

```sh
python3 scripts/assess_atm_fees.py < assessment-input.json
```

Its stdin must be a JSON object with:

- `account_class`: `purple`, `light_blue`, `evergreen`, or `dark_green` (common `*_account` spellings are accepted).
- `month`: target month as `YYYY-MM`.
- `transitioned`: boolean. Set it to `true` only when account lookup establishes that the account is transitioned/replaced; a customer's age by itself is not sufficient.
- `withdrawals`: an array of normalized records. Each record requires `id`, `date` (`YYYY-MM-DD` or `MM/DD/YYYY`), nonnegative `amount`, `route` (`in_network`, `domestic_out_of_network`, or `foreign`), and `status` (`posted` or `pending`). Include `observed_bank_fee` when an associated bank fee is established. Do not put an operator surcharge in this field.
- Optional Purple-only `operator_fee_events`: posted, confirmed-eligible operator-fee records with `id`, `date`, `amount`, `status`, and boolean `eligible`.
- Optional Purple-only `posted_rebates`: positive amounts of confirmed ATM-operator-fee rebates already posted for the same month's eligible events.

It emits JSON containing per-withdrawal expected/observed fee comparisons, possible overcharges, and the possible missing Purple rebate. `ready_for_manual_review: true` means the data are incomplete or ambiguous and must not be used as an exact credit instruction. The executor remains responsible for confirming that the input covers all relevant transactions and has correctly associated fee line items.

## Decide and act

1. Reconcile all relevant posted fee lines before deciding: one withdrawal can have a bank fee and a distinct operator surcharge, while one fee can never be assigned to more than one withdrawal. Provide a transparent line-by-line explanation: withdrawal, classification, applicable rule, expected bank fee, actual bank fee, separately identified operator surcharge, existing rebate, and any exact discrepancy. Do not classify a separately identified operator surcharge as a bank fee merely because it was posted near a withdrawal.
2. A credit is permitted only for either (a) an incorrectly charged bank fee or (b) a missing eligible rebate. It must be the exact positive net correction. Do not credit an estimate, an unrelated inconvenience, a pending transaction, or an operator surcharge that has not been established as rebate-eligible.
3. Check all correction candidates for that checking account first. The credit tool may be called only once per checking account per customer interaction and then has a 14-day cooldown. Combine all established corrections into one exact credit. Use `fee_refund` if fee-mischarge corrections are the majority; use `rebate_credit` if missing-rebate corrections are the majority.
4. Ask for confirmation of the exact amount and account immediately before the tool call. On success, report the credit type, amount, and returned new balance. If the tool reports a failure or an unknown outcome, do not retry; explain that no further attempt will be made in this interaction and preserve the evidence for follow-up.
5. If no error is found, say so and explain the applicable fees. If evidence is insufficient, ask only for the missing statement/receipt/network or product information, or direct the customer to obtain transaction history through customer service. Never claim a refund was applied unless the credit tool confirms it.
