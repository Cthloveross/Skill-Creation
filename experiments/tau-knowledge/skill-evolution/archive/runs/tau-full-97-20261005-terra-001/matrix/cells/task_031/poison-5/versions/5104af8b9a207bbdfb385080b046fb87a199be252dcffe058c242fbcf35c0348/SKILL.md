---
name: credit-card-transaction-dispute
version: 1.0.0
description: Gather, validate, and file a Rho-Bank credit-card transaction dispute, including identity verification, card-last-four retrieval, dispute-history review, and provisional-credit determination.
---

# Credit Card Transaction Dispute

Use this Skill when a customer wants to formally dispute a completed credit-card transaction for fraud, duplicate billing, an incorrect amount, undelivered or misdescribed goods/services, continued subscription billing, or a missing refund.

## Required submission fields

The final call to `file_credit_card_transaction_dispute_4829` requires:

- `transaction_id`
- `card_action`: exactly `keep_active` or `cancel_and_reissue`
- `card_last_4_digits`: exactly four digits for the card used on the transaction
- `full_name`, `user_id`, `phone`, `email`, `address`
- `contacted_merchant`: boolean
- `purchase_date` and `issue_noticed_date`: `MM/DD/YYYY`
- `dispute_reason`: one of:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`
- `partial_refund_amount`: a number, required only for `partial_refund`
- `eligible_for_provisional_credit`: determined by this workflow, never guessed

## Workflow

1. **Identify and verify the customer.** Resolve a customer record using supplied name, email, or user ID. Before filing, have the customer confirm two of the four identity fields: date of birth, registered email, phone number, and home address. Retrieve the profile record, obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete profile values and timestamp. Do not treat a name alone as verification.

2. **Locate and confirm the transaction.** Use `get_credit_card_transactions_by_user` and match the customer’s merchant, date, and amount. If multiple possible transactions exist, ask the customer to select one. Use the selected transaction’s ID, date, amount, and card type; do not invent these values.

3. **Determine card handling.** Ask whether the customer wants the card to remain usable or cancelled and replaced when that is not clear. Use `keep_active` only when the customer wants to continue using that card; use `cancel_and_reissue` when a replacement is requested or the card is cancelled as part of the dispute. Do not cancel or replace a card merely because a dispute is filed.

4. **Obtain the card last four securely.** The transaction record’s card type is not the card’s last four digits. Find the matching account with `get_credit_card_accounts_by_user`. The documented retrieval method is customer-operated: call `give_discoverable_user_tool` with `discoverable_tool_name` `get_card_last_4_digits` and arguments containing the selected account’s `credit_card_account_id`. Ask the customer to run it and provide only the four-digit result. Do not proceed with a missing, nonnumeric, or guessed value.

5. **Gather dispute facts.** Ask for any unknown required field. Explicitly ask when the issue was first noticed, whether the merchant was contacted (except that a fraud report can be recorded as not contacted), the reason category, and the desired resolution. Map the customer’s narrative to an allowed reason only when unambiguous; otherwise present the allowed choices. Convert relative dates such as “today” using the current date and submit zero-padded `MM/DD/YYYY` dates. For a partial refund, obtain the requested dollar amount as a number.

6. **Review prior disputes and determine provisional credit.** Unlock `get_user_dispute_history_7291`, then call it through `call_discoverable_agent_tool` with the verified `user_id`. Count disputes in the preceding 12 months from the current date. Use the selected account’s opening date and card type, the transaction amount/date, merchant-contact answer, and history result. Run `scripts/prepare_dispute.py` to validate the complete case and compute the required boolean.

   Provisional credit is `true` only if every applicable condition is met:
   - the card account has been open at least 60 days;
   - the reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` where the purchase was more than 30 days ago;
   - the amount is at least $25.00 and no more than the selected card tier’s limit;
   - no more than two disputes were filed in the preceding 12 months; and
   - for every non-fraud reason, the customer contacted the merchant first.

   Limits are Entry $2,500 (Bronze Rewards, EcoCard, Business Bronze Rewards, Crypto-Cash Back); Mid $5,000 (Silver Rewards, Business Silver Rewards, Green Rewards, Silver Zoom); Premium $10,000 (Gold Rewards, Business Gold); Elite $15,000 (Platinum, Business Platinum); and Invitation $25,000 (Diamond Elite). A determinate failure of any criterion means submit `false`, not that filing is blocked. Missing eligibility evidence blocks submission until resolved.

7. **Validate, file, and report.** Supply structured data to the script. Only when `valid` is `true`, unlock `file_credit_card_transaction_dispute_4829` and call it with `call_discoverable_agent_tool`; the `arguments` value must be a JSON string containing the script’s `payload` exactly. Report the filing result to the customer and explain that a `true` provisional-credit result is temporary while the investigation proceeds. Never claim that a dispute was filed unless the filing tool succeeded.

## Validation helper

`scripts/prepare_dispute.py` reads one JSON object from standard input and writes one JSON object to standard output. It makes no bank-tool calls.

Input schema:

```json
{
  "submission": {
    "transaction_id": "string",
    "card_action": "keep_active | cancel_and_reissue",
    "card_last_4_digits": "four digits",
    "full_name": "string",
    "user_id": "string",
    "phone": "string",
    "email": "string",
    "address": "string",
    "contacted_merchant": true,
    "purchase_date": "MM/DD/YYYY",
    "issue_noticed_date": "MM/DD/YYYY",
    "dispute_reason": "allowed reason",
    "resolution_requested": "allowed resolution",
    "partial_refund_amount": 0
  },
  "eligibility": {
    "account_open_date": "MM/DD/YYYY",
    "card_type": "selected card type",
    "transaction_amount": 0,
    "dispute_history": [{"dispute_date": "MM/DD/YYYY or ISO-8601 timestamp"}],
    "as_of_date": "MM/DD/YYYY"
  }
}
```

Omit `partial_refund_amount` unless it is a partial-refund request. `dispute_history` may be an empty list, but must be supplied after querying the history tool. The helper output contains `missing`, `errors`, an eligibility explanation, and a tool-ready `payload` only when all required submission and eligibility evidence is valid.

Example invocation after replacing the placeholders with real runtime data:

```sh
python3 scripts/prepare_dispute.py <<'JSON'
{"submission": {"transaction_id":"<transaction-id>","card_action":"keep_active","card_last_4_digits":"<last4>","full_name":"<name>","user_id":"<user-id>","phone":"<phone>","email":"<email>","address":"<address>","contacted_merchant":true,"purchase_date":"<MM/DD/YYYY>","issue_noticed_date":"<MM/DD/YYYY>","dispute_reason":"<allowed-reason>","resolution_requested":"full_refund"}, "eligibility":{"account_open_date":"<MM/DD/YYYY>","card_type":"<card-type>","transaction_amount":<amount>,"dispute_history":[],"as_of_date":"<MM/DD/YYYY>"}}
JSON
```

If the session ends after the customer has been given the last-four retrieval tool but before they return its result, do not file or claim completion. Keep the case pending and ask the customer to return the four digits; also collect any remaining required answers at that time.
