---
name: credit-card-dispute-intake-and-filing
description: Safely prepare and file one or more credit-card transaction disputes, including required intake validation, provisional-credit determination, card replacement coordination, and discoverable-tool workflow. Use when a customer identifies specific credit-card transactions for dispute.
---

# Credit Card Dispute Intake and Filing

Use this Skill after the customer has identified the transaction(s) they want to dispute. File each transaction as a separate dispute. Do not substitute a merchant/date/amount description for a verified transaction ID.

## Required information and verification

1. Complete standard identity verification before any account-changing action. Ask the customer to confirm **two of the four** profile fields (date of birth, email, phone, address); lookup data is not itself verification.
2. After two fields match the profile, get the current timestamp with `get_current_time` and call `log_verification` with the complete required audit record.
3. Obtain or confirm the customer profile, credit-card account, and transaction record using normal banking tools. Verify that each selected transaction belongs to the customer and that its merchant, date, amount, and card match the customer’s selection.
4. For every selected transaction, collect:
   - dispute reason;
   - when the issue was noticed;
   - whether the merchant was contacted (required question for all non-fraud disputes);
   - requested resolution, plus a positive partial-refund amount if applicable; and
   - whether the card should remain active or be cancelled/reissued when relevant.

Use only these reason codes:
`unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`.

Use only these resolution codes: `full_refund`, `partial_refund`, `reversal_of_charge`.

Use only these card actions: `keep_active`, `cancel_and_reissue`.

## Required supporting lookups

- Retrieve the disputed card’s last four digits with `get_card_last_4_digits(credit_card_account_id)`. The knowledge-base direction for support agents is to give this discovered tool to the user with `give_discoverable_user_tool`, then wait for the result; do not ask the customer to disclose a full card number.
- Retrieve the customer’s dispute history with `get_user_dispute_history_7291(user_id)`. Unlock it first if the runtime requires discovery-tool unlocking. Count disputes already filed during the 12 months before filing this batch. Do not let newly submitted disputes in the same batch change that baseline.
- If cancellation/reissue is requested, follow the replacement-card requirements in addition to the dispute requirements:
  1. Confirm the shipping address, replacement reason (`fraud_suspected` for suspected fraud), and standard versus expedited shipping.
  2. Determine replacement eligibility, including the 60-day tier replacement limit, before unlocking or calling the replacement tool.
  3. Check `get_pending_replacement_orders_5765(credit_card_account_id)` immediately before ordering. A pending or shipped order blocks another replacement order.
  4. If eligible and unblocked, unlock and call `order_replacement_credit_card_7291` with the account identifier, reason, confirmed shipping address, speed, required fee acknowledgement when a fee applies, and notes. For fraud or stolen cards, strongly recommend expedited shipping. Explain that the old card is cancelled and that delivery is 7–10 business days standard or 2–3 business days expedited.
  5. Do not silently change a requested `cancel_and_reissue` action to `keep_active`. If replacement cannot proceed, explain why and obtain the customer’s direction before filing a different-action dispute.

For a requested reissue, use `cancel_and_reissue` for every dispute tied to the affected card. A replacement may be ordered before the disputes; retain the last four digits of the card on which the disputed transactions occurred.

## Provisional-credit decision

Determine this separately for every dispute. A dispute is eligible only if **all** conditions hold:

1. The account has been open at least 60 days.
2. Reason is unauthorized/fraudulent, duplicate, or goods/services not received where the purchase was more than 30 days ago.
3. The transaction is at least $25 and no more than the tier maximum: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000.
4. The customer filed no more than two disputes in the prior 12 months.
5. For every non-fraud reason, the customer contacted the merchant first.

A failed eligibility criterion does not prevent filing the dispute; send `eligible_for_provisional_credit: false`. Missing information needed to determine eligibility does prevent filing until it is obtained.

## Build and validate payloads

Use `scripts/build_dispute_plan.py` to consistently validate the collected data and produce one exact dispute payload per transaction. The script performs no banking action.

Input is JSON on stdin:

- `current_date`: `MM/DD/YYYY`.
- `profile`: `full_name`, `user_id`, `phone`, `email`, `address`.
- `accounts`: objects with `account_id`, `card_type`, `date_of_account_open` (`MM/DD/YYYY`), and `card_last_4_digits`.
- Either `prior_dispute_count_12_months` (a nonnegative integer calculated from the history lookup) or `prior_disputes` (objects containing `dispute_date`).
- `disputes`: one object per selected verified transaction containing `transaction_id`, `account_id`, `transaction_amount`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, `contacted_merchant`, and `card_action`. Include `partial_refund_amount` only for partial refunds.

Example invocation with placeholders:

```sh
python scripts/build_dispute_plan.py <<'JSON'
{"current_date":"MM/DD/YYYY","profile":{"full_name":"<name>","user_id":"<user-id>","phone":"<phone>","email":"<email>","address":"<address>"},"accounts":[{"account_id":"<account-id>","card_type":"Gold Rewards Card","date_of_account_open":"MM/DD/YYYY","card_last_4_digits":"1234"}],"prior_dispute_count_12_months":0,"disputes":[{"transaction_id":"<transaction-id>","account_id":"<account-id>","transaction_amount":100.0,"purchase_date":"MM/DD/YYYY","issue_noticed_date":"MM/DD/YYYY","dispute_reason":"duplicate_charge","resolution_requested":"full_refund","contacted_merchant":true,"card_action":"keep_active"}]}
JSON
```

The script emits JSON with `ok`, `validation_errors`, a per-dispute eligibility explanation, and `payloads`. Proceed only if `ok` is true. `payloads` contain precisely the fields for `file_credit_card_transaction_dispute_4829`; non-partial payloads omit `partial_refund_amount`.

## Filing workflow

1. Resolve every validation error or unavailable eligibility input. A valid plan may still contain ineligible provisional-credit results.
2. Unlock `file_credit_card_transaction_dispute_4829`.
3. For each generated payload, call `call_discoverable_agent_tool` with `agent_tool_name: file_credit_card_transaction_dispute_4829` and the payload serialized as the `arguments` JSON string.
4. Preserve each tool result and tell the customer which disputes were submitted. Explain provisional credit only according to the calculated result; it is temporary and may be reversed after investigation.
5. If a tool call fails, do not claim submission for that transaction. Retain the failure context and retry or escalate through the applicable support process. Do not retry a transaction blindly after an ambiguous response.

The script does not unlock tools, query customer data, place a replacement order, or file a dispute. Those are execution-agent actions using the normal banking tools.
