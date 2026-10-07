---
name: november-atm-fee-reconciliation
version: 1.1.0
description: Review a verified customer's November ATM withdrawals and ATM-fee charges across Blue, Green, and Light Green checking accounts; identify documented Rho-Bank fee overcharges; and apply one exact permitted fee-refund credit per eligible account.
---

# November ATM Fee Reconciliation

Use this Skill when a customer asks to review ATM fees for Blue, Green, and/or Light Green checking accounts. It supports a complete calendar-month review, keeps ATM-owner charges separate from Rho-Bank charges, and calculates only documented customer refunds.

## Required controls

- Obtain the customer identifier using the normal customer lookup workflow. Before applying a credit, verify identity and account ownership as required by the checking-credit procedure. After confirming two profile fields, call `get_current_time` and log the completed verification with `log_verification`.
- Retrieve the customer's accounts with `get_all_user_accounts_by_user_id_3847`. Retain each selected checking account's ID, class, status, balance, and opening date.
- Review **every requested eligible checking account**, not just the first account with an error. Retrieve transaction history with `get_bank_account_transactions_9173(account_id)` for each selected Blue, Green, and Light Green account.
- Review posted in-period ATM withdrawals and ATM-fee records. Transaction results are reverse chronological, so reorder posted withdrawals chronologically when applying Light Green's monthly domestic allowance.
- Do not infer a withdrawal's country, network status, a fee's ownership, or a fee-to-withdrawal association from an amount alone. Use the transaction description and other transaction evidence. Mark unsupported facts as unresolved.
- ATM-owner/operator charges are separate from Rho-Bank fees and are not refundable under these account schedules.
- Pending activity is not a settled fee mischarge. Explain that it must settle before review; do not include it in a credit.
- An absent or undercharged fee does not reduce a refund for an actual overcharge. Refund only the documented excess of posted Rho-Bank fees over the applicable schedule.
- Credits may be applied only to checking accounts, only for documented fee mischarges (or separately documented missing rebates), and only once per checking account per interaction. The system also has a 14-day cooldown. Submit one combined `fee_refund` for all supported fee overcharges on that account.

## End-to-end workflow

1. **Set scope.** Confirm the statement year if it is not clear. Define the calendar-month start and end date. For a November request made during November, use the available portion of November and state the exact coverage period.
2. **Identify and verify.** Look up the supplied customer identifier. Collect any required second profile confirmation before applying credits, then log the verification. If verification cannot be completed, do not apply a credit.
3. **Retrieve all requested accounts.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the runtime user ID. Select active checking accounts whose class is Blue, Green, or Light Green. Do not credit savings or a product that cannot be confirmed.
4. **Retrieve all account histories.** Unlock and call `get_bank_account_transactions_9173` once for each selected checking account. Extract every in-period ATM withdrawal and every ATM-fee line with transaction ID, date, description, signed amount, type, and status.
5. **Classify and associate evidence.** Identify whether each withdrawal is domestic or foreign and, for domestic withdrawals, whether it is out of network. Identify whether each fee is a Rho-Bank fee, an operator fee, or unresolved. Associate fee records only where the record evidence supports the relationship.
6. **Calculate each account.** Normalize the evidence into the helper input below and run `scripts/atm_fee_review.py`. It reports per-withdrawal expected fees, actual posted Rho-Bank fees, overcharge components, unresolved evidence, and one candidate refund.
7. **Review all results before acting.** A candidate is actionable only if the helper reports `ok: true`, `candidate_credit.eligible_for_submission: true`, all manual evidence checks remain valid, and the account is eligible for the one permitted credit. Do not offset an overcharge with an absent fee or an undercharge.
8. **Apply corrections.** Unlock `apply_checking_account_credit_5829`. For every independently eligible account, call it exactly once with that account's ID, the exact positive candidate amount, and `credit_type: "fee_refund"`. Do not combine corrections across accounts. A helper result is a recommendation only; the executor must make the banking-tool call.
9. **Close accurately.** On successful application, retrieve the account information again when needed for the updated balance. Tell the customer the account, exact refund, reason, and confirmed balance. If a credit is rejected (including cooldown), do not retry. Explain the result without claiming an unconfirmed credit.
10. **Human request.** If the customer asks for a human, use the available transfer workflow with an accurate summary; use `customer_requests_human_no_specific_reason` when no more specific reason applies. Do not say a transfer or handoff is complete unless the transfer tool publicly confirms it.

## Fee rules

Withdrawal amounts below are the posted U.S.-dollar withdrawal amounts.

| Product | Domestic Rho-Bank fee | Foreign Rho-Bank fee | Daily ATM limit |
|---|---|---|---:|
| Blue | Out-of-network: 1% of withdrawal, capped at $3.00 | Greater of 3% or $5.00 | $500 |
| Green | Non-network: $3.00 | Greater of 3% or $5.00 | $600 |
| Light Green | First four posted domestic out-of-network withdrawals in the calendar month: $0; later withdrawals: $1.50 | Up to and including $100: $2.00; above $100 through $300: $3.50; above $300: $5.00 | $150 |

For Light Green, process the first-four allowance in chronological order across supported posted **domestic out-of-network** withdrawals only. Foreign withdrawals use the foreign schedule and do not consume that allowance. Daily-limit findings are informational and are not themselves a fee-refund reason.

## Helper interface

Run `scripts/atm_fee_review.py` in the Skill runtime. It reads one JSON object from stdin and emits one JSON object to stdout. It has no external dependencies, never calls bank tools, and never applies a credit.

### Input schema

```json
{
  "account": {"account_id": "string", "product": "blue|green|light_green"},
  "review_month": "YYYY-MM",
  "coverage_complete": true,
  "withdrawals": [
    {
      "transaction_id": "string",
      "date": "MM/DD/YYYY or YYYY-MM-DD",
      "amount": "positive USD withdrawal amount",
      "status": "posted|pending",
      "location": "domestic|foreign|unknown",
      "out_of_network": true,
      "fee_transaction_ids": ["associated ATM-fee IDs"]
    }
  ],
  "fees": [
    {
      "transaction_id": "string",
      "date": "MM/DD/YYYY or YYYY-MM-DD",
      "amount": "negative posted debit amount",
      "status": "posted|pending",
      "kind": "bank|operator|unknown"
    }
  ]
}
```

Set `coverage_complete` to true only when all relevant in-month ATM withdrawals and ATM-fee lines from the retrieved history are represented. Use `unknown` instead of inventing classifications. `fee_transaction_ids` must be evidence-based associations; the helper deliberately does not guess based on proximity, date, or amount.

### Output and validation

The output contains `assessments`, `unresolved`, `unmatched_fee_ids`, `daily_limit_observations`, `refund_total`, and `candidate_credit`. Each assessed row includes `difference` (actual minus expected) and `refund_component` (only the positive portion of that difference).

Before submitting a candidate credit, verify that:

- `ok` is true and the account ID/product match the retrieved account;
- the month is complete and `coverage_complete` is truthfully true;
- all source records are in the requested month;
- all bank or unknown fee records are associated or appear in `unmatched_fee_ids` for investigation;
- `unresolved` is empty;
- each positive `refund_component` traces to posted transaction evidence;
- the candidate amount is positive and equals the supported overcharges; and
- identity, checking-account eligibility, and one-credit-per-account checks are complete.

If the helper returns `ok: false`, correct the normalized input rather than guessing. If evidence cannot establish a classification or association, explain the unresolved scope and do not credit it.
