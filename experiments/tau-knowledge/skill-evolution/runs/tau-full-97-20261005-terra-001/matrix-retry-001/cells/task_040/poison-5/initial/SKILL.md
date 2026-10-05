---
name: credit-card-transaction-dispute-intake
version: 1.0.0
description: Prepare, validate, determine provisional-credit eligibility for, and submit one or more credit-card transaction disputes when the customer, account, transactions, and requested resolution are known or can be obtained through the banking runtime.
---

# Credit Card Transaction Dispute Intake

Use this Skill for formal credit-card transaction disputes, including unauthorized charges, duplicates, billing errors, merchandise/service issues, subscription charges, and missing refunds. It prepares one independent submission per disputed transaction and determines the required `eligible_for_provisional_credit` value.

## Required information

For every transaction, obtain and confirm:

- Canonical `transaction_id`, transaction amount, transaction date, merchant, and the card actually used.
- The card's last four digits, the account-open date, and exact supported card type.
- Customer `full_name`, `user_id`, registered `phone`, `email`, and `address`.
- `issue_noticed_date` in `MM/DD/YYYY`; use the runtime's current date only when the customer says they noticed it "today."
- `contacted_merchant` as a boolean. It remains required for fraud claims, even though lack of contact does not make a fraud claim ineligible for provisional credit.
- A normalized dispute reason and requested resolution.
- For `partial_refund`, a positive exact `partial_refund_amount` that does not exceed the transaction amount.
- The number of already-filed credit-card disputes in the prior 12 months.

The only valid dispute reasons are:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

The only valid resolutions are `full_refund`, `partial_refund`, and `reversal_of_charge`. Normalize an explicit request for a charge reversal or chargeback to `reversal_of_charge`; an explicit request for a full refund, or to dispute the full transaction amount as a refund, maps to `full_refund`. Ask a targeted clarification if the customer's requested remedy is genuinely ambiguous.

`card_action` is mandatory for every filing:

- `keep_active` when the customer wants to continue using that card.
- `cancel_and_reissue` when the card is to be cancelled and replaced, including when replacement was separately ordered.

Do not infer card cancellation from the dispute reason. Confirm the desired action for an unauthorized transaction if it was not stated. The same action must still be supplied for a non-fraud dispute; normally it is `keep_active` unless the customer asks to replace that card.

## Runtime workflow

1. **Verify the person and retrieve authoritative records.** Resolve the customer to one canonical user record. Before performing a filing, conduct the runtime's applicable identity check by having the customer confirm at least two of date of birth, registered email, registered phone, and registered address. After successful confirmation, call `get_current_time` and `log_verification` with all required fields from the authoritative user record and the timestamp. Do not treat an unconfirmed value merely displayed in a lookup as customer confirmation.
2. **Match every requested charge.** Use `get_credit_card_transactions_by_user` and `get_credit_card_accounts_by_user`. Match each claim to exactly one completed transaction by card, merchant, amount, and date. Do not submit on an ambiguous or nonmatching transaction; clarify the discrepancy first.
3. **Get card last-four values.** The documented retrieval mechanism is `get_card_last_4_digits(credit_card_account_id)`. Per the discovered-tool instructions, give the customer this tool with `give_discoverable_user_tool` for each relevant account, using that account's ID, and use the returned last four digits for only that account. Do not request or retain a full card number.
4. **Obtain dispute history.** Unlock `get_user_dispute_history_7291`, then invoke it through `call_discoverable_agent_tool` with `{"user_id":"..."}`. Count records whose dispute date is within the 12 months before the filing-date snapshot. Use the already-filed history retrieved immediately before this intake for every claim in the batch; do not let a different claim being prepared in the same batch alter its "previous disputes" count. If history is unavailable, malformed, or incomplete, do not guess eligibility; resolve the retrieval issue before filing.
5. **Determine provisional-credit eligibility separately for each claim.** The customer is eligible only if every applicable condition holds:
   - The relevant card account has been open at least 60 days.
   - Reason is fraud, duplicate, or `goods_services_not_received`. The last category additionally requires the purchase to be **more than** 30 days before the filing date.
   - The transaction is at least $25 and no greater than its card tier's limit.
   - No more than two already-filed disputes exist in the preceding 12 months.
   - For every non-fraud reason, `contacted_merchant` is true.

   Limits are Bronze/Eco/Business Bronze/Crypto-Cash Back $2,500; Silver/Business Silver/Green/Silver Zoom $5,000; Gold/Business Gold $10,000; Platinum/Business Platinum $15,000; Diamond Elite $25,000. Reasons `incorrect_amount`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed` are never eligible. A false eligibility result does not prevent filing the dispute.
6. **Validate before side effects.** Run `scripts/prepare_disputes.py` with current runtime data. Correct every reported error for a claim before submitting that claim. The script produces no banking side effect.
7. **File each valid dispute.** Unlock `file_credit_card_transaction_dispute_4829` once, then call it once for each prepared claim with `call_discoverable_agent_tool`. Its `arguments` must be a JSON string containing exactly the required filing fields. Include `partial_refund_amount` only when the resolution is `partial_refund`. Never substitute merchant name or an account ID for `transaction_id`.
8. **Report results.** Preserve each filing result and tell the customer which transactions were submitted, their requested remedy, card action, and whether a temporary provisional credit is eligible. Explain that provisional credit is temporary during investigation and can be reversed if the claim is not resolved in the customer's favor. Clearly distinguish filing failures or unresolved claims from successfully filed claims.

For a tool error, missing required fact, malformed date, missing last four digits, unsupported card type, or an unmatched transaction, do not fabricate a payload. Ask for the specific missing item or retry the documented read-only lookup when appropriate. A partial-refund request without an exact amount cannot be filed as partial; the customer may instead choose a full refund, a charge reversal, or defer that claim.

## Validator script

Run with JSON on standard input:

```json
{
  "as_of_date": "MM/DD/YYYY",
  "profile": {"full_name":"...","user_id":"...","phone":"...","email":"...","address":"..."},
  "prior_disputes_past_12_months": 0,
  "cards": [{"card_type":"Gold Rewards Card","account_open_date":"MM/DD/YYYY","card_last_4_digits":"1234"}],
  "disputes": [{
    "transaction_id":"...",
    "card_type":"Gold Rewards Card",
    "transaction_amount":342.5,
    "purchase_date":"MM/DD/YYYY",
    "issue_noticed_date":"MM/DD/YYYY",
    "dispute_reason":"unauthorized_fraudulent_charge",
    "resolution_requested":"reversal_of_charge",
    "contacted_merchant":false,
    "card_action":"keep_active"
  }]
}
```

For a partial refund, add `"partial_refund_amount": 12.34` to that dispute. The script emits JSON with an entry per input dispute. Each entry has `can_submit`, `errors`, a `provisional_credit` explanation, and, when valid, `tool_arguments`: the exact object to JSON-serialize for the filing tool. Confirm that all expected claims have a `can_submit: true` entry before invoking the filing tool; a bad claim need not prevent separately valid claims from being submitted.
