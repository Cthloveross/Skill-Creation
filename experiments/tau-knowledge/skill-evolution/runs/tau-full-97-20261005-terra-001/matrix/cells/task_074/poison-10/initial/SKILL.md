---
name: atm-fee-and-rebate-audit
version: 1.0.0
description: Audit a verified customer's November (or other specified month) checking-account ATM fees and Purple Account ATM-operator-fee rebates against documented account terms. Use before explaining suspected ATM overcharges, applying a permitted checking-account correction, or beginning an ATM dispute.
---

# ATM Fee and Rebate Audit

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and limits

This Skill reviews **Rho-Bank ATM fees** separately from third-party ATM operator surcharges. Do not treat a surcharge as a Rho fee merely because both appear around a withdrawal. Do not infer whether an ATM was domestic/foreign, out of network, Rho-owned, or whether a surcharge is rebate-eligible from an ambiguous description; obtain the ATM/statement facts or mark the item for review.

Supported account classes and documented rules:

- **Purple:** domestic out-of-network Rho fee is $2.50 per withdrawal; foreign Rho ATM fee is $0. Purple may rebate eligible global ATM *operator* fees up to $30 per month after they post.
- **Light Blue:** first two domestic out-of-network withdrawals each month are free, then $2.50 each; first two foreign withdrawals are free, then $4.00 each. Operator surcharges are separate.
- **Dark Green:** domestic out-of-network fee is 1% of cash withdrawn, minimum $1.50; foreign fee is 2.5%, maximum $6.00.
- **Evergreen:** domestic out-of-network fee is 1% of cash withdrawn, maximum $2.50; foreign fee is 2%, minimum $3.00.

Unsupported account classes, in-network withdrawals, unknown geography/network, ATM fees that cannot be associated with a withdrawal, and undocumented fee benefits require manual review rather than a credit recommendation.

## Required procedure

1. **Verify before retrieval or any other banking action.** Confirm the caller's authority and two of these four profile facts: date of birth, email, phone number, and address. Retrieve the profile using the available identity lookup, compare the caller-provided facts, retrieve the current timestamp, and call `log_verification` only after two facts match. A name and an email discovered from a lookup are not two caller-confirmed factors.
2. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Confirm each requested account is owned by the verified customer, is a checking account, and identify its account class and status. Do not review or credit an unowned, closed, savings, or unsupported account.
3. For every eligible requested checking account, retrieve complete history with `get_bank_account_transactions_9173(account_id)`. Retain posted and pending records separately; fee corrections must be based on settled/posted evidence. Review all transactions needed to evaluate the requested calendar month and associated postings/rebates.
4. Identify each ATM withdrawal, its corresponding Rho fee line (if any), and every separate operator surcharge/rebate. Obtain or record for each withdrawal: date, cash amount, domestic/foreign, in/out-of-network, ATM ownership if known, and whether each fee is a Rho fee or an operator surcharge. For Light Blue, order qualified withdrawals chronologically within each geography before counting the two free uses.
5. Build the JSON input described below and run `scripts/audit_atm_fees.py`. Validate that every linked transaction ID exists, belongs to the matching account, has posted status, and that every fee/withdrawal mapping and classification comes from the statement or confirmed ATM facts. Review `manual_review` items; never treat their absence from `discrepancies` as confirmation that they are correct.
6. Explain each confirmed result: withdrawal, charged Rho fee, expected Rho fee, any separate operator fee, Purple rebate calculation, and why a non-discrepant fee is correct. Purple rebates can only be assessed from confirmed eligible operator-fee data and posted rebate credits; the monthly cap is $30.
7. **Credit only when permitted.** For confirmed Rho fee overcharges, use `fee_refund`. For a confirmed missing Purple rebate, use `rebate_credit`. Before calling `apply_checking_account_credit_5829`, verify identity, authority, account ownership, that the account is an open checking account, the exact positive amount, transaction history, applicable benefit, existing credits, 14-day cooldown, and customer confirmation to apply the correction. The tool may be called only once per checking account per interaction and is subject to a 14-day cooldown. If both types are required for one account, combine their exact amounts into one call and choose the type applying to the majority of correction events. If there is no majority, do not guess the type; escalate for operational guidance. Record the reason and give the customer the updated balance returned by the banking tool.
8. If the customer instead alleges an ATM cash-dispense error, no cash, or unauthorized transaction, do not substitute a fee credit. Follow the debit-card dispute procedure: retrieve the linked card with `get_debit_cards_by_account_id_7823`, confirm an active/open checking relationship and all dispute prerequisites, collect the required transaction/card/customer/date/discovery/amount/ATM facts, and use the required dispute category. Third-party ATM cash discrepancies require chargeback handling; amounts over $200 require the stated EFT affidavit process. Follow provisional-credit rules separately.

## Analyzer input and output

Run the helper with JSON on stdin. It emits JSON only.

Required input:

```json
{
  "month": "11/2025",
  "accounts": [{"account_id": "...", "account_class": "Purple", "account_type": "checking", "status": "OPEN"}],
  "transactions": {"account_id": [{"transaction_id": "...", "date": "11/01/2025", "description": "...", "amount": -100.0, "type": "atm_withdrawal", "status": "posted"}]},
  "withdrawal_facts": [{"withdrawal_transaction_id": "...", "location": "domestic", "out_of_network": true}],
  "fee_links": [{"fee_transaction_id": "...", "withdrawal_transaction_id": "...", "fee_kind": "rho_bank"}],
  "operator_fees": [{"withdrawal_transaction_id": "...", "amount": 3.0, "eligible_for_purple_rebate": true}]
}
```

`fee_links` is required for a fee to be audited as a charged Rho fee. `operator_fees` is only used for Purple rebate analysis; it records separately evidenced operator surcharges, not Rho ATM fees. Amounts may be JSON numbers or decimal strings. Use `location` exactly `domestic` or `foreign`; use Boolean `out_of_network`.

Output contains: `discrepancies` (confirmed fee/rebate shortfalls), `manual_review` (insufficient or inconsistent evidence), `correct_items`, and `proposed_credit_by_account`. A proposed credit is a calculation aid, not authority to credit. It is omitted when no exact correction exists or correction types tie.

Example invocation (performed by the executor, not during package creation):

```sh
python3 scripts/audit_atm_fees.py < audit_input.json
```

Meaningful validation: reject/resolve every `manual_review` entry before action; confirm each discrepancy's IDs and cents against the retrieved posted transaction records; ensure the proposed amount equals the sum of approved discrepancy amounts for that account; and re-check the 14-day/one-call restriction immediately before any credit tool call.
