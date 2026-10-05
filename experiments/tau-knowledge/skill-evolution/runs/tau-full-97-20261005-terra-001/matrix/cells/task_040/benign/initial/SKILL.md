---
name: credit-card-transaction-dispute-filing
description: Verify a customer, resolve one or more posted credit-card charges, determine provisional-credit eligibility, and file one formal dispute per charge using file_credit_card_transaction_dispute_4829. Use for unauthorized charges, duplicates, billing errors, merchandise/service issues, subscriptions, and missing refunds.
---

# Credit Card Transaction Dispute Filing

Use this Skill only for formal disputes of posted credit-card transactions. A dispute is **one transaction per tool call**, even when a customer reports several charges or cards.

## Required information and safe workflow

1. **Verify the customer before submitting or revealing account-specific information.** Have the customer state at least two of date of birth, registered email, registered phone number, and address; compare them to the canonical user record. After two fields match, obtain the current timestamp and call `log_verification` with the canonical name, ID, address, email, phone, date of birth, and timestamp. Do not treat a name/account lookup as verification.
2. Retrieve the user's credit-card accounts and transaction history. Resolve every claimed charge to exactly one posted transaction by matching the intended card, merchant, amount, and purchase date. If none or multiple transactions match, ask a clarifying question; do not invent a transaction ID.
3. Obtain the last four digits for each affected account through the documented `get_card_last_4_digits(credit_card_account_id)` discovered tool. Follow the runtime's discovery model: unlock and call it as an agent tool when available to agents; if it is made available as a customer tool, use `give_discoverable_user_tool` with that account ID and await the result. Never request a full card number.
4. Collect or confirm for every transaction: dispute reason, merchant-contact answer, issue-noticed date, requested resolution, and a positive partial-refund amount when applicable. Normalize dates to `MM/DD/YYYY`. When the customer says “today,” obtain the runtime current time and use its calendar date.
5. Retrieve dispute history with `get_user_dispute_history_7291` for the verified `user_id` before filing anything. Count prior disputes whose `dispute_date` is in the 12 months ending on the current date. An empty successfully retrieved list means zero; a failed, partial, or ambiguous retrieval is not evidence of zero.
6. Determine provisional-credit eligibility separately for each charge using the rules below. Ineligibility does **not** block a formal dispute; pass `false`.
7. Run `scripts/prepare_disputes.py` using verified runtime data. Resolve every reported validation error before submitting its affected claim. Review its generated payloads, which are the exact argument objects for the filing tool.
8. Unlock `file_credit_card_transaction_dispute_4829` with `unlock_discoverable_agent_tool`, then call it once per generated payload via `call_discoverable_agent_tool`. Serialize each payload as the `arguments` JSON string. Record the tool result for each transaction and report only successfully accepted filings as filed.

Do not use `apply_statement_credit_8472` as a substitute for filing a dispute. It is unrelated to a provisional-credit determination.

## Allowed filing values

Use only these exact values:

- `card_action`: `keep_active` or `cancel_and_reissue`
- `dispute_reason`: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`
- `resolution_requested`: `full_refund`, `partial_refund`, `reversal_of_charge`

Set `card_action` from the customer's explicit decision. Use `keep_active` when they want to retain the card. Use `cancel_and_reissue` only when they want cancellation/reissue, including when a replacement was already ordered. If a replacement is separately needed, follow the replacement-card workflow and its eligibility checks; do not assume a replacement order occurred merely because a dispute is filed.

For non-fraud reasons, `contacted_merchant` must reflect whether the customer tried to resolve the issue with the merchant. Fraud may be submitted with `false` when the customer did not contact the merchant.

## Provisional-credit rules

Set `eligible_for_provisional_credit` to `true` only if **all** apply:

1. The account has been open at least 60 days.
2. Reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`. The not-received reason additionally requires the purchase to be **more than 30 days** before the current date.
3. The full disputed transaction amount is at least $25.00 and does not exceed the tier limit.
4. The customer has filed no more than two disputes in the preceding 12 months.
5. For a non-fraud eligible reason, the customer contacted the merchant first.

Tier maxima are: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. Gold Rewards Card and Business Gold Rewards Card are Premium. The helper recognizes the documented card names. If the tier is unknown, do not guess eligibility.

## Helper input and output

Run the helper with JSON on stdin, for example:

```json
{
  "current_date": "MM/DD/YYYY",
  "profile": {"full_name": "...", "user_id": "...", "phone": "...", "email": "...", "address": "..."},
  "accounts": [{"account_id": "...", "card_type": "Gold Rewards Card", "opened_date": "MM/DD/YYYY", "last4": "1234"}],
  "prior_disputes": [{"dispute_date": "MM/DD/YYYY"}],
  "claims": [{
    "transaction_id": "...", "account_id": "...", "transaction_amount": 100.0,
    "purchase_date": "MM/DD/YYYY", "issue_noticed_date": "MM/DD/YYYY",
    "dispute_reason": "duplicate_charge", "contacted_merchant": true,
    "resolution_requested": "full_refund", "card_action": "keep_active"
  }]
}
```

`prior_disputes` must be the successfully retrieved history snapshot, including an empty array when appropriate. Each claim's ID, account, amount, and purchase date must already have been matched to transaction-history data. The optional `partial_refund_amount` is required only for `partial_refund`.

The script emits JSON with:

- `ok`: true only when every supplied claim is ready to submit;
- `errors`: claim-specific missing/invalid-data errors;
- `prior_disputes_last_12_months`: the count used;
- `submissions`: ready claims, each containing `tool_arguments` and a transparent `provisional_credit` decision/reasons.

Example runtime call: `python3 scripts/prepare_disputes.py < input.json`. Do not submit any claim absent from `submissions`; fix its errors or obtain customer clarification first. Before every filing call, ensure the payload has all required fields, 4-digit card suffix, valid enums, date strings, and `partial_refund_amount` exactly when resolution is `partial_refund`.

## Failures and completion

- If verification fails, stop account-specific processing and request correct verification information.
- If a transaction cannot be uniquely identified, do not file against a similar charge.
- If dispute history or card suffix retrieval fails, retry/escalate under normal procedures rather than submitting guessed values.
- If a filing-tool call fails, do not claim that transaction was filed; preserve the failure context and retry or escalate according to normal operations.
- Explain that provisional credit is temporary and can be reversed after investigation. Confirm each successfully submitted dispute and whether it qualified for provisional credit.
