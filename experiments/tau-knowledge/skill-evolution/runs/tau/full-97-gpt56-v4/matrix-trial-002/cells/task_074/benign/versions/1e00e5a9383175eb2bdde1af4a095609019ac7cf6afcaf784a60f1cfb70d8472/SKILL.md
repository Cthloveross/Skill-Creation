---
name: review-atm-fees-and-correct-checking-account
version: 1.0.0
description: Review a verified customer's November ATM withdrawals, bank ATM fees, operator surcharges, and rebates across Purple, Light Blue, Dark Green, and Evergreen checking accounts. Use when a customer believes ATM fees or ATM-fee rebates were incorrect and an exact, policy-supported checking-account correction may be needed.
---

# Review ATM fees and rebates

Use this Skill to investigate the customer's actual posted transaction history before making any conclusion or credit. Account terms distinguish Rho-Bank fees from third-party ATM-operator surcharges; do not treat an operator surcharge as a Rho-Bank fee merely because both may appear near a withdrawal.

## Required tools and access

Unlock and use these documented agent tools as needed:

1. `get_all_user_accounts_by_user_id_3847(user_id)` to locate the customer's checking accounts and their account IDs.
2. `get_bank_account_transactions_9173(account_id)` for each relevant account. It returns newest first and includes pending and posted entries.
3. `apply_checking_account_credit_5829(account_id, amount, credit_type)` only after all prerequisites below are met.

Use `unlock_discoverable_agent_tool` before the first use of each of these tools, then call it through `call_discoverable_agent_tool` with JSON-string arguments.

## Identity and ownership verification

A credit requires identity and account-ownership verification. Do not infer that verification solely from an account lookup or a customer-provided name/email.

1. Locate the customer using a supplied profile identifier (for example, email) and retrieve the profile.
2. Ask the customer to confirm at least two of the four profile fields: date of birth, email, phone number, and address. Compare their answers to the retrieved profile.
3. When two fields match, call `get_current_time`, then call `log_verification` with the complete retrieved profile fields and the time returned by the tool.
4. Use the verified profile's `user_id` to retrieve accounts. Confirm the relevant account is a checking account before any credit.

If the customer cannot complete verification, do not disclose detailed account activity and do not credit the account. Explain what verification is needed.

## Investigation workflow

1. Retrieve all accounts for the verified user. Identify active checking accounts by account class/type, rather than relying only on the customer's product list. Match the Purple, Light Blue, Dark Green, and Evergreen product classes where present.
2. Retrieve transaction history separately for every relevant checking account. Review only the November period the customer asked about; state the year used and do not assume transactions that have not yet occurred. Include pending transactions in the explanation, but do not refund a fee or apply a missing-rebate credit based solely on a pending item.
3. For every posted ATM-related item, record its date, withdrawal amount, location/country or network indication in the description, fee description and amount, and any `fee_rebate`, `rebate_credit`, or `fee_refund`. Establish whether an `atm_fee` is the bank's fee or an ATM-owner surcharge from its wording. If the description does not establish this, do not guess; tell the customer that the entry cannot be validated from the available data.
4. Associate a fee or rebate with a withdrawal only where date, description, amount, and/or available transaction details support the association. Posting dates may differ from withdrawal dates.
5. Optionally create a structured list of the confirmed events and run `scripts/atm_fee_review.py`. The script calculates expected *bank* fees and flags a provisional correction; it does not access bank data, decide ambiguous classifications, or perform a banking action.
6. Check all history for already-posted refunds, rebates, or credits related to the same event before calculating any correction. Do not duplicate them.
7. Explain each validated result to the customer: charged amount, applicable term, expected amount, any applied rebate, and why an operator surcharge may be separate.

## Product rules for confirmed, posted events

Use the category actually supported by the transaction details. `domestic_out_of_network` and `foreign` are distinct. In-network withdrawals have no described out-of-network fee and should not be assessed using these schedules.

| Product | Confirmed event | Expected Rho-Bank ATM fee |
|---|---|---|
| Purple | Domestic out-of-network withdrawal | $2.50 per withdrawal |
| Purple | Foreign ATM withdrawal | $0.00 foreign ATM withdrawal fee |
| Light Blue | Domestic out-of-network withdrawal | First two in the calendar month are free; later withdrawals are $2.50 each |
| Light Blue | Foreign ATM withdrawal | First two in the calendar month are free; later withdrawals are $4.00 each |
| Dark Green | Domestic out-of-network withdrawal | 1% of cash amount, with a $1.50 minimum |
| Dark Green | Foreign ATM withdrawal | 2.5% of cash amount, capped at $6.00 |
| Evergreen | Domestic out-of-network withdrawal | 1% of cash amount, capped at $2.50 |
| Evergreen | Foreign ATM withdrawal | 2% of cash amount, with a $3.00 minimum |

For Light Blue, count confirmed withdrawals chronologically within the same calendar month and category. Never consume a free-use allowance with a transaction whose category or date is unknown.

Purple also has ATM-owner-fee rebates up to $30 per calendar month. A qualifying operator fee must be posted and be clearly eligible; rebates are credited after eligible fees post. Total eligible rebate cannot exceed the remaining $30 monthly cap after rebates already posted for that month. Do not assume that every `atm_fee` qualifies: coding, timing, location/terminal eligibility, and the cap can prevent a rebate. Purple's $2.50 domestic out-of-network fee is separate from an operator surcharge.

## Credit decision and execution

A credit is permitted only for a verified fee mischarge or a verified missing eligible rebate, only to a checking account, and only in the exact calculated amount.

Before calling the credit tool, verify all of the following:

- The account is a checking account belonging to the verified customer.
- Every event included is posted, identified, and supported by its transaction history and the applicable rule above.
- Previously posted fee refunds, fee rebates, and rebate credits have been deducted from the correction calculation.
- The proposed total is positive and exact to cents; no estimate, rounding, or unsupported operator surcharge is included.
- No prior credit has been applied to that account in this customer interaction. The tool permits only one credit per checking account and triggers a 14-day cooldown.

For multiple validated corrections on one checking account, combine them in one call. Use `fee_refund` if fee-mischarge corrections are the majority; use `rebate_credit` if missing-rebate corrections are the majority. Call `apply_checking_account_credit_5829` with the actual account ID, a positive decimal amount, and that credit type. Do not issue a credit if the record is incomplete, ambiguous, pending, ineligible, already corrected, or shows no overcharge/missing rebate.

After a successful credit tool result, tell the customer the total credit, reason, account, and the updated balance reported by the tool. If no correction is warranted, provide the reviewed explanation without promising a refund.

## Calculator interface

Run with JSON on standard input and JSON on standard output:

```json
{
  "product": "Purple Account",
  "events": [
    {
      "date": "MM/DD/YYYY",
      "category": "domestic_out_of_network",
      "cash_amount": "0.00",
      "bank_fee_charged": "0.00",
      "operator_surcharge": "0.00",
      "operator_fee_eligible": false,
      "rebate_credited": "0.00",
      "status": "posted",
      "confirmed": true,
      "reference": "transaction identifier or analyst reference"
    }
  ]
}
```

`cash_amount`, charged fees, surcharges, and rebates are nonnegative dollar strings. `operator_surcharge` and `rebate_credited` may be omitted and default to zero. `operator_fee_eligible` is required to calculate a Purple operator-fee rebate and must be `true` only after the transaction details establish eligibility. Only confirmed, posted events with supported categories are included in calculations; other entries are returned as exclusions for manual follow-up. The response contains event-level expected fees, fee overcharges, missing rebates, totals, exclusions, and a non-binding recommended credit type.

Validate the script output before using it: ensure its included references correspond to the actual transaction records, inspect every exclusion, and independently ensure that credits already shown in the full transaction history have been allocated to the correct event. The script's recommendation never substitutes for the required verification, account-class check, or bank-tool review.
