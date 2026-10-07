---
name: atm-fee-and-rebate-audit
version: 1.1.0
description: Audit a verified customer's specified-month checking-account ATM fees and Purple ATM-operator-fee rebates against documented account terms. Use before explaining suspected ATM overcharges, applying a permitted checking-account correction, or beginning an ATM dispute.
---

# ATM Fee and Rebate Audit

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and supported terms

Audit Rho-Bank ATM fees separately from third-party ATM operator surcharges. Do not treat an operator surcharge as a Rho fee. Do not infer that a fee belongs to a withdrawal merely because the entries share a posting date: fee posting may settle on a different date. A fee can instead be audited directly when its own description or statement detail explicitly identifies the Rho fee, geography/network, withdrawal amount, and applicable calculation facts.

Supported checking-account terms are:

- **Purple:** domestic out-of-network Rho fee is $2.50 per withdrawal; foreign Rho ATM fee is $0. Purple may rebate eligible global ATM *operator* fees up to $30 per month after posting.
- **Light Blue:** first two domestic out-of-network withdrawals each month are free, then $2.50 each; first two foreign withdrawals are free, then $4.00 each. Operator surcharges are separate.
- **Dark Green:** domestic out-of-network fee is `max(1% of cash withdrawn, $1.50)`; foreign fee is `min(2.5% of cash withdrawn, $6.00)`.
- **Evergreen:** domestic out-of-network fee is `min(1% of cash withdrawn, $2.50)`; foreign fee is `max(2% of cash withdrawn, $3.00)`.

Unsupported account classes, in-network withdrawals, unknown geography/network, ambiguous fee descriptions, and undocumented benefits require manual review. Do not create a fee-to-withdrawal association based only on date, adjacent placement, or matching amount.

## Required procedure

1. **Verify before retrieval or any other banking action.** Confirm the caller's authority and two of these four profile facts: date of birth, email, phone number, and address. Retrieve the profile using the available identity lookup, compare the caller-provided facts, retrieve the current timestamp, and call `log_verification` only after two facts match. A name and an email discovered from a lookup are not two caller-confirmed factors.
2. Retrieve all accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Confirm every requested account belongs to the verified customer, is an open checking account, and identify its account class. Do not review or credit an unowned, closed, savings, or unsupported account.
3. Retrieve complete history for **every** requested eligible checking account with `get_bank_account_transactions_9173(account_id)`. Retain posted and pending records separately. Corrections require posted evidence; review the requested month and any related fee/rebate postings.
4. Classify every relevant ATM withdrawal, Rho fee, operator surcharge, and posted rebate from actual statement language. Record withdrawal date, cash amount, domestic/foreign location, network status, ownership where known, and whether a fee is Rho-imposed or operator-imposed. For Light Blue, chronologically count all confirmed qualified withdrawals separately by geography before assessing its allowance.
5. Establish each discrepancy using one of only two evidence paths:
   - **Linked path:** a transaction/statement provides an actual fee-to-withdrawal linkage. Audit the linked posted Rho fee using the withdrawal facts.
   - **Explicit standalone-fee path:** the posted fee's own description explicitly supplies the Rho-fee classification and enough facts to calculate the correct amount. For example, an explicitly identified domestic non-Rho fee stated as a percentage of a named withdrawal amount must still be tested against both the percentage and any documented minimum or maximum. This path does not require inventing a transaction link.

   Use neither path for a fee that is merely near a withdrawal in the history. A standalone Light Blue fee additionally needs statement-supported domestic/foreign allowance ordinal information.
6. Create the helper input below and run `scripts/audit_atm_fees.py`. Check all transaction IDs against retrieved history, account ownership, posted status, fee classification, cents, and source facts. Resolve every `manual_review` entry before an action. The helper is a calculation aid; it does not replace review of statement wording.
7. Explain confirmed findings, including charged Rho fee, correct fee, correction, and any separate operator fee or Purple rebate. A confirmed Rho fee charged above the schedule is a **fee mischarge**, including Purple foreign Rho fees that should be $0; it is not automatically an operator-fee rebate issue.
8. **Obtain authorization and credit only when permitted.** Before `apply_checking_account_credit_5829`, verify identity, authority, ownership, open checking status, exact positive correction, relevant transaction history, applicable terms, prior credits, and the 14-day cooldown. Obtain the customer's confirmation to apply the correction. Use `fee_refund` for confirmed fee mischarges and `rebate_credit` only for a confirmed missing rebate. The tool may be called once per checking account per interaction. Combine all approved corrections for that account into one exact credit; if fee refunds and rebate credits coexist, use the type covering the majority of correction events, and escalate if there is no majority. Record the reason and provide the updated balance returned by the banking tool.
9. If the customer alleges an ATM cash-dispense error, no cash, or unauthorized activity, do not substitute a fee credit. Follow the debit-card dispute process: retrieve the linked card with `get_debit_cards_by_account_id_7823`, collect the required transaction/card/customer/date/discovery/amount/ATM facts, and apply the applicable dispute and provisional-credit requirements. Third-party ATM cash discrepancies require chargeback handling; amounts above $200 require the stated EFT affidavit process.

## Helper input and output

Run the script with one JSON object on stdin; it writes one JSON object to stdout.

```json
{
  "month": "MM/YYYY",
  "accounts": [{"account_id": "...", "account_class": "Dark Green", "account_type": "checking", "status": "OPEN"}],
  "transactions": {"account_id": [{"transaction_id": "...", "date": "MM/DD/YYYY", "description": "...", "amount": -1.5, "type": "atm_fee", "status": "posted"}]},
  "withdrawal_facts": [{"withdrawal_transaction_id": "...", "location": "domestic", "out_of_network": true}],
  "fee_links": [{"fee_transaction_id": "...", "withdrawal_transaction_id": "...", "fee_kind": "rho_bank"}],
  "explicit_fee_facts": [{"fee_transaction_id": "...", "location": "domestic", "out_of_network": true, "withdrawal_amount": "...", "explicitly_identified_as_rho_fee": true, "allowance_ordinal": 3}],
  "operator_fees": [{"withdrawal_transaction_id": "...", "amount": "...", "eligible_for_purple_rebate": true}]
}
```

All money values may be JSON numbers or decimal strings. `location` is exactly `domestic` or `foreign`. `out_of_network` and `explicitly_identified_as_rho_fee` are Booleans. `fee_links` implements the linked path. `explicit_fee_facts` implements the standalone-fee path and must be derived from explicit statement detail, not an inferred association. `allowance_ordinal` is required for standalone Light Blue facts and must reflect the complete evidenced monthly count for that geography. `operator_fees` contains separately evidenced operator surcharges and is used only for Purple rebate analysis.

The output has `discrepancies`, `correct_items`, `manual_review`, and `proposed_credit_by_account`. A proposal is never credit authority. Validate that each proposed amount equals the approved, exact discrepancy sum for that account and re-check the one-call/cooldown rule immediately before any banking tool call.

Example executor invocation:

```sh
python3 scripts/audit_atm_fees.py < audit_input.json
```
