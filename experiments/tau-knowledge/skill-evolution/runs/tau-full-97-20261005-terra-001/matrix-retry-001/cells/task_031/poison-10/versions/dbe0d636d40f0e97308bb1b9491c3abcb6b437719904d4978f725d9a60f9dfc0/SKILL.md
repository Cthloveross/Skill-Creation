---
name: file-credit-card-transaction-dispute
description: File a credit-card transaction dispute after identifying the transaction, collecting every required customer and dispute field, determining provisional-credit eligibility, and invoking the required discoverable filing tool. Use when a customer reports an unauthorized charge, billing error, duplicate, missing/incorrect goods or services, subscription issue, or missing refund.
---

# File Credit Card Transaction Dispute

## Purpose

Use this Skill to prepare and submit a complete dispute with `file_credit_card_transaction_dispute_4829`. The filing tool requires all mandated fields, including a card's last four digits and a definite provisional-credit eligibility boolean. Never invent missing customer statements or card data.

## Required inputs for the filing tool

Collect or retrieve the following before submitting:

- `transaction_id`
- `card_action`: exactly `keep_active` or `cancel_and_reissue`
- `card_last_4_digits`: exactly the four digits for the card used in the transaction
- `full_name`, `user_id`, registered `phone`, registered `email`, registered `address`
- `contacted_merchant`: boolean
- `purchase_date` and `issue_noticed_date`, both `MM/DD/YYYY`
- `dispute_reason`, one of:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`
- `partial_refund_amount`: a number, only when `resolution_requested` is `partial_refund`
- `eligible_for_provisional_credit`: boolean determined from the eligibility rules below

## Workflow

1. **Identify the customer and transaction.** Obtain the canonical `user_id` and registered contact fields with the user-information tools. Use `get_credit_card_transactions_by_user` to locate the transaction and confirm its merchant, amount, date, and card type with the customer. Do not select a transaction merely because the amount or merchant is similar.

2. **Map the reported problem and obtain choices.** Explain the available reason and resolution codes in customer-friendly language, then record the exact corresponding code. Ask whether the customer wants to keep using the card (`keep_active`) or cancel and replace it (`cancel_and_reissue`). Ask whether they attempted to resolve the problem with the merchant; for a fraud report, record the answer but do not require merchant contact.

3. **Collect missing dates and card digits.** Ask when the customer first noticed the issue. If they say “today,” obtain the current date with `get_current_time` and format it as `MM/DD/YYYY`.

   The filing cannot be submitted without `card_last_4_digits`. If the customer lacks the card, offer the documented self-service discovered tool `get_card_last_4_digits` using the card's account ID. Pass it to the customer with `give_discoverable_user_tool` when that facility is available, using JSON arguments shaped as `{"credit_card_account_id":"<account-id>"}`. Alternatively, direct the customer to their credit-card account in the app or website, then **View card details** or **Reveal card number**, complete any identity prompt, and share only the last four digits. Do not guess the digits, substitute another card's digits, or submit before they are available.

4. **Determine provisional-credit eligibility.** Retrieve the relevant card account through `get_credit_card_accounts_by_user`, use the current date, and determine account age and tier. When eligibility is otherwise possible, obtain the customer’s dispute history using `get_user_dispute_history_7291` (unlock and call it through the discoverable-agent workflow if required by the runtime) and count disputes filed in the prior 12 months.

   A customer is eligible only if every applicable condition is met:
   - the card account has been open at least 60 days;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`; the last reason additionally requires a purchase more than 30 days before the current date;
   - the transaction amount is at least $25 and does not exceed the card-tier maximum;
   - no more than two disputes were filed in the preceding 12 months; and
   - for every non-fraud reason, the customer contacted the merchant first.

   Tier limits are: $2,500 for Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, and Crypto-Cash Back Card; $5,000 for Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, and Silver Zoom Card; $10,000 for Gold Rewards Card and Business Gold Rewards Card; $15,000 for Platinum Rewards Card and Business Platinum Rewards Card; and $25,000 for Diamond Elite Card.

   The reasons `incorrect_amount`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed` are categorically ineligible. For these, set `eligible_for_provisional_credit` to `false`; unknown history or account facts do not change that conclusion. For potentially eligible reasons, do not guess unavailable facts—obtain them before setting the boolean.

5. **Validate the proposed submission.** Use `scripts/validate_dispute.py` with the collected structured fields. It normalizes the tool arguments, checks required field formats and conditional refund handling, and computes/checks eligibility. Resolve every reported error. If eligibility is indeterminate, collect the listed facts rather than sending a guessed boolean.

6. **Submit only when complete.** First call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `file_credit_card_transaction_dispute_4829`. Then call `call_discoverable_agent_tool` with that same name and an `arguments` value that is a JSON string containing the validated `tool_arguments`. Include `partial_refund_amount` only for a partial-refund request.

7. **Handle results.** Report that the dispute was filed only after a successful tool result. If the tool rejects the request, use its error to correct missing or invalid data and retry only after resolving it. If the customer cannot provide a required item such as the last four digits, clearly state that filing remains pending and identify the exact required next step; do not claim submission.

## Validator usage

Run the packaged validator by sending one JSON object on standard input and reading one JSON object from standard output. It performs no bank action.

Example input shape (placeholders only):

```json
{
  "dispute": {
    "transaction_id": "<transaction-id>",
    "card_action": "keep_active",
    "card_last_4_digits": "0123",
    "full_name": "<registered-name>",
    "user_id": "<user-id>",
    "phone": "<registered-phone>",
    "email": "<registered-email>",
    "address": "<registered-address>",
    "contacted_merchant": true,
    "purchase_date": "01/15/2025",
    "issue_noticed_date": "01/20/2025",
    "dispute_reason": "duplicate_charge",
    "resolution_requested": "full_refund"
  },
  "transaction_amount": 100.0,
  "card_type": "Silver Rewards Card",
  "account_open_date": "01/01/2024",
  "as_of_date": "02/01/2025",
  "prior_dispute_count_12_months": 0
}
```

A successful result has `valid_for_submission: true`, a non-null `eligibility.eligible`, and `tool_arguments`. Use precisely that object as the arguments for the filing tool. If a caller already supplies `eligible_for_provisional_credit`, the validator rejects it when it disagrees with a determinable result.
