---
name: credit-card-dispute-and-replacement
version: 1.0.0
description: Process one or more credit-card transaction disputes, determine provisional-credit eligibility, and, when requested for compromise or fraud, safely coordinate a replacement-card request. Use when transaction, account, and verified-customer information can be obtained through the supplied banking tools.
---

# Credit-card dispute and replacement workflow

Use this Skill for formal credit-card transaction disputes. A dispute filing is a separate action for each transaction. Do not use it for a charge that has not been identified in transaction history.

## 1. Establish the customer and card

1. Follow the runtime's identity-verification procedure before any account-changing action. Where `log_verification` is available, confirm at least two of date of birth, registered email, registered phone, and registered address, then get the current timestamp and log the complete verified record.
2. Look up the customer, their credit-card accounts, and transaction history. Match each selected transaction by transaction ID, date, amount, merchant, and card type; do not infer a transaction ID merely from a similar amount.
3. Obtain the account ID for the card on which the transaction occurred. Obtain its last four digits with `get_card_last_4_digits(credit_card_account_id)`. If the environment makes this a discoverable agent tool, unlock it before calling it. If policy/environment instead requires customer self-service, provide the customer that exact tool and account ID. Never substitute an unverified last-four value.
4. Collect or derive for **each** transaction: a permitted reason code, whether the customer contacted the merchant, purchase date, issue-noticed date, and a permitted requested resolution. “Today” may be converted to `MM/DD/YYYY` only after consulting the supplied current-time result. Ask if it remains ambiguous.
5. Use registered customer data for the dispute payload: full name, user ID, registered phone, registered email, and registered home address. A work/alternate shipping address is not the dispute address.

Allowed codes:

- Reasons: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`.
- Resolution: `full_refund`, `partial_refund`, `reversal_of_charge`.
- Card action: `keep_active` or `cancel_and_reissue`.

Use `cancel_and_reissue` when the customer requests cancellation/replacement because of suspected compromise; otherwise use `keep_active`. A partial refund additionally requires a positive numeric `partial_refund_amount`; omit that key for all other resolutions.

## 2. Determine provisional-credit eligibility

Before filing, retrieve dispute history with `get_user_dispute_history_7291(user_id)` (unlock first if discoverable). Count disputes filed during the 12 months before the filing date. Determine the card’s tier from its account type and transaction amount from the matched transaction. Apply every criterion, not merely the reason:

- Account has been open at least 60 days.
- Reason is `unauthorized_fraudulent_charge` or `duplicate_charge`, or it is `goods_services_not_received` and the purchase is more than 30 days old.
- Amount is at least $25 and no more than the card-tier cap: entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000.
- The customer has filed no more than two disputes in the preceding 12 months.
- For every non-fraud reason, the customer contacted the merchant.

Set `eligible_for_provisional_credit` to `false` if any criterion fails or a required fact cannot be verified. Explain that provisional credit, if eligible, is temporary during investigation. The packaged script can validate a candidate payload and calculate this decision; it does not file disputes.

## 3. Replacement-card branch

Perform this branch only when the customer also wants a replacement. Confirm the shipping address (including unit/suite), the single replacement reason, and shipping speed. The replacement reason must be one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.

Before ordering, check for outstanding replacements using `get_pending_replacement_orders_5765(credit_card_account_id)` (unlock if required). Do not place another request while an existing order is pending/shipped/non-final. Confirm replacement eligibility, including the applicable 60-day tier limit (entry 2, mid 3, premium and above 4). If eligible, unlock `order_replacement_credit_card_7291` and call it with the account identifier, reason, confirmed shipping address, `standard` or `expedited`, fee acknowledgement where required, and useful notes.

Standard delivery is free and takes 7–10 business days. Expedited delivery is 2–3 business days; entry-tier costs $15, mid-tier costs $10, and premium-and-above is complimentary. Obtain explicit consent if a fee applies. Inform the customer that the old card is cancelled, the replacement has a different card number/CVV, and the account number remains unchanged.

If a replacement cannot be ordered because of a pending order or tier limit, do not repeatedly submit it. Explain the restriction and still process eligible dispute filings with the card action matching the actual requested/available cancellation handling.

## 4. File and report

For each complete, validated dispute:

1. Unlock `file_credit_card_transaction_dispute_4829`.
2. Call it using `call_discoverable_agent_tool` and a JSON string containing exactly the required data: `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`. Include `partial_refund_amount` only for a partial-refund request.
3. Record the response and clearly summarize which individual disputes and replacement request were submitted. Do not claim approval, a permanent refund, or replacement shipment until the respective tool confirms it.

If required facts are absent, ask only for the unresolved facts and do not submit a malformed filing. If a tool returns `UNKNOWN`, do not repeat that operation; report/escalate according to the runtime procedure.

## Helper script

`scripts/prepare_dispute.py` accepts one JSON object on stdin and emits one JSON object on stdout. It accepts `dispute` (the candidate tool payload), `account_open_date`, `filing_date`, `transaction_amount`, `card_type`, and `prior_disputes_last_12_months`. It validates payload fields and computes `eligible_for_provisional_credit`. It returns `ok`, `errors`, `payload` (only if valid), and `eligibility_checks`. Dates must be `MM/DD/YYYY`; currency inputs may be JSON numbers or strings such as `"$124.50"`.

Example invocation in a shell-capable executor:

```sh
printf '%s' '{"dispute":{"transaction_id":"...","card_action":"keep_active","card_last_4_digits":"1234","full_name":"...","user_id":"...","phone":"...","email":"...","address":"...","contacted_merchant":true,"purchase_date":"01/01/2025","issue_noticed_date":"02/01/2025","dispute_reason":"duplicate_charge","resolution_requested":"full_refund"},"account_open_date":"01/01/2024","filing_date":"02/01/2025","transaction_amount":"89.99","card_type":"Silver Rewards Card","prior_disputes_last_12_months":0}' | python3 scripts/prepare_dispute.py
```

Before using the output as a tool argument, require `ok: true`, check that the resolved transaction and registered customer fields agree with tool results, and use the script-produced boolean rather than guessing eligibility.
