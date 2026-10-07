---
name: credit-card-transaction-dispute-filing
description: Prepare, determine provisional-credit eligibility for, and file one or more credit-card transaction disputes when the customer identifies disputed transactions. Use this for fraud, duplicates, billing errors, delivery problems, merchandise problems, recurring post-cancellation charges, and missing refunds.
---

# Credit Card Transaction Dispute Filing

File a separate dispute for every distinct transaction. Do not combine transactions across merchants or cards. The filing tool requires complete data for each submission, including the card's last four digits, even when the customer has supplied profile and transaction details.

## Required information per dispute

Collect or retrieve all of the following before filing:

- `transaction_id` and its purchase date, amount, merchant, and card type
- card last four digits for the card that made the transaction
- customer `full_name`, `user_id`, registered `phone`, `email`, and `address`
- card action: exactly `keep_active` or `cancel_and_reissue`
- whether the customer contacted the merchant (`contacted_merchant`)
- date the customer noticed the issue, in `MM/DD/YYYY`
- one permitted `dispute_reason`
- one explicit permitted `resolution_requested`; partial refunds also need a numeric amount
- provisional-credit eligibility calculated from the account, transaction, and prior-dispute data

Use these exact reason values:

| Customer issue | `dispute_reason` |
|---|---|
| Unrecognized, unauthorized, or fraudulent charge | `unauthorized_fraudulent_charge` |
| Same charge appears more than once | `duplicate_charge` |
| Charged more or less than expected | `incorrect_amount` |
| Goods/services never received | `goods_services_not_received` |
| Goods/services materially differ from description | `goods_services_not_as_described` |
| Cancelled subscription continues charging | `canceled_subscription_still_charging` |
| Promised refund never appeared | `refund_never_processed` |

Permitted resolution values are `full_refund`, `partial_refund`, and `reversal_of_charge`. Ask the customer to choose one when their wording does not unambiguously select an enum. Do not guess between a refund and a charge reversal. For `partial_refund`, obtain the dollar amount; do not provide `partial_refund_amount` for the other resolutions.

## Runtime procedure

1. **Identify and reconcile the transactions.** Retrieve the customer's profile, credit-card accounts, and transaction history using the normal read-only tools. Match each described merchant and issue to exactly one transaction on the intended card. If a match is ambiguous, ask for a transaction date, amount, or other distinguishing detail rather than filing against a guessed transaction.

2. **Resolve dates and customer choices.** If the customer says "today" or another relative date, call `get_current_time` and convert the date to `MM/DD/YYYY`. Ask for missing merchant-contact status, notice date, card action, or exact resolution enum. Fraud disputes do not require merchant contact for provisional-credit eligibility, but the filing argument still requires a boolean; record `false` unless the customer states that they contacted the merchant.

3. **Obtain card last four digits.** When account IDs are known, unlock and call the discovered `get_card_last_4_digits` tool with each relevant `credit_card_account_id`, then associate the returned four digits with the corresponding account. This is the appropriate alternative when the customer cannot provide them. If that tool cannot return the value, do not substitute a transaction ID, account ID, profile field, or a guessed value. Direct the customer to securely reveal card details in the app or website and provide only the last four digits.

4. **Obtain prior-dispute data.** Unlock and call `get_user_dispute_history_7291` with the canonical `user_id`. Retain the returned dispute dates so disputes filed in the preceding 12 months can be counted. An empty result is zero prior disputes; do not treat a history retrieval failure as an empty history.

5. **Determine provisional-credit eligibility independently for every transaction.** Use the criteria below, or provide the normalized runtime data to `scripts/prepare_disputes.py`. A filing may still be submitted when eligibility is false; pass `false` in that case.

   Eligible is `true` only when **all** conditions hold:
   - the relevant account has been open at least 60 days as of filing;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
   - for goods/services not received, the purchase is more than 30 days old;
   - amount is at least $25.00 and no greater than the tier's limit;
   - no more than two prior disputes were filed in the 12 months before the filing date;
   - for every non-fraud reason, the customer contacted the merchant.

   Tier limits are: $2,500 Entry (Bronze Rewards, EcoCard, Business Bronze Rewards, Crypto-Cash Back); $5,000 Mid (Silver Rewards, Business Silver Rewards, Green Rewards, Silver Zoom); $10,000 Premium (Gold Rewards, Business Gold Rewards); $15,000 Elite (Platinum, Business Platinum); and $25,000 Invitation (Diamond Elite). Reasons outside the three eligible reason categories are always ineligible.

6. **Validate before action.** Use the supplied script if useful. Resolve every reported input error for a transaction before filing that transaction. Confirm that the returned payload exactly has the required fields and that `eligible_for_provisional_credit` is a boolean, not an explanation.

7. **File the disputes.** Unlock `file_credit_card_transaction_dispute_4829`, then submit one call per ready transaction using `call_discoverable_agent_tool`. Set `agent_tool_name` to `file_credit_card_transaction_dispute_4829` and set `arguments` to a JSON string of the prepared payload. Required payload keys are:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active | cancel_and_reissue",
  "card_last_4_digits": "1234",
  "full_name": "string",
  "user_id": "string",
  "phone": "string",
  "email": "string",
  "address": "string",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "permitted enum",
  "resolution_requested": "permitted enum",
  "eligible_for_provisional_credit": true
}
```

Include numeric `partial_refund_amount` only for `partial_refund`. Record each successful tool result. If one filing fails, report that transaction as unfiled and continue only with other independently complete and validated disputes; do not claim failed submissions were filed.

8. **Close clearly.** Tell the customer which transaction disputes were submitted, which could not be submitted and why, and whether each submitted dispute is eligible for temporary provisional credit. Explain that provisional credit is temporary while the investigation is ongoing and may be reversed if the decision is unfavorable.

## Validation helper

`scripts/prepare_disputes.py` accepts one JSON object on stdin and emits a JSON preparation report on stdout. It is deterministic and does not call banking tools or file disputes.

Input schema:

```json
{
  "as_of_date": "MM/DD/YYYY or YYYY-MM-DD",
  "customer": {
    "full_name": "string",
    "user_id": "string",
    "phone": "string",
    "email": "string",
    "address": "string"
  },
  "accounts": [{
    "account_id": "string",
    "card_type": "Gold Rewards Card",
    "date_of_account_open": "MM/DD/YYYY",
    "card_last_4_digits": "1234"
  }],
  "transactions": [{
    "transaction_id": "string",
    "card_type": "Gold Rewards Card",
    "merchant_name": "string",
    "transaction_amount": 100.0,
    "transaction_date": "MM/DD/YYYY"
  }],
  "dispute_history": [{"dispute_date": "MM/DD/YYYY or timestamp"}],
  "requests": [{
    "transaction_id": "string",
    "card_action": "keep_active",
    "contacted_merchant": false,
    "issue_noticed_date": "MM/DD/YYYY",
    "dispute_reason": "unauthorized_fraudulent_charge",
    "resolution_requested": "reversal_of_charge"
  }]
}
```

For example, an executor can run `python3 scripts/prepare_disputes.py < input.json`. Its `filings` array contains only `submission_ready: true` records, each with the exact tool payload. Its `blocked` array identifies incomplete or invalid requests. Review `eligibility` reasons and `warnings`, then use only validated payloads in the filing tool.
