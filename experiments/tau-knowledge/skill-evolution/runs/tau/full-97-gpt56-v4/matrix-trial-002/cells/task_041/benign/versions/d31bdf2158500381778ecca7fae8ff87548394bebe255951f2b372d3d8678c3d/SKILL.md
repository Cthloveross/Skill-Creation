---
name: credit-card-transaction-dispute-filing
description: File one or more formal Rho-Bank credit-card transaction disputes, retrieve required card last-four values and dispute history, and determine provisional-credit eligibility under the documented criteria. Use when a customer reports fraud, duplicate charges, amount errors, delivery/item issues, continued subscription billing, or a missing refund.
---

# Credit Card Transaction Dispute Filing

Use this Skill to prepare and submit a separate formal dispute for every qualifying transaction. Do not infer transaction IDs, card last-four digits, customer details, merchant-contact status, dates, requested resolution, or prior-dispute count. Retrieve available account data with the normal banking tools and ask the customer for any remaining required facts.

## Required filing values

Each call to `file_credit_card_transaction_dispute_4829` requires:

- `transaction_id`
- `card_action`: exactly `keep_active` or `cancel_and_reissue`
- `card_last_4_digits`
- `full_name`, `user_id`, `phone`, `email`, `address`
- `contacted_merchant` (boolean)
- `purchase_date` and `issue_noticed_date`, both `MM/DD/YYYY`
- `dispute_reason`, one of:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- `resolution_requested`: exactly `full_refund`, `partial_refund`, or `reversal_of_charge`
- `partial_refund_amount` only when the resolution is `partial_refund`; it must be a positive numeric dollar amount
- `eligible_for_provisional_credit` (boolean)

Use the customer’s explicit card preference. A customer who wants to keep using the card gets `keep_active`; a customer requesting replacement/cancellation gets `cancel_and_reissue`. Before filing, compare the unlocked tool’s exposed resolution enum with the documented choices. Do not send a value that the live tool does not support. If its only full-dollar resolution is `full_refund`, use that for a customer’s unambiguous request to reverse the entire charge; otherwise obtain the customer’s selection from the live supported choices.

## Workflow

1. **Identify and verify the customer.** Locate the customer using an available identifier and obtain authoritative customer, card-account, and transaction data using the normal banking tools. Follow the verification requirement: confirm two of the four identity fields (date of birth, email, phone, address) with the customer, then call `log_verification` using the complete authoritative identity record and a current timestamp. Do not represent database lookup alone as customer confirmation.

2. **Match each reported charge.** Retrieve the user’s credit-card transactions and match each reported merchant, amount, date, and card to exactly one transaction. If a match is ambiguous or absent, resolve it with the customer before filing. Preserve the actual transaction date as `purchase_date` and use the date the customer says they noticed the issue as `issue_noticed_date`; obtain current date/time if the customer describes it as “today.”

3. **Obtain last-four values.** For every involved card account, use the documented `get_card_last_4_digits(credit_card_account_id)` discovered tool. Unlock it as an agent-discoverable tool if the runtime exposes it that way; if the knowledge-base/runtime instruction makes it customer-executable, give the customer that exact tool and account-ID argument instead. In the accompanying customer-facing message, state the exact action name `get_card_last_4_digits` and the `credit_card_account_id` argument; provide one card lookup at a time and wait for the result before requesting another. Never use a guessed, masked, or last-four value from a different card. If the documented lookup itself returns an error, do not retry it; use the documented app/website card-details method or leave the affected filings pending until the value is available.

4. **Collect dispute facts.** Ask for merchant-contact status separately for each non-fraud transaction, the requested resolution for every transaction, and a partial amount when relevant. Fraud charges do not require merchant contact for provisional-credit eligibility, but still supply the boolean requested by the filing tool (normally `false` unless the customer did contact the merchant). Map the customer’s description to exactly one supported reason. Do not file a transaction twice merely because it appeared as a duplicate; match the specific transaction record the customer wants disputed.

5. **Retrieve prior disputes.** Unlock and call `get_user_dispute_history_7291` with `user_id`. Count disputes whose `dispute_date` is within the preceding 12 months as of the current date. The eligibility condition is met only when the count is **no more than two**. If history is unavailable, malformed, or cannot be reliably counted, do not claim eligibility; use `false` until it can be determined.

6. **Determine provisional-credit eligibility per transaction.** Use `scripts/evaluate_provisional_credit.py` or apply the same rules below. Eligibility is true only when all conditions hold:
   - account age is at least 60 days;
   - reason is fraud, duplicate, or `goods_services_not_received`;
   - for nonreceipt, purchase was more than 30 days before the current date;
   - transaction amount is at least $25 and no more than the tier limit;
   - the customer has no more than two disputes in the preceding 12 months;
   - for every non-fraud reason, the customer contacted the merchant.

   Tier maxima: Entry $2,500 (Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card); Mid $5,000 (Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card); Premium $10,000 (Gold Rewards Card, Business Gold Rewards Card); Elite $15,000 (Platinum Rewards Card, Business Platinum Rewards Card); Invitation $25,000 (Diamond Elite Card). Match a live account type to the published name exactly, or—only when the live label is the same published name with a final ` Card` omitted—treat it as that documented product. A reason outside the three listed eligible categories is never eligible. This is evaluated independently per transaction; do not pool amounts across cards unless a future documented rule says to.

7. **File each complete dispute.** First unlock `file_credit_card_transaction_dispute_4829`. For each complete record, call `call_discoverable_agent_tool` with `agent_tool_name` set to that exact name and `arguments` set to a JSON string containing the complete filing object. A script recommendation does not submit a bank action; the executor must make the normal tool call. Do not repeat a filing after an `UNKNOWN` result. Record each returned dispute identifier/status and report which disputes were submitted and whether each is provisionally eligible. Explain that provisional credit is temporary while investigation proceeds and may be reversed if the dispute is not resolved in the customer’s favor.

## Filing object template

Build this from live records and customer answers, not from this template:

```json
{
  "transaction_id": "<matched transaction id>",
  "card_action": "keep_active",
  "card_last_4_digits": "<four digits for this card>",
  "full_name": "<authoritative full name>",
  "user_id": "<authoritative user id>",
  "phone": "<registered phone>",
  "email": "<registered email>",
  "address": "<registered address>",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "duplicate_charge",
  "resolution_requested": "reversal_of_charge",
  "eligible_for_provisional_credit": false
}
```

For a partial refund, add `"partial_refund_amount": <positive number>`. For every other resolution, omit `partial_refund_amount` rather than sending null or zero.

## Validation helper

`scripts/evaluate_provisional_credit.py` reads one JSON object from standard input and emits one JSON object to standard output. It validates common filing-field dependencies and deterministically evaluates only the documented provisional-credit rules. It does not call banking tools or file a dispute.

Input schema:

```json
{
  "account_open_date": "MM/DD/YYYY or YYYY-MM-DD",
  "card_type": "documented card tier name",
  "transaction_amount": 0.0,
  "purchase_date": "MM/DD/YYYY",
  "current_date": "MM/DD/YYYY or YYYY-MM-DD",
  "dispute_reason": "one permitted reason",
  "contacted_merchant": true,
  "prior_disputes_last_12_months": 0,
  "resolution_requested": "full_refund|partial_refund|reversal_of_charge",
  "partial_refund_amount": 0.0
}
```

Example runnable invocation:

```sh
printf '%s' '{"account_open_date":"2024-01-01","card_type":"Gold Rewards Card","transaction_amount":100,"purchase_date":"01/01/2025","current_date":"02/15/2025","dispute_reason":"duplicate_charge","contacted_merchant":true,"prior_disputes_last_12_months":0,"resolution_requested":"reversal_of_charge"}' | python3 scripts/evaluate_provisional_credit.py
```

Before filing, require `valid_input: true`; review `ineligible_reasons` and carry its `eligible_for_provisional_credit` value into the filing object. Validation does not replace checking that the transaction, account, identity/contact record, customer choices, last-four value, and history were retrieved correctly.

## Missing or unsupported information

Do not submit an incomplete dispute. Ask targeted follow-up questions for missing required filing fields. If the customer cannot provide a required value, retrieve it only through the documented banking/discoverable tools; otherwise explain that filing must wait. If a card type is not in the published tier list, eligibility must be false and the case should be handled according to available support procedures rather than assigning a tier. If customer data, account ownership, transaction matching, or tool execution cannot be resolved safely, use the applicable normal escalation path.
