---
name: credit-card-transaction-dispute-filing
description: File one or more formal credit-card transaction disputes after matching each reported charge, collecting every required field, retrieving card last-four values and dispute history, and applying provisional-credit eligibility rules. Use for fraud, duplicate, billing, delivery, subscription, and refund disputes.
---

# Credit Card Transaction Dispute Filing

Use this Skill once a customer asks to dispute credit-card charges. Treat every transaction as a separate dispute. Do not file a record with guessed, missing, or mismatched required data.

## Required workflow

1. Identify the customer and retrieve their profile, credit-card accounts, and transaction history using the normal banking tools. Match each reported charge to exactly one transaction by card/account, merchant, amount, and purchase date. If ambiguous or absent, ask for clarification rather than selecting a transaction.
2. Obtain the registered full name, user ID, phone, email, and address from the profile. Follow any runtime identity-verification requirements before performing account actions; if verification is completed, log it using the normal verification tool.
3. Obtain the card last four digits for **each affected account** with the documented `get_card_last_4_digits(credit_card_account_id)` discovered tool. If runtime policy exposes it as an agent tool, unlock and call it. If the documentation/runtime designates it as a customer tool, pass that exact tool and the account ID to the user, then wait for its result. Never derive the last four from a transaction ID or invent it.
4. Unlock and call `get_user_dispute_history_7291` with the user ID to determine how many prior disputes were filed in the twelve months before the filing date. Count records whose dispute date falls in that window; if history is unavailable, eligibility cannot safely be determined, so do not claim eligibility or file until the required result is available.
5. For each dispute, collect and normalize:
   - `transaction_id`, transaction amount, purchase date (`MM/DD/YYYY`), card last four, and associated account/card tier;
   - when the issue was noticed (`MM/DD/YYYY`). If the customer says “today,” obtain current time and convert its date;
   - one exact reason code from the permitted set;
   - whether the merchant was contacted. Fraud does not require merchant contact for provisional-credit eligibility, but still use an explicit boolean in the filing;
   - requested resolution. Map “reverse/reversed/chargeback” to `reversal_of_charge`; collect a positive numeric `partial_refund_amount` only for `partial_refund`;
   - card action: `keep_active` or `cancel_and_reissue`. Ask for this for fraud reports; do not silently cancel a card.
6. Run `scripts/prepare_disputes.py` locally on the assembled data. It validates permitted values, formatting, conditional partial-refund data, and determines provisional-credit eligibility. Resolve every `errors` or `missing` item before filing.
7. Unlock `file_credit_card_transaction_dispute_4829`. For every validated filing, call it through `call_discoverable_agent_tool` with its exact name and a JSON-string version of the corresponding `payload`. A script recommendation does not itself perform a bank action.
8. Record each tool outcome separately. Tell the customer which disputes were filed and any unavailable disputes and their precise missing information. Explain that provisional credit, when eligible, is temporary while investigation occurs; do not promise a final result.

## Exact filing fields and enum mapping

The filing payload requires:

`transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`.

Allowed `dispute_reason` values are:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Allowed `resolution_requested` values are `full_refund`, `partial_refund`, and `reversal_of_charge`. Include `partial_refund_amount` only for `partial_refund`; it must be a positive number and should not exceed the original transaction amount.

## Provisional-credit decision

A customer is eligible only if **all** apply:

- the account has been open at least 60 days as of the filing date;
- reason is fraud, duplicate charge, or goods/services not received;
- for goods/services not received, purchase was more than 30 days before filing;
- amount is at least $25 and does not exceed the tier limit;
- no more than two disputes were filed in the preceding 12 months;
- for every non-fraud reason, merchant contact is true.

Limits: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. The helper recognizes the documented card-type mappings and allows an explicit `max_provisional_credit_limit` when a product is not listed. A failed criterion means the filing flag is `false`, not that the dispute should be rejected. Missing decision inputs are blocking validation errors.

## Helper interface

Run `python3 scripts/prepare_disputes.py` and send one JSON object on stdin. It emits JSON on stdout and has no banking side effects.

Input schema:

```json
{
  "filing_date": "MM/DD/YYYY",
  "profile": {"full_name":"...", "user_id":"...", "phone":"...", "email":"...", "address":"..."},
  "prior_disputes_last_12_months": 0,
  "disputes": [{
    "transaction_id":"...", "transaction_amount": 0.0,
    "account_open_date":"MM/DD/YYYY", "card_type":"...",
    "card_last_4_digits":"1234", "purchase_date":"MM/DD/YYYY",
    "issue_noticed_date":"MM/DD/YYYY", "card_action":"keep_active",
    "contacted_merchant": false,
    "dispute_reason":"unauthorized_fraudulent_charge",
    "resolution_requested":"full_refund"
  }]
}
```

For an unlisted card tier, provide `max_provisional_credit_limit` in that dispute object. Add `partial_refund_amount` only where needed. Output includes one result per input item: `valid`, `missing`, `errors`, `eligibility` (boolean and reasons), and a ready-to-JSON-encode `payload` only if valid. Review all outputs before tool calls.
