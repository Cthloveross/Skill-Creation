---
name: credit-card-dispute-and-compromised-card-replacement
description: Process one or more credit-card transaction disputes, calculate provisional-credit eligibility, and—when the customer requests it—safely order a replacement for a compromised card. Use when transaction details, account details, and customer statements must be gathered and submitted through the documented dispute and replacement tools.
---

# Credit Card Dispute and Replacement Workflow

Use this Skill for a credit-card dispute, including a request to replace the affected card. A separate dispute must be filed for each transaction. Do not treat a request to replace a card as authorization to dispute unrelated transactions.

## 1. Verify identity before changes

Before filing a dispute or ordering a replacement, use standard verification. Confirm **two of four** profile fields directly with the customer: date of birth, email, phone number, or registered address. Do not count a value merely retrieved from a profile unless the customer supplied or confirmed it.

After two fields match the retrieved profile:

1. Call `get_current_time`.
2. Call `log_verification` with the complete profile values, customer name and user ID, and the timestamp returned by `get_current_time`.

If two fields have not been confirmed, ask only for another verification field. Do not file disputes, cancel a card, or order a replacement first.

## 2. Establish the affected card and transactions

Use the verified user's account and transaction records to identify the relevant completed transaction(s), their transaction IDs, dates, amounts, and the corresponding credit-card account. Ensure every selected transaction belongs to the same card for which the customer requests replacement.

For each selected transaction, obtain and record:

- the transaction ID and purchase date from transaction history;
- the card's account ID and tier from the card-account lookup;
- one exact `dispute_reason`:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- whether the customer contacted the merchant (`contacted_merchant`);
- when the customer noticed the problem;
- one exact `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`;
- `partial_refund_amount` only when the selected resolution is `partial_refund`.

Resolve relative dates such as “today” using the current date at the time of service, then send tool dates in `MM/DD/YYYY`. If the customer explicitly characterizes a transaction as a duplicate, use `duplicate_charge`; do not override their selected characterization based only on similar amount or merchant.

## 3. Obtain the last four digits safely

A dispute submission requires the card last four digits. If they are unavailable, provide the customer the documented discoverable user tool rather than asking for a full card number or giving alternative retrieval instructions:

```text
give_discoverable_user_tool(
  discoverable_tool_name="get_card_last_4_digits",
  arguments='{"credit_card_account_id":"<affected account ID>"}'
)
```

Wait for the resulting four digits and ensure they correspond to the affected account. Do not submit the dispute until this required value is available.

## 4. Determine provisional-credit eligibility independently per transaction

Retrieve the user's dispute history with `get_user_dispute_history_7291` using the user ID. If that tool is exposed only as an agent-discoverable tool in the runtime, unlock it before calling it. Count disputes filed during the 12 months before the current date; count the actual returned records rather than assuming an empty history.

Use the account open date, affected transaction amount and purchase date, card tier, merchant-contact answer, current date, and the history count. Run:

```text
python scripts/evaluate_provisional_credit.py <<'JSON'
{
  "account_open_date": "MM/DD/YYYY",
  "as_of_date": "MM/DD/YYYY",
  "card_type": "<card tier name>",
  "transaction_amount": 0.00,
  "purchase_date": "MM/DD/YYYY",
  "dispute_reason": "<reason enum>",
  "contacted_merchant": true,
  "disputes_past_12_months": 0
}
JSON
```

The script emits JSON with `eligible_for_provisional_credit`, `reasons`, and computed day counts. Its input dates must be calendar dates in `MM/DD/YYYY`; its output is a decision aid and must be retained with the case rationale.

Eligibility is true only when all of these are true:

- the account has been open at least 60 days;
- the reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
- for goods/services not received, the purchase was more than 30 days ago;
- the amount is at least $25.00 and does not exceed the card tier limit;
- no more than two disputes were filed in the preceding 12 months; and
- for a non-fraud reason, the customer attempted to resolve the issue with the merchant.

Limits are $2,500 for Entry, $5,000 for Mid, $10,000 for Premium, $15,000 for Elite, and $25,000 for Invitation tier. If an eligibility input cannot be established, do not guess; obtain it or mark the customer ineligible until it is established.

## 5. Optional replacement for a compromised card

Perform this section only if the customer asks to replace/cancel the card. Record `card_action` as `cancel_and_reissue` on every dispute for that card. Otherwise use `keep_active`.

Before ordering:

1. Confirm the replacement reason exactly as one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. Use `fraud_suspected` only when the customer reports suspected fraudulent use.
2. Confirm the shipping address, including unit or suite, and whether shipping is `standard` or `expedited`.
3. Explain standard shipping (7–10 business days, free) and expedited shipping (2–3 business days). For Entry tier, expedited costs $15; Mid tier costs $10; Premium and above are complimentary. Capture affirmative fee consent whenever a fee applies.
4. Check for outstanding orders using `get_pending_replacement_orders_5765` with the credit-card account ID (unlock first if required by the runtime). Do not submit another order when any order is pending or shipped. Delivered and cancelled orders are final.
5. Confirm replacement eligibility, including the 60-day tier replacement cap: Entry 2, Mid 3, Premium and above 4. If the records available to the executor cannot establish the cap, do not bypass it; seek the required review or explain that the order cannot yet be submitted.

Only after all prerequisites pass, unlock `order_replacement_credit_card_7291` and call it through `call_discoverable_agent_tool`. The JSON string must include the account identifier, reason, confirmed `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and relevant `notes`. Do not claim an order exists until the tool returns success.

A successful replacement cancels the old card, issues a card with a new number and CVV, and leaves the account number unchanged. Communicate the selected delivery window and email notifications. For fraud or theft, remind the customer to review transactions.

## 6. Validate and submit each dispute

Build one JSON payload per selected transaction. Before tool use, validate it:

```text
python scripts/validate_dispute_payload.py <<'JSON'
{
  "transaction_id": "<transaction ID>",
  "card_action": "keep_active",
  "card_last_4_digits": "1234",
  "full_name": "<verified profile name>",
  "user_id": "<verified user ID>",
  "phone": "<registered phone>",
  "email": "<registered email>",
  "address": "<registered home address>",
  "contacted_merchant": false,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "unauthorized_fraudulent_charge",
  "resolution_requested": "full_refund",
  "eligible_for_provisional_credit": true
}
JSON
```

For partial refunds, include a positive numeric `partial_refund_amount`. Do not include that field for another resolution. The validator emits `{ "valid": true, "errors": [] }` only for a structurally valid request.

When valid, unlock `file_credit_card_transaction_dispute_4829` once, then submit each payload using:

```text
call_discoverable_agent_tool(
  agent_tool_name="file_credit_card_transaction_dispute_4829",
  arguments="<JSON-serialized validated payload>"
)
```

All listed required fields must be present. The dispute tool accepts one transaction, so make one call per transaction and keep the returned confirmation or failure associated with that transaction. A full refund is the requested resolution, not a guarantee of the investigation outcome.

## Failure handling and closeout

- If a required detail is missing, ask for that detail or use only the documented retrieval method; never invent it.
- If identity remains unverified, do not perform account-changing actions.
- If a tool reports failure, do not state the dispute or replacement succeeded. Preserve the tool response, explain the blocked step, and follow the runtime's escalation process if needed.
- If a replacement cannot be placed because an order is pending or the replacement cap is exceeded, explain the restriction and the documented manual-review/support option.
- Summarize each successfully filed dispute, the provisional-credit determination as temporary and conditional where applicable, and the replacement status separately.
