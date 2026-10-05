---
name: review-checking-atm-fees
description: Verify an account holder, retrieve their checking accounts and transaction histories, and perform a documented, read-only review of November ATM fees for Blue, Green, and Light Green checking accounts. Use when a customer questions ATM fees, rebates, or related cash withdrawals and needs an explanation rather than an immediate account change or refund.
---

# Review Checking-Account ATM Fees

Use this Skill for a read-only comparison of posted or pending ATM fees against the published Blue, Green, and Light Green fee schedules. It does **not** create refunds, rebates, disputes, transfers, or account changes.

## Preconditions and controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this read-only account-history workflow:

1. Verify identity before accessing account records. Obtain confirmation of **two of four** identity fields (date of birth, email, phone number, or address) from the customer; compare them with the customer record without disclosing unprovided values. Do not treat a name or a preexisting lookup as identity verification.
2. After two fields match, obtain the current timestamp and call `log_verification` with the complete retrieved record and timestamp.
3. Establish authority and ownership by retrieving accounts only for the verified user's `user_id`; use only the checking accounts returned for that user. Confirm that each named account's account class/product and status match the requested review. Account status is relevant to the explanation; it does not authorize any transaction.
4. This workflow makes no debit, credit, payment, or refund, so balance, recipient/card details, cutoffs, and action confirmation do not authorize an action here. Still identify the applicable fee schedule, transaction status, withdrawal amount, location classification, and any separate operator fee before reaching a conclusion.

If identity cannot be verified, stop and request the missing verification fields. Do not retrieve account or transaction history. If the customer asks to dispute a fee or demands a refund after the review, do not promise an outcome or invent a remediation process; use only a separately documented dispute/refund workflow or offer an appropriate human escalation when needed.

## Runtime tool workflow

The banking tools named below are discoverable agent tools. Unlock a tool before calling it with `call_discoverable_agent_tool`.

1. If needed, use the customer-provided name to locate the record, then complete the two-field verification process above. Use `get_current_time` and `log_verification` only after the fields match.
2. Unlock and call `get_all_user_accounts_by_user_id_3847` with the verified `user_id`.
   - Identify checking accounts and report their `account_id`, `account_class`, and `status` before reviewing activity.
   - Locate one Blue, one Green, and one Light Green account from returned class/product information. Never select an account merely because its name was stated by the customer.
   - If a named product is absent, ambiguous, not checking, or not owned by the verified user, say so and do not substitute another account.
3. Unlock and call `get_bank_account_transactions_9173` once for each eligible returned account, passing that account's `account_id`.
   - Keep `transaction_id`, `date`, `description`, `amount`, `type`, and `status`.
   - Filter for the requested November and include both `posted` and `pending` entries, clearly labeling pending entries as not settled.
   - Review `atm_fee`, `atm_withdrawal`, and relevant `fee_rebate`, `rebate_credit`, or `fee_refund` entries. An ATM fee is normally a separate line from the withdrawal.
4. From the descriptions and transaction facts, determine for each fee whether the related withdrawal was domestic out-of-network or foreign, its U.S.-dollar withdrawal amount, and whether a fee/rebate line is explicitly linked. Do not infer foreign versus domestic solely from an unfamiliar merchant name. If descriptions do not establish the location/network or pairing, report it as unresolved and ask for the statement detail or ATM location.
5. Pass normalized records and only supported link/location facts to `scripts/analyze_atm_fees.py`. The script makes arithmetic and completeness checks; it does not retrieve banking data or take banking actions.
6. Explain each conclusion with the actual fee, applicable expected fee, calculation, transaction status, and any unresolved evidence. Do not count ATM-owner/operator charges as bank fees: such third-party fees are separate.

## Fee schedules used by this Skill

Apply a schedule only after the account product and withdrawal category are established.

| Product | Domestic out-of-network withdrawal | Foreign withdrawal |
|---|---|---|
| Blue | `min(1% × withdrawal amount, $3.00)` | `max(3% × USD-equivalent amount, $5.00)` |
| Green | `$3.00` per non-network withdrawal | `max(3% × settled USD-equivalent amount, $5.00)` |
| Light Green | First 4 out-of-network withdrawals in the calendar month are free; each later withdrawal is `$1.50` | `$2.00` up to and including `$100`; `$3.50` over `$100` through and including `$300`; `$5.00` above `$300` |

For Light Green domestic out-of-network fees, count relevant withdrawals in chronological order across the entire calendar month, not just transactions that happen to have an identified fee. If every relevant withdrawal cannot be classified, do not claim which withdrawal exceeded the four-free limit. Treat the distinct foreign fee schedule as a foreign-fee assessment; do not stack a domestic charge onto it without explicit policy evidence.

## Analyzer input and output

`scripts/analyze_atm_fees.py` reads one JSON object from standard input and emits one JSON object on standard output.

Required input fields:

```json
{
  "review_month": "YYYY-MM",
  "accounts": [
    {"account_id": "string", "product": "Blue|Green|Light Green", "account_class": "string", "status": "string"}
  ],
  "transactions_by_account": {"account_id": [{"transaction_id": "string", "date": "MM/DD/YYYY", "description": "string", "amount": -1.23, "type": "atm_fee", "status": "posted"}]},
  "withdrawal_context": [
    {"fee_transaction_id": "string", "withdrawal_transaction_id": "string", "location_category": "domestic_out_of_network|foreign"}
  ]
}
```

`withdrawal_context` is deliberately explicit. The executor supplies an entry only when transaction descriptions or statement facts support the linkage and category. The analyzer uses the linked withdrawal's absolute amount as the USD amount. Include a context entry for every known November ATM withdrawal on a Light Green account so it can safely evaluate the monthly free-withdrawal count.

Example invocation after data has been retrieved and normalized:

```sh
python3 scripts/analyze_atm_fees.py < review_input.json
```

The output contains `account_reports`, a per-fee `assessment` (`matches_schedule`, `does_not_match_schedule`, or `insufficient_evidence`), expected and actual amounts when calculable, and `rebate_candidates`. It also emits warnings rather than silently guessing when input is incomplete, dates are invalid, a fee is not linked, a product is unsupported, or the Light Green sequence is incomplete.

## Final customer response checklist

- State that the review covers the verified customer's returned checking accounts; list account product/class and status without exposing unrelated account data.
- For each ATM fee, give date, description, actual amount, related withdrawal/date/amount where supported, domestic/foreign basis, schedule calculation, and posted/pending status.
- Identify separately posted ATM-related rebate/refund candidates, but do not assume an unrelated credit offsets a particular fee.
- State that ATM operator fees are separate when applicable.
- Clearly distinguish a confirmed discrepancy from an item needing more detail. For any discrepancy, explain that it needs the authorized dispute/refund path rather than asserting that a credit has been issued.
