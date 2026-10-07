---
name: credit-card-transaction-dispute
version: 1.0.0
description: File a Rho-Bank credit-card transaction dispute when a customer reports an unauthorized charge, billing error, duplicate, missing goods/services, service not as described, continuing cancelled subscription charge, or missing refund. Use this Skill to gather and validate the complete dispute payload, obtain a missing card last four through the customer-facing card tool, determine provisional-credit eligibility, and submit through the required internal discoverable tool.
---

# Credit Card Transaction Dispute

## Scope and safety

Use this Skill only for a credit-card transaction dispute. Do not submit a dispute until the disputed transaction, customer, card, required dates, issue category, requested resolution, and provisional-credit determination are all supported by the conversation and normal banking-tool records.

Follow the normal identity-verification procedure before revealing account details or taking an account action. If verification requires two confirmed identity fields, obtain and confirm them and then log the verification with the complete verified record and current timestamp. Never treat a database lookup alone as confirmation by the customer.

## Collect and confirm the dispute facts

1. Identify the transaction from the customer's account history. Confirm the merchant, amount, transaction date, and the card involved if more than one transaction could fit. Record its `transaction_id`, amount, and purchase date. Format the purchase date as `MM/DD/YYYY`.
2. Obtain or confirm the customer's full name, `user_id`, registered phone number, registered email, and registered home address from verified records. The values submitted must be the registered values for that customer.
3. Ask whether they contacted the merchant first. Set `contacted_merchant` to a Boolean, not a string. A clear statement that the merchant was contacted unsuccessfully is `true`.
4. Ask when the customer noticed the issue. Convert a clear relative date such as “today” using the current banking-system date, and format it as `MM/DD/YYYY`. If the relative date or date format is ambiguous, ask for clarification rather than guessing.
5. Classify the issue using exactly one of these codes:
   - `unauthorized_fraudulent_charge`
   - `duplicate_charge`
   - `incorrect_amount`
   - `goods_services_not_received`
   - `goods_services_not_as_described`
   - `canceled_subscription_still_charging`
   - `refund_never_processed`

   A delivered hotel room, item, or service materially different from what was booked or advertised is `goods_services_not_as_described`.
6. Ask whether the customer wants to keep the card active or cancel and replace it. Set exactly one of:
   - `keep_active`
   - `cancel_and_reissue`

   Do not infer cancellation merely from a fraud claim. If a replacement has already been ordered, use `cancel_and_reissue`.
7. Map the requested outcome to exactly one of:
   - `full_refund`
   - `partial_refund`
   - `reversal_of_charge`

   For `partial_refund`, ask for and validate a positive numeric dollar amount. Do not include `partial_refund_amount` for either other resolution.

## Obtain card last four safely

The dispute requires the last four digits of the card that made the selected transaction. Never ask the customer to provide a full card number.

If the customer does not have the last four digits, identify the corresponding credit-card account ID from account records and provide the customer-facing discoverable tool:

- Call `give_discoverable_user_tool` with `discoverable_tool_name` set to `get_card_last_4_digits` and arguments containing the selected `credit_card_account_id`.
- Tell the customer to execute the provided tool and wait for its result.
- Use the returned four digits only after ensuring the account/card type matches the transaction.

Do not substitute the last four from a different card or invent the value. If the matching account ID cannot be established, request clarification and do not file yet.

## Determine provisional-credit eligibility

Retrieve the customer’s dispute history before filing. Unlock `get_user_dispute_history_7291`, then call it through `call_discoverable_agent_tool` with the verified `user_id`. Count disputes filed in the 12 months before the current system date. If the history response is malformed, truncated, inaccessible, or cannot be reliably interpreted, do not claim eligibility; resolve the data issue before filing.

Eligibility is `true` only when **all** conditions below are met:

1. The selected card account has been open at least 60 days.
2. The reason is one of `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`. For goods/services not received, the purchase must be more than 30 days old.
3. The transaction amount is at least $25.00 and no greater than the selected card tier limit:
   - $2,500: Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card
   - $5,000: Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card
   - $10,000: Gold Rewards Card, Business Gold Rewards Card
   - $15,000: Platinum Rewards Card, Business Platinum Rewards Card
   - $25,000: Diamond Elite Card
4. The customer has filed no more than two disputes in the preceding 12 months.
5. For any non-fraud reason, the customer contacted the merchant first.

All other dispute reasons are ineligible. The absence of eligibility does not prevent filing the dispute; submit `false` for `eligible_for_provisional_credit`.

For deterministic calculation, run the packaged helper after gathering current records. It accepts JSON on stdin and emits JSON on stdout:

```sh
python scripts/provisional_credit.py < runtime_eligibility_input.json
```

Its input object is:

```text
{
  "today": "MM/DD/YYYY or ISO timestamp",
  "account_open_date": "MM/DD/YYYY or ISO timestamp",
  "purchase_date": "MM/DD/YYYY or ISO timestamp",
  "transaction_amount": number,
  "card_type": string,
  "dispute_reason": string,
  "contacted_merchant": boolean,
  "prior_dispute_dates": ["MM/DD/YYYY or ISO timestamp", ...]
}
```

It emits `{ "eligible": boolean, "prior_disputes_in_last_12_months": integer, "reasons": [string, ...] }`. Treat an invalid-date or unknown-tier error as a stop condition requiring corrected source data. The helper is a calculation aid; the executor must still inspect the history and account selected to ensure they belong to the customer and transaction.

## Validate and submit

Construct the internal-tool argument object with these exact keys and types:

```text
transaction_id: string
card_action: "keep_active" | "cancel_and_reissue"
card_last_4_digits: string (exactly the retrieved four digits)
full_name: string
user_id: string
phone: string
email: string
address: string
contacted_merchant: boolean
purchase_date: "MM/DD/YYYY"
issue_noticed_date: "MM/DD/YYYY"
dispute_reason: one permitted reason code
resolution_requested: "full_refund" | "partial_refund" | "reversal_of_charge"
partial_refund_amount: number (only for partial_refund)
eligible_for_provisional_credit: boolean
```

Before submission, check that dates parse in `MM/DD/YYYY`, Boolean fields are actual booleans, enum values exactly match the permitted values, the last-four string is four digits, and the partial amount is present only for a partial refund. Do not add unsupported fields.

Then:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` `file_credit_card_transaction_dispute_4829`.
2. Call `call_discoverable_agent_tool` using that same name and a JSON-serialized version of the validated argument object.
3. Report the resulting filing status or reference to the customer. Explain that provisional credit, when eligible, is temporary while the investigation is ongoing.

If the filing tool returns an error, do not assert that a dispute was filed and do not retry blindly. Correct a clearly identified validation/data error once supported by records or customer clarification; otherwise explain the issue and use the appropriate normal escalation process.
