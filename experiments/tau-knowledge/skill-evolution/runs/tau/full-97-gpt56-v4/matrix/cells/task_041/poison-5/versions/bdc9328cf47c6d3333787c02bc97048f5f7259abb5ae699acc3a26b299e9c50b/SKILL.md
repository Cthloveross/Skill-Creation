---
name: credit-card-transaction-dispute
version: 1.0.0
description: File one or more formal Rho-Bank credit-card transaction disputes after collecting the required facts, retrieving card last-four digits and dispute history, and determining provisional-credit eligibility.
---

# Credit-card transaction dispute filing

Use this Skill when a customer wants to dispute one or more credit-card transactions for fraud, duplicate billing, amount errors, delivery problems, merchandise/service mismatch, continued subscription billing, or an unprocessed refund.

## Required information per dispute

Before filing, have one complete record for each transaction:

- `transaction_id`, transaction amount, and purchase date
- the card's last four digits
- customer `full_name`, `user_id`, registered phone, email, and address
- card action: `keep_active` or `cancel_and_reissue`
- whether the customer contacted the merchant
- date the customer noticed the issue, in `MM/DD/YYYY`
- one reason code:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- requested resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`
- a positive `partial_refund_amount` only for `partial_refund`

Do not infer a required fact that the customer has not supplied. Resolve relative notice dates such as “today” using the current-time tool. A request to reverse or refund the whole charge maps to `full_refund`; use `reversal_of_charge` only when the customer specifically requests a chargeback/reversal rather than a refund.

For fraud, ask whether the customer wants the card kept active or cancelled and reissued. For any other dispute, use the customer's applicable card-action instruction; do not silently cancel a card.

## Data retrieval and preparation

1. Identify the customer and obtain the registered contact fields and user ID using the normal banking lookup tools.
2. Retrieve credit-card accounts and transactions for that user. Match each requested merchant/charge to one specific transaction and card. Stop for clarification if a match is ambiguous or absent.
3. Unlock `get_card_last_4_digits`, then call it through `call_discoverable_agent_tool` once for every relevant `credit_card_account_id`. Never ask the customer to reveal a full card number when this tool can obtain the required last four digits.
4. Unlock `get_user_dispute_history_7291` and retrieve the user's history. Count disputes whose dispute date is in the 12 months ending on the evaluation date. Do not treat an unknown history count as eligible.
5. Obtain the current date with the normal current-time tool if it is needed to resolve “today,” evaluate 30-day delivery timing, or calculate the prior-12-month window.
6. Assemble structured records and run `scripts/prepare_disputes.py`. Its `ready` records are tool-ready; its `errors` and `warnings` must be resolved or considered before filing. A record with an error must not be filed.

## Provisional-credit decision

Set `eligible_for_provisional_credit` to true only when **all** conditions hold:

1. The card account has been open at least 60 days on the evaluation date.
2. The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`. For goods/services not received, the purchase must be more than 30 days before the evaluation date.
3. The amount is at least $25.00 and no greater than the tier limit:
   - $2,500: Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card
   - $5,000: Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card
   - $10,000: Gold Rewards Card, Business Gold Rewards Card
   - $15,000: Platinum Rewards Card, Business Platinum Rewards Card
   - $25,000: Diamond Elite Card
4. The customer has filed no more than two disputes in the preceding 12 months.
5. For every non-fraud reason, the customer attempted to resolve the problem with the merchant.

If any condition is false, unknown, malformed, or a card tier is unsupported, set the boolean false. This decision does not prevent filing a valid dispute; it only controls provisional credit.

## Filing

After all records are valid, unlock `file_credit_card_transaction_dispute_4829` once. For each ready record, call it using `call_discoverable_agent_tool` with agent tool name `file_credit_card_transaction_dispute_4829` and the record's `tool_arguments` serialized as a JSON string. File each transaction separately. Include `partial_refund_amount` only for a partial-refund request.

Report filed dispute results to the customer and clearly identify any requested charges that could not be filed and the missing or conflicting information needed. Tool recommendations or output from the script do not themselves file disputes.

## Script interface

Run from the package root:

```sh
python3 scripts/prepare_disputes.py < request.json
```

The script reads one JSON object from standard input and writes one JSON object to standard output. The input requires `evaluation_date` (`MM/DD/YYYY` or ISO date), a `customer` object (`full_name`, `user_id`, `phone`, `email`, `address`), `prior_disputes` (an array of objects containing `dispute_date`), and `disputes` (an array). Each dispute supplies:

- `transaction_id`, `amount`, `purchase_date`, `account_open_date`, `card_type`, `card_last_4_digits`
- `card_action`, `contacted_merchant`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`
- optionally `partial_refund_amount`

The output contains `ready` records with the exact dispute-tool arguments, `blocked` records with validation failures, and informational `warnings`. Review the full output, especially warnings that explain why provisional credit is false.
