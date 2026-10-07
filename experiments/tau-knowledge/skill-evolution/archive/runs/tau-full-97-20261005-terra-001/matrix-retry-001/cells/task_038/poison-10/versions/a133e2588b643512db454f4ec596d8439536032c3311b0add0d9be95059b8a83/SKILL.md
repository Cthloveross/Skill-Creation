---
name: credit-card-dispute-and-compromised-card-replacement
description: Process one or more credit-card transaction disputes, calculate provisional-credit eligibility, and, when requested, safely replace the affected compromised card. Use when customer statements and account or transaction records must be gathered and submitted through documented banking tools.
---

# Credit Card Dispute and Replacement Workflow

Use this Skill for credit-card transaction disputes and an optional replacement of the affected card. File one dispute per selected transaction. A request to replace a card does not authorize disputes for unrelated transactions.

## 1. Verify identity before account-changing actions

Before filing a dispute or ordering a replacement, confirm two of the four profile fields directly with the customer: date of birth, email, phone number, or registered address. A value retrieved from a profile is not a customer confirmation.

Once two values match the profile, call `get_current_time`, then call `log_verification` with the complete retrieved profile, name, user ID, and returned timestamp. If fewer than two fields are confirmed, request another verification field and do not file disputes, cancel the card, or order a replacement.

## 2. Locate and present all matching transactions

Use the verified user's transaction and card-account records. Identify completed transactions matching the merchant/card context the customer describes.

**Completeness rule:** Treat each transaction-history record as independent. Before asking the customer to select charges, enumerate **every** record that matches the requested merchant, affected card type, and completed status. Include each transaction's amount and full `MM/DD/YYYY` date. Do not stop after a presumed duplicate, a fixed count, or a date range unless the customer explicitly supplied that restriction. Reconcile the number of presented items to the number of matching records before sending the selection prompt.

Ask the customer which listed transaction(s) they want disputed. For every selected transaction, retain its transaction ID, amount, purchase date, and card type. Confirm that all selected transactions belong to the same card if a replacement is requested.

Obtain for each selected transaction:

- one exact `dispute_reason`: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`;
- whether the customer contacted the merchant;
- the date the issue was noticed;
- one exact `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`;
- a positive `partial_refund_amount` only for `partial_refund`.

Resolve a relative date such as “today” using the current service date and send dates as `MM/DD/YYYY`. If the customer explicitly calls a transaction a duplicate, use `duplicate_charge`.

## 3. Obtain required card last four digits

A dispute requires the card last four digits. If unavailable, provide only the documented discoverable user tool, scoped to the account associated with the selected transactions:

```text
give_discoverable_user_tool(
  discoverable_tool_name="get_card_last_4_digits",
  arguments='{"credit_card_account_id":"<affected account ID>"}'
)
```

Do not ask for a full card number and do not submit disputes until the resulting last four digits are available and correspond to the affected account.

## 4. Determine provisional-credit eligibility per transaction

Before submission, retrieve dispute history using `get_user_dispute_history_7291` with the verified user ID; unlock it first if required by the runtime. Count returned disputes filed in the 12 months preceding the current date. Do not assume the history is empty.

Run the packaged evaluator for each selected transaction:

```text
python scripts/evaluate_provisional_credit.py <<'JSON'
{
  "account_open_date": "MM/DD/YYYY",
  "as_of_date": "MM/DD/YYYY",
  "card_type": "<card type>",
  "transaction_amount": 0.00,
  "purchase_date": "MM/DD/YYYY",
  "dispute_reason": "<reason enum>",
  "contacted_merchant": true,
  "disputes_past_12_months": 0
}
JSON
```

The script reads one JSON object and emits `valid_input`, `eligible_for_provisional_credit`, reasons, and calculated ages. It is a deterministic policy aid; retain its rationale with the case.

Eligibility is true only if: account age is at least 60 days; the reason is fraud, duplicate, or goods/services-not-received; goods/services-not-received is more than 30 days old; the amount is at least $25 and within the tier limit; no more than two disputes occurred in the prior 12 months; and the merchant was contacted for non-fraud disputes. Limits are $2,500 Entry, $5,000 Mid, $10,000 Premium, $15,000 Elite, and $25,000 Invitation. Missing eligibility inputs must not be guessed.

## 5. Replacement workflow

Perform this only when the customer asks to replace/cancel the affected card. In that case use `cancel_and_reissue` as `card_action` for disputes on that card; otherwise use `keep_active`.

Before ordering, confirm:

1. One replacement reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
2. The complete shipping address, including unit/suite if applicable.
3. `standard` or `expedited` shipping. Standard is free and 7–10 business days. Expedited is 2–3 business days and costs $15 for Entry, $10 for Mid, and $0 for Premium and above; obtain affirmative consent for any fee.
4. Pending replacement status using `get_pending_replacement_orders_5765` with the affected account ID, unlocking it first if necessary. Do not place another order if any order is pending or shipped.
5. Replacement eligibility and the 60-day tier cap: Entry 2, Mid 3, Premium and above 4. If the available records cannot establish the cap, do not bypass it.

After all prerequisites pass, unlock `order_replacement_credit_card_7291` and call it via `call_discoverable_agent_tool` with an account identifier, reason, confirmed `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and relevant notes. Do not state that an order exists unless the tool reports success.

A successful replacement cancels the old card, creates a new number and CVV, and preserves the account number. State the chosen delivery window and email notifications; for fraud or theft, remind the customer to review transactions.

## 6. Validate and submit disputes

Build and validate one payload per selected transaction:

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

The validator reads JSON on stdin and emits `{ "valid": bool, "errors": [string] }`. Include a positive numeric `partial_refund_amount` only for `partial_refund`.

Only if valid, unlock `file_credit_card_transaction_dispute_4829` and call it once per transaction through `call_discoverable_agent_tool`, passing the validated payload as its JSON-string arguments. Keep each tool result tied to its transaction. A requested refund is not a guaranteed outcome.

## Failure handling

- Ask for missing required facts or use only the documented retrieval method; never invent data.
- If identity is not verified or the card last four digits are unavailable, pause before disputes and replacement ordering.
- If a tool fails, do not claim success; preserve the result and explain the blocked step.
- If a replacement is blocked by a pending order or cap, explain the restriction and available manual-review/support path.
- Separately summarize successful disputes, provisional-credit determinations, and replacement status.
