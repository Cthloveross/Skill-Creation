---
name: november-atm-fee-audit
version: 1.0.0
description: Review a verified customer's checking-account ATM fees for a requested calendar month, compare confirmed bank fees with Blue, Green, and Light Green fee schedules, and safely consolidate any confirmed overcharge into at most one permitted checking-account fee-refund credit per account.
---

# ATM fee audit and correction

Use this Skill when a customer asks to investigate ATM fees across Blue, Green, and/or Light Green checking accounts, especially when they cannot identify the suspect entries. It supports review of the bank's ATM fee only; ATM-owner/operator charges are separate and must never be refunded as a bank fee.

## Required verification and retrieval

1. Verify identity before disclosing account activity or taking account action. Have the customer supply enough information to confirm **two of** email, date of birth, phone number, and address against the profile. Do not reveal an unconfirmed value as a prompt.
2. After two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete profile fields and that timestamp.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified `user_id`. Record each returned checking account's `account_id`, `account_class`, status, balance, and opening date. Do not rely on account names supplied by the customer as account IDs or product classifications.
4. For every relevant returned checking account, unlock and call `get_bank_account_transactions_9173(account_id)`. It returns newest first and includes posted and pending entries. Review the complete requested calendar month, not merely entries the customer remembers.

The customer may have provided a name/email for lookup, but that alone does not replace two-field verification. The customer-facing response should summarize only the verified customer's information and the resulting account activity.

## Fee schedule used for bank-fee comparison

Classify a withdrawal only from a clear transaction description, transaction context, or other supplied account evidence. If the record does not establish whether it was foreign, in-network, or domestic out-of-network, mark it unresolved rather than guessing.

| Account class | Confirmed withdrawal category | Expected Rho-Bank fee |
|---|---|---:|
| Blue | domestic out-of-network | 1% of withdrawal amount, capped at $3.00 |
| Blue | foreign | greater of 3% of USD-equivalent withdrawal amount or $5.00 |
| Green | domestic out-of-network | $3.00 per withdrawal |
| Green | foreign | greater of 3% of USD-equivalent withdrawal amount or $5.00 |
| Light Green | domestic out-of-network | First four in each calendar month are free; each later withdrawal is $1.50 |
| Light Green | foreign | $2.00 through $100; $3.50 over $100 through $300; $5.00 above $300 |
| Any listed account | confirmed in-network | $0.00 under the listed out-of-network/foreign schedules |

For Light Green, amounts exactly $100 and $300 use the lower tier. Foreign ATM fees are per withdrawal. For Blue and Green percentage-based foreign fees, use the USD amount posted for the cash withdrawal. ATM-owner/network fees are additional and separate in all cases.

The supplied policy does not specify a rounding convention for a percentage result with more than two decimal places. Do not invent one. Treat such a record as requiring policy clarification instead of calculating a credit estimate.

## Transaction-review method

1. Isolate all ATM withdrawals and `atm_fee` entries in the target month, including pending entries.
2. Match a bank fee line to its withdrawal only when the description, date, amount, and surrounding context make the match reliable. A third-party/operator fee must be excluded. An unmatched ATM fee, ambiguous pairing, unclear category, or unclear fee issuer makes the account review incomplete.
3. Count every confirmed, posted Light Green domestic out-of-network withdrawal in calendar order for that account/month to determine the four free withdrawals. Same-day entries may be supplied in their transaction-history order; the fee is constant after the fourth withdrawal.
4. Check the full account history for earlier `fee_refund`, `rebate_credit`, or other evidence that the exact disputed bank fee was already corrected. Do not refund it twice.
5. Keep pending activity separate. Because a credit can be used only once for that account in this interaction and triggers a 14-day cooldown, wait for relevant pending ATM activity to settle before applying a correction so all confirmed corrections can be combined.
6. Build a structured audit input and run `scripts/audit_atm_fees.py`. The helper makes calculations deterministic and refuses a recommendation if coverage is incomplete, a pending relevant entry exists, the fee issuer/category is uncertain, the percentage result requires unstated rounding, a prior correction is identified, or a credit was already used in this interaction.

## Helper input and output

Run `scripts/audit_atm_fees.py` with JSON on stdin. It emits JSON on stdout.

Input schema:

```json
{
  "review_month": "MM/YYYY",
  "accounts": [
    {
      "account_id": "checking account ID from account lookup",
      "account_class": "Blue, Green, or Light Green",
      "review_complete": true,
      "unmatched_atm_fee_count": 0,
      "unknown_atm_withdrawal_count": 0,
      "prior_refund_for_reviewed_fee": false,
      "credit_called_this_interaction": false
    }
  ],
  "events": [
    {
      "account_id": "account ID",
      "date": "MM/DD/YYYY",
      "sequence": 1,
      "withdrawal_amount": "100.00",
      "category": "foreign | domestic_out_of_network | in_network",
      "category_confirmed": true,
      "withdrawal_status": "posted | pending",
      "fee_status": "posted | pending",
      "bank_fee_attribution_confirmed": true,
      "charged_bank_fee": "5.00"
    }
  ]
}
```

Use positive dollar strings for `withdrawal_amount` and `charged_bank_fee`, even if source transaction amounts are negative debits. Include one event for every relevant withdrawal in the reviewed month. `charged_bank_fee` may be `0.00` only when the review establishes that no Rho-Bank ATM fee was charged. Set `bank_fee_attribution_confirmed` to `false` rather than entering an operator fee. The `accounts` controls document whether all relevant lines have been accounted for.

Example invocation shape (values are placeholders, not case data):

```text
run_skill_script(relative_path="scripts/audit_atm_fees.py", input_json=<audit JSON>)
```

Output contains per-event expected fees and differences, account blockers, and `credit_recommendations`. A recommendation appears only for a complete account review, only when the total confirmed overcharge is positive, and uses a two-decimal exact total. Validate before action that every account with a positive correction has exactly one unblocked recommendation, no blocked account is acted on, and the output's account IDs/classes agree with account lookup.

## Applying a permitted correction

Only after the above validation:

1. Confirm the target remains a checking account from the account lookup.
2. Confirm the result is a bank fee overcharge, rather than a third-party fee or an uncertain/pending record.
3. For each eligible account, combine **all** confirmed overcharges into its single total. Do not make multiple calls for separate transactions.
4. Unlock `apply_checking_account_credit_5829` and call it once for that account with the verified account ID, the positive `credit_recommendations[].amount`, and `credit_type` set to `fee_refund`.
5. Do not apply credits to savings or non-checking accounts. Do not apply any credit where the helper reports blockers, for an already corrected fee, or when a credit has already been applied to that account in this interaction. The tool also enforces a 14-day cooldown.
6. Tell the customer what was reviewed, distinguish valid bank fees from third-party fees, identify any unresolved or pending entries and needed follow-up, and state the single applied bank-fee refund and resulting balance only after a successful tool result.

If classification, matching, fee issuer, or rounding cannot be established from available records, do not estimate and do not credit. Explain the limitation and continue only when the needed evidence is available.
