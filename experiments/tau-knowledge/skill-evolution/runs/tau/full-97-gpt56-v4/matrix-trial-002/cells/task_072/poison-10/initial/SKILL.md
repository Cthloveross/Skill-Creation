---
name: review-atm-fees-and-correct-checking-account-errors
description: Securely review a verified customer's ATM fee and rebate activity for checking accounts, explain applicable Bluest and Light Green rules, and apply one exact eligible correction only after transaction evidence establishes a fee mischarge or missing rebate.
---

# Review ATM Fees and Rebates

Use this Skill when a customer believes ATM fees or ATM rebates on a Bluest or Light Green checking account are wrong. It supports investigation, not automatic refunds. It requires account and transaction evidence before concluding that a charge is incorrect.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Preconditions and security

1. Treat the caller as unverified until they independently confirm **two of these four** profile fields: date of birth, email address, phone number, and address. A name alone does not count.
2. Look up the supplied identifier only to locate the profile; do not present profile data as a prompt for the customer to repeat.
3. Once two fields have been independently confirmed against the profile, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete matching profile record and timestamp.
4. Confirm the requester is the customer/account owner. Do not disclose transaction details or perform a credit if identity, authority, or ownership cannot be established.
5. Determine the statement period explicitly. If the customer says only “November,” ask which year; do not assume it from the date of contact.

## Tool workflow

After verification and ownership confirmation:

1. Unlock `get_all_user_accounts_by_user_id_3847` with `unlock_discoverable_agent_tool`, then call it with the verified `user_id` through `call_discoverable_agent_tool`.
2. Confirm each relevant account is an active checking account and identify its product/class as Bluest or Light Green. Do not inspect savings accounts or infer account ownership from a product name.
3. Unlock `get_bank_account_transactions_9173`, then retrieve each relevant checking account's transactions using its `account_id`. Transaction history is reverse chronological and includes posted and pending entries.
4. Restrict the review to the agreed statement period. Keep ATM withdrawals, ATM-fee entries, fee-rebate/rebate-credit entries, descriptions, dates, amount signs, statuses, and any linkage needed to associate a fee with a withdrawal.
5. Review posted entries first. Pending entries may be explained as provisional, but must not be treated as final proof of a mischarge or missing rebate.
6. If data cannot associate a fee to a withdrawal, identify location/foreign status, distinguish Rho-Bank fees from third-party operator surcharges, establish Bluest daily-balance eligibility, or confirm whether a rebate has already posted, explain the gap and request the statement/transaction details. Do not estimate a credit.

Use `scripts/review_atm_fees.py` to make a reproducible preliminary ledger assessment from exported records. The script does not access banking systems, verify identity, determine account ownership, or make credits; the executor still must validate every finding against the actual transaction history.

## Product rules to apply

Apply only the schedule that is supported by the account product and transaction facts:

### Bluest

- Benefits require a daily balance of at least $112,500. Establish eligibility for the relevant period before treating a benefit as available.
- Rho-Bank charges no foreign ATM withdrawal fee. A confirmed Rho-Bank foreign-ATM fee is therefore a candidate fee mischarge.
- Third-party ATM fees are eligible for rebates up to an aggregate $50 per monthly statement cycle. Rebates stop at the $50 cap. Operator fees are not automatically erroneous merely because they were charged.
- A documented out-of-network Rho-Bank ATM charge may be $2 per withdrawal; do not characterize it as an error without determining whether it was foreign and whether the governing rule makes it inapplicable.

### Light Green

- The account includes four free out-of-network ATM withdrawals per month; after the fourth qualifying withdrawal, the Rho-Bank fee is $1.50 per withdrawal.
- Foreign ATM charges are determined separately for each successful foreign withdrawal: $2.00 at or below $100, $3.50 above $100 through $300, and $5.00 above $300. Threshold values use the lower tier.
- Foreign ATM operator charges are separate from Rho-Bank fees. Do not refund an operator charge as a Rho-Bank fee mischarge without documented authorization.

## Deciding and correcting

A credit is permitted only for a **confirmed fee mischarge** or a **confirmed missing rebate**. Before any credit, verify all of the following:

- the account is a checking account;
- the customer is verified and is the account owner;
- the pertinent fee/rebate and related withdrawal are posted and supported by transaction history;
- the governing benefit or fee schedule applies, including balance eligibility and monthly counting/cap rules;
- no matching correction has already posted;
- the exact net correction can be calculated without rounding or estimates; and
- no prior credit has been applied in this interaction or within the tool-enforced 14-day cooldown.

If multiple confirmed corrections exist on one checking account, combine them into one exact net amount. Unlock `apply_checking_account_credit_5829` and call it at most once for that account and interaction, using a positive amount and either `fee_refund` (majority fee corrections) or `rebate_credit` (majority missing rebates). Never credit savings or an unsupported dispute. After a successful credit, report the amount, reason, and the updated balance returned by the normal banking tool.

If the evidence is insufficient, provide a concise review summary, distinguish confirmed facts from unresolved items, and request the missing statement lines or withdrawal details. If a required system is unavailable after appropriate normal handling, transfer with `technical_system_error`; do not invent a result.

## Script interface

Run:

```sh
python3 scripts/review_atm_fees.py < review_input.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output. Input fields are:

- `product`: `"bluest"` or `"light_green"`
- `month`: a label such as `"2025-11"`
- `bluest_benefits_active`: required boolean for Bluest; use `false` when balance eligibility is not established
- `transactions`: transaction objects with at least `transaction_id`, `date`, `description`, `amount`, `type`, and `status`; ATM-fee records should include `related_withdrawal_id`, `fee_kind` (`rho` or `third_party`), and `is_foreign` when known. ATM withdrawals should include `is_foreign` and `withdrawal_amount` when known.

The output separates `confirmed_candidates`, `needs_evidence`, and `notes`. Only entries marked `confirmed` with an `exact_correction` are candidates for the manual banking validation described above. Script output is never authority to apply a credit.

## Customer response

Explain the period reviewed, fees/rebates found, the product rule for each result, and any final correction. Clearly state that third-party ATM charges may be separate from Rho-Bank charges. Never expose other accounts, profile fields, or transaction data.