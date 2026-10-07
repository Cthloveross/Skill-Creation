---
name: review-atm-fees-and-refund-mischarges
description: Review a verified customer's checking-account ATM fees against Blue, Green, and Light Green schedules using account and transaction-history tools. Use when a customer asks whether ATM fees were correct and, if fully supported, apply one exact aggregated fee_refund credit per checking account.
---

# Review ATM fees and correct confirmed mischarges

Use this Skill for a customer asking to investigate ATM fees. It supports a review of posted Rho-Bank ATM fees and conservative correction of documented overcharges. It does **not** refund third-party ATM operator surcharges, guess ATM location/currency, or infer account type from the customer's description.

## Required tools and access

The executor must use the normal banking tools declared for the task:

1. Verify the customer before exposing account activity. Match at least two customer-provided identity fields with a returned customer record, obtain the current timestamp, then call `log_verification` with the complete returned record and timestamp.
2. Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)` to retrieve the customer's actual accounts, including ID, type, class, status, and balance.
3. Unlock and call `get_bank_account_transactions_9173(account_id)` for each relevant actual checking account. This returns newest-first activity, including transaction date, description, amount, type, and status.
4. Only after a fully supported calculation, unlock and call `apply_checking_account_credit_5829(account_id, amount, "fee_refund")`.

Do not use credit-card tools for this request. Never apply a credit merely because a customer says fees appear high.

## Account and activity review procedure

1. Confirm which returned accounts are checking accounts. Use their returned `account_class`/account identity rather than the customer's claimed list. If an account is closed, missing, non-checking, or has an unrecognized class, explain that it cannot be reviewed or credited under this procedure.
2. Retrieve each eligible account's full transaction history. Filter to the requested November in the relevant year (if the request is made during November, explain the review is month-to-date unless future activity is unavailable) and retain all posted `atm_withdrawal` and `atm_fee` entries. Retain descriptions and IDs for auditability.
3. Match every candidate Rho ATM-fee entry to its successful cash withdrawal using date, amount, account, and description/location. Fees can post separately at settlement. Do not match a fee where more than one plausible withdrawal exists.
4. Determine whether each withdrawal was domestic out-of-network, domestic in-network, or foreign from the transaction record/receipt. A clearly identified ATM-owner/operator surcharge is external and outside this bank-fee correction process. A fee with unknown country/network/owner is unresolved, not an overcharge.
5. Include only posted, unambiguously matched Rho fees in the calculation. Pending fees should be revisited after posting; do not refund them now.
6. Normalize the verified cases and run `scripts/fee_review.py` as described below. For Light Green domestic out-of-network activity, include **every posted qualifying withdrawal in the calendar month**, including ones with a $0 Rho fee, so the four free withdrawals are counted correctly.
7. Review the script's errors and `blocked_accounts`. Resolve all ambiguity for an account before crediting that account. Use the exact `total_refund_by_account` amount; do not round, estimate, or net across accounts.
8. Before crediting, confirm the target is a checking account. Combine all confirmed ATM fee corrections for the same account into one credit because the credit tool is allowed only once per checking account per interaction and then has a 14-day cooldown. Use `fee_refund` (all corrections in this Skill are fee corrections). Do not make a zero-dollar call.
9. Tell the customer what was reviewed, distinguish Rho fees from ATM-operator charges, list any confirmed correction, and state the result returned by the credit tool. If no discrepancy is found, explain the applicable schedule. If data is insufficient, state precisely what could not be established and do not credit.

A customer may be older than the permitted Light Green age range or may mention a prior Light Green account. That does not authorize guessing a conversion or retroactively choosing another schedule. Review transactions under the actual returned account class; do not infer automatic conversion when the conversion setting is unavailable.

## Fee schedules implemented by the helper

All amounts are USD and every expected fee is rounded to cents using normal half-up currency rounding.

| Actual account class | Verified withdrawal classification | Expected Rho-Bank fee |
|---|---|---:|
| Blue Account | domestic out-of-network | 1% of withdrawal amount, capped at $3.00 |
| Blue Account | foreign | greater of 3% of USD-equivalent withdrawal amount or $5.00 |
| Green Account (checking) | domestic out-of-network | $3.00 |
| Green Account (checking) | foreign | greater of 3% of USD-equivalent withdrawal amount or $5.00 |
| Light Green Account | domestic out-of-network | first 4 qualifying withdrawals in each calendar month are $0.00; each later withdrawal is $1.50 |
| Light Green Account | foreign | up to and including $100: $2.00; over $100 through $300: $3.50; over $300: $5.00 |
| Any listed account | domestic in-network | $0.00 under the out-of-network fee schedules |

For foreign calculations, use the USD-equivalent cash amount that posted/settled. Never use local-currency face value unless it is explicitly the posted USD equivalent.

## Helper invocation

`scripts/fee_review.py` reads JSON from stdin and writes JSON to stdout. It has no banking side effects.

Input schema:

```json
{
  "cases": [
    {
      "account_id": "string",
      "account_class": "Blue Account | Green Account (checking) | Light Green Account",
      "withdrawal_date": "MM/DD/YYYY",
      "channel": "domestic_out_of_network | domestic_in_network | foreign",
      "withdrawal_amount": "positive USD decimal string",
      "rho_fee_charged": "nonnegative USD decimal string",
      "status": "posted | pending",
      "fee_transaction_id": "optional audit identifier",
      "withdrawal_transaction_id": "optional audit identifier",
      "match_confirmed": true,
      "charge_owner": "rho_bank | external_operator | unknown"
    }
  ]
}
```

`cases` must contain one row per withdrawal/associated fee, not one row per account. For a Light Green domestic out-of-network month, provide all qualifying posted withdrawals in chronological order or any order; the helper sorts them by date. Set `rho_fee_charged` to `0.00` when no Rho fee line was charged. Only mark `match_confirmed` true when the linkage has been independently established.

Example runnable call pattern (use actual runtime input rather than this illustrative structure):

```sh
python3 scripts/fee_review.py <<'JSON'
{"cases": []}
JSON
```

Output fields:

- `results`: per-case expected fee, overcharge, and review outcome;
- `total_refund_by_account`: exact positive amount to use for each safe, unblocked account;
- `blocked_accounts`: accounts with malformed, ambiguous, unknown-owner, or unsupported cases that must not be credited until resolved;
- `errors`: input issues;
- `safe_to_credit_accounts`: accounts that have a nonzero confirmed refund and no blocking issue.

Validate that every transaction date is in the requested review period, every fee is a posted Rho fee with a confirmed withdrawal match, the actual account is checking, and each helper refund total equals the sum of its listed overcharges. The helper intentionally blocks rather than makes assumptions when evidence is incomplete.
