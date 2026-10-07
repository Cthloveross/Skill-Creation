---
name: platinum-rewards-annual-fee-rebate-review
description: Assess a Platinum Rewards Card customer's annual-fee rebate eligibility from posted transaction data using account-opening anniversary windows. Use for read-only rebate inquiries; do not use it to apply a credit, change an account, or resolve a disputed transaction.
---

# Platinum Rewards annual-fee rebate review

Use this Skill to produce an auditable, read-only eligibility assessment for a Platinum Rewards Card. The policy requires at least $7,500.00 in eligible **net posted purchases** in each of 12 consecutive account-opening-anniversary windows. A qualifying completed fee-billed year earns a $150.00 annual-fee statement-credit rebate.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

This Skill is read-only and must never itself apply a rebate. Before retrieving or disclosing account-specific results, verify the customer using two of the four identity fields (date of birth, email, phone number, and address), then call `log_verification` with all required account-profile values and the current timestamp. A supplied name, user ID, or account number alone identifies a record but is not two-factor identity verification.

For the read-only review, confirm that the verified customer owns the selected Platinum Rewards Card and select the exact account. If there are multiple accounts of that product, do not combine their transactions or guess which account the customer means.

## Required source data and preflight

1. Obtain the current timestamp with `get_current_time`.
2. After identity verification, retrieve card accounts and identify the Platinum Rewards Card account, its opening date, and whether it is still open and has not been product-changed.
3. Retrieve the full transaction history for the verified customer. Retain only transactions conclusively associated with the selected card account. Treat `transaction_date` as a posting date only when the data source defines it that way; otherwise obtain a posting-date field. Authorization dates cannot be used.
4. Confirm the assessment year is fee-billed, rather than a first year whose fee was waived. Confirm whether the annual fee for that year has been billed. A waived first year does not earn a rebate.
5. Confirm the source covers the entire 12-window period, including refunds, returns, credits, and unresolved disputes. Do not infer completeness from a partial screen or an abbreviated response.

If account status, product-change status, annual-fee billing/waiver status, posted-date meaning, transaction coverage, or transaction-to-account association is unavailable, give a calculated provisional total only and state that an official eligibility decision cannot be confirmed.

## Policy rules to apply

- A window begins on the monthly anniversary of the account-opening date and ends the day before the next anniversary. The evaluation consists of 12 consecutive windows.
- Evaluate only after the 12th window has closed. For a fee-billed cardmember year, eligibility is all-or-nothing: every window must meet the threshold.
- Count net purchases posted during the window, including authorized-user, virtual-card, and international purchases that post as purchases.
- Exclude fees, interest, balance transfers, cash advances, cash equivalents, coded person-to-person transfers or funding transactions, and unresolved disputed transactions.
- Returns, refunds, and credits reduce the total in the window in which they post. Do not move them to the original purchase's window.
- A closed or product-changed account before year-end evaluation or rebate posting is not eligible for the rebate.
- A qualifying rebate is a $150.00 statement credit applied after the annual fee for that year is billed. Do not promise a posting date or initiate a credit.

The supplied policy does not define an anniversary convention for accounts opened on a day absent from a later month (for example, the 31st). Escalate that calendar edge case for policy clarification rather than silently choosing a different date.

## Calculation workflow

Create structured input for `scripts/evaluate_rebate.py` and run it once the required account and transaction data are available. The script is a deterministic calculator; it does not retrieve records, verify identity, or perform banking actions.

```sh
python3 scripts/evaluate_rebate.py < rebate_input.json
```

### Script input schema

The script reads one JSON object from standard input:

```json
{
  "account": {
    "account_id": "string",
    "card_type": "Platinum Rewards Card",
    "opened_on": "YYYY-MM-DD",
    "annual_fee_billed": true,
    "first_year_fee_waived": false,
    "account_active": true,
    "product_changed_before_evaluation": false
  },
  "as_of": "YYYY-MM-DD",
  "transaction_history_complete": true,
  "posting_dates_confirmed": true,
  "transaction_scope_confirmed": true,
  "transactions": [
    {
      "transaction_id": "string",
      "account_id": "string",
      "card_type": "Platinum Rewards Card",
      "posted_on": "YYYY-MM-DD",
      "amount": "decimal string or number",
      "status": "COMPLETED or POSTED",
      "transaction_type": "purchase, refund, return, credit, fee, interest, cash_advance, cash_equivalent, balance_transfer, p2p_transfer, funding, adjustment, or dispute",
      "counts_toward_threshold": true
    }
  ],
  "evaluation_start": "YYYY-MM-DD (optional)",
  "threshold": "7500.00 (optional)",
  "rebate_amount": "150.00 (optional)"
}
```

`evaluation_start`, when supplied, must be the start of the fee-billed cardmember year and an exact supported anniversary of `opened_on`. When it is absent, the script selects the latest 12-window period whose final window ended before `as_of`. `counts_toward_threshold`, if supplied, is the authoritative transaction classification; otherwise the script applies the documented type/status exclusions. Refund, return, and credit types are normalized as reductions even if exported with an unsigned amount.

### Script output and validation

The script emits one JSON object containing `status`, `evaluation`, a 12-item `windows` array, monthly net totals, shortfalls, included and excluded transaction IDs, and `decision_reasons`.

Validate before communicating a result:

- `evaluation.window_count` must be 12 and the end date must be before `as_of`.
- Each window must show `meets_threshold: true` to report qualification.
- `status` must be `eligible` before saying the customer qualifies. `not_eligible` identifies a failed month or an account/waiver condition. `pending` means the year has not closed. `insufficient_data` means no official conclusion is safe.
- Check that `data_gaps` is empty for an official result. Review the reported excluded transactions and any `warnings`, especially unclassified transactions.
- Never state that a rebate has already been posted merely because the calculation is eligible.

## Customer response

State the selected card, the evaluated start/end dates, whether all 12 windows met the threshold, and the outcome. For a failure, list the month(s), posted net totals, and shortfall(s). For a qualifying fee-billed, active account, explain that the $150.00 statement credit is applied after the annual fee is billed. If the output is pending or insufficient, clearly identify the missing verification or account/transaction information and avoid a definitive eligibility claim.
