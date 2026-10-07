---
name: credit-card-transaction-dispute-filing
description: File one or more formal Rho-Bank credit-card transaction disputes, retrieve card last-four digits and dispute history through discovered tools, and determine provisional-credit eligibility from account, transaction, and customer data.
---

# Credit Card Transaction Dispute Filing

Use this Skill when a customer wants to formally dispute one or more completed credit-card transactions. It supports separate disputes across multiple cards. File a separate dispute for every eligible, fully specified transaction; do not combine transactions or submit transactions the customer asks to exclude.

## Required information and normalization

For each requested transaction, establish the matching transaction record and card account, then collect or derive:

- `transaction_id`, purchase date, amount, and card account/card tier;
- card action: `keep_active` or `cancel_and_reissue`;
- card last four digits;
- customer full name, `user_id`, registered phone, email, and home address;
- whether the merchant was contacted;
- issue-noticed date in `MM/DD/YYYY`;
- one permitted dispute reason;
- requested resolution, and a numeric partial-refund amount when applicable.

Map customer language only to these exact reason codes:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Map the requested outcome only to `full_refund`, `partial_refund`, or `reversal_of_charge`. A request to reverse or charge back a full transaction maps to `reversal_of_charge`; do not silently change a stated partial-refund request to a full dispute. `partial_refund_amount` is required only for `partial_refund`, must be a positive numeric dollar amount, and should not exceed the transaction amount. If the customer cannot supply it, defer that transaction rather than inventing an amount.

Use the current date when a customer identifies the issue as "today" but does not know the date. Format the resulting issue-noticed date as `MM/DD/YYYY`.

## Runtime procedure

1. Identify the customer and retrieve their registered profile, card accounts, and transaction history using the normal banking tools. Match a transaction by the requested card, merchant, date, and amount; if more than one candidate remains, ask for clarification rather than guessing.
2. For every involved account, unlock the discovered agent tool `get_card_last_4_digits`, then call it through `call_discoverable_agent_tool` with the account's `credit_card_account_id`. Use its returned four digits in the dispute payload. This is appropriate even when the customer does not have the digits available.
3. Unlock and call discovered tool `get_user_dispute_history_7291` with the canonical `user_id`. Retain the returned dispute dates for the provisional-credit calculation. A failed, malformed, or partial history result means eligibility cannot be safely established; resolve the tool/data problem before filing a dispute that requires this field.
4. Obtain the current date/time with the normal time tool. Determine provisional eligibility independently for each transaction using the criteria below, or run `scripts/evaluate_provisional_credit.py` after supplying the retrieved data. A customer is eligible only when **all** criteria pass:
   - the pertinent card account has been open at least 60 days as of filing;
   - reason is fraud, duplicate charge, or goods/services not received;
   - for goods/services not received, the purchase was more than 30 days before filing;
   - transaction amount is at least $25 and no more than the tier limit;
   - no more than two disputes were filed in the preceding 12 months; and
   - for any non-fraud reason, the customer contacted the merchant.

   Tier limits: Entry (Bronze Rewards, EcoCard, Business Bronze Rewards, Crypto-Cash Back) $2,500; Mid (Silver Rewards, Business Silver Rewards, Green, Silver Zoom) $5,000; Premium (Gold Rewards, Business Gold Rewards) $10,000; Elite (Platinum, Business Platinum) $15,000; Invitation (Diamond Elite) $25,000. An unknown tier or missing required datum produces `eligible_for_provisional_credit: false` unless the information can be resolved before filing.
5. Validate every payload before submitting: dates must be `MM/DD/YYYY`; enum values must be exact; all profile fields must be registered values; last four must be exactly four digits; and the transaction/card data must match the retrieved records. The customer selecting `keep_active` applies to fraud claims as well when they explicitly want to retain the card.
6. Unlock `file_credit_card_transaction_dispute_4829` once, then call it through `call_discoverable_agent_tool` once per validated dispute. Send `arguments` as a JSON string. Required argument shape:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active | cancel_and_reissue",
  "card_last_4_digits": "1234",
  "full_name": "registered full name",
  "user_id": "canonical user id",
  "phone": "registered phone",
  "email": "registered email",
  "address": "registered address",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "permitted reason code",
  "resolution_requested": "full_refund | partial_refund | reversal_of_charge",
  "eligible_for_provisional_credit": false
}
```

For `partial_refund`, additionally include `"partial_refund_amount": 0.0`. Do not include a guessed partial amount. Keep an exact record of each tool response. If a submission returns an error or unknown outcome, report that status and do not repeat the operation blindly.
7. Summarize only the disputes actually accepted by the filing tool, including each transaction and whether it was eligible for provisional credit. Clearly state any deferred/excluded transactions and the information needed to proceed. Provisional credit is temporary and eligibility does not guarantee the final dispute outcome.

## Eligibility helper

`scripts/evaluate_provisional_credit.py` is a deterministic local evaluator. It accepts one JSON object on stdin and emits one JSON object on stdout; it does not call bank tools or submit disputes.

Input schema:

```json
{
  "filing_date": "MM/DD/YYYY or ISO datetime/date",
  "account_open_date": "MM/DD/YYYY or ISO datetime/date",
  "card_type": "card tier name",
  "purchase_date": "MM/DD/YYYY or ISO datetime/date",
  "amount": 100.0,
  "dispute_reason": "reason code",
  "contacted_merchant": true,
  "prior_dispute_dates": ["MM/DD/YYYY or ISO datetime/date"]
}
```

Example invocation in the Skill runtime: `python scripts/evaluate_provisional_credit.py < input.json`. Its output includes `eligible`, the recognized limit, the trailing-12-month count, and explicit failed checks. Treat malformed or incomplete input as not eligible and resolve it with the relevant bank tool before filing.
