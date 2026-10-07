---
name: audit-atm-fees-and-credit-corrections
version: 1.0.0
description: Review November ATM fees for a customer with Bluest and/or Light Green checking accounts, determine documented fee or rebate discrepancies from transaction history, and make at most one exact authorized checking-account credit when eligibility and identity-verification requirements are met.
---

# ATM-fee audit and correction

Use this Skill when a customer believes ATM fees or ATM rebates on a Bluest Account or Light Green Account are wrong. It is designed for an agent that can unlock the documented account lookup, transaction-history, and checking-credit tools.

## Guardrails

- Treat the transaction history, not the customer's recollection, as the source for transaction dates, amounts, statuses, fee descriptions, and already-applied credits.
- Do not claim transaction history is unavailable: the documented `get_bank_account_transactions_9173(account_id)` procedure returns it once the account ID is known.
- A credit is allowed only for an exact missing eligible rebate or an exact fee mischarge. It is **not** a goodwill adjustment.
- Credits are checking-only. Make no more than **one** credit call for an account in the interaction. The tool also imposes a 14-day cooldown; never retry a credit whose outcome is unknown.
- Before any credit, independently verify account ownership/identity. The customer must confirm two of the four profile fields: date of birth, email, phone number, and address. A value merely displayed by a lookup is not a customer confirmation. Log the completed verification with the current timestamp using `log_verification`.
- It is acceptable to retrieve and review activity before a credit decision, but do not disclose unnecessary transaction details until identity is appropriately established.

## Required agent-tool sequence

1. Identify the customer from an identifier they supplied (for example, email) using the ordinary profile lookup. Preserve the returned `user_id`; do not guess it.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` with that `user_id`. Keep only checking accounts that are relevant to the request, normally the Bluest and Light Green accounts. Record each account ID, class, status, balance, and opening date.
3. Unlock and call `get_bank_account_transactions_9173` once for each relevant checking `account_id`.
4. Review the full returned history for **November in the year shown by the transactions/current time**. Consider posted ATM withdrawals, `atm_fee` entries, and all `fee_rebate`, `rebate_credit`, and `fee_refund` entries. Pending lines may be explained as pending but must not be treated as final missing rebates or fee mischarges.
5. Link a fee to its corresponding withdrawal only where the date, description, ATM/location, and amounts support the link. Separate Rho-Bank fees from operator surcharges. Do not label a third-party surcharge as a Rho-Bank mischarge.
6. Apply the policy below. When structured event data is available, `scripts/atm_fee_audit.py` can calculate an auditable candidate total; its output is a recommendation, not an automatic bank action.
7. If a positive correction remains after subtracting already applied relevant credits, obtain/complete the two-field identity confirmation, call `get_current_time`, and call `log_verification`. Reconfirm the account is a checking account and that the evidence supports every component of the correction.
8. Combine **all** corrections for that account into one exact positive amount. Unlock and call `apply_checking_account_credit_5829(account_id, amount, credit_type)` exactly once. Use `fee_refund` when fee-mischarge components are the majority and `rebate_credit` when missing-rebate components are the majority. Do not round. If the evidence does not establish an applicable majority/type, do not improvise a credit; explain what is needed or seek authorized escalation.
9. Tell the customer what was reviewed, the documented fee/rebate rule that applies, the exact credit outcome if one was successfully applied, and any remaining limitation. State a new balance only if the credit tool actually returns it.

## Policy interpretation

### Bluest Account

All Bluest benefits require maintaining the $112,500 daily balance needed to keep benefits active. If historical eligibility for the date at issue cannot be established, do not assume benefits were active; explain the limitation rather than crediting that uncertain component.

When benefits were active:

- A Rho-Bank out-of-network ATM withdrawal fee is $2.00 per withdrawal.
- Rho-Bank charges $0.00 for foreign ATM withdrawals. A foreign ATM operator may nevertheless impose a separate third-party surcharge.
- Eligible ATM-fee rebates are credited only up to the aggregate $50 cap per monthly statement cycle. Compare eligible third-party fees with rebates actually posted and calculate any missing amount chronologically so the total requested rebate never exceeds the unused cap.

A $2.00 domestic Rho-Bank fee is not, by itself, proof of an error. Conversely, a foreign Rho-Bank fee while the benefit was active is a fee-mischarge candidate. Do not refund an operator charge merely because it was high; it may instead be an eligible rebate candidate subject to the $50 cap and evidence that it was not already rebated.

### Light Green Account

- The first four out-of-network ATM withdrawals in a calendar month are free; after the fourth, the Rho-Bank fee is $1.50 per withdrawal.
- Foreign-withdrawal fees are assessed separately per foreign transaction: $2.00 for withdrawals up to and including $100, $3.50 for more than $100 through $300 inclusive, and $5.00 above $300. Threshold values belong to the lower tier.
- Operator surcharges are separate from these Rho-Bank fees.

Sort relevant posted withdrawals in ascending date/time order before applying the four-free-withdrawals rule. Use the explicit foreign schedule for transactions documented as foreign; do not invent a location classification from an ambiguous description. If a transaction lacks the withdrawal amount or whether it was foreign/out-of-network, report that the exact fee cannot yet be verified.

## Calculation and reconciliation

For each supported event, calculate only a positive customer correction:

`fee correction = max(0, actual Rho-Bank fee charged - documented correct Rho-Bank fee)`

For a supported eligible Bluest third-party rebate:

`missing rebate = max(0, eligible rebate through that event under the remaining $50 cap - matching rebate already posted)`

Subtract any already-posted rebate/refund that demonstrably corrects the same fee. Do not use current account balance as proof of historical daily-balance eligibility, and do not double count an ATM fee and a separately posted reimbursement.

If no positive supported discrepancy remains, do not call the credit tool. Explain that the reviewed fees match the applicable schedule and distinguish bank fees from ATM-operator charges.

## Handling incomplete evidence

If account lookup, transaction history, ATM location, foreign status, withdrawal amount, eligible-benefit status, or a matching credit is unavailable, identify the exact missing fact. Do not estimate, use an unrelated fee schedule, or apply a speculative credit. The customer can provide the statement line/receipt or use the bank's documented support channels to obtain needed transaction history.

## Runnable calculator

Run the packaged helper with JSON on standard input:

```json
{
  "account_class": "Light Green Account",
  "events": [
    {
      "date": "11/03/2025",
      "location": "domestic_out_of_network",
      "withdrawal_amount": "80.00",
      "rho_fee_charged": "1.50",
      "third_party_fee": "0.00",
      "rebate_credits": "0.00",
      "status": "posted"
    }
  ]
}
```

For Bluest, include `"bluest_benefits_active": true` only when historical daily-balance eligibility is established. `location` must be one of `domestic_out_of_network`, `foreign`, or `unknown`. All amounts are nonnegative decimal-dollar strings. The script emits JSON containing per-event findings, the positive fee-refund total, missing-rebate total, and an `insufficient_evidence` list. Review source transactions yourself before acting on it.
