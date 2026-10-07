---
name: credit-card-transaction-dispute
version: 1.0.0
description: File a formal Rho-Bank credit-card transaction dispute when a customer reports fraud, duplicate billing, an amount error, missing or misrepresented goods/services, unwanted subscription charges, or a missing promised refund. Use it to collect and validate every required dispute field, retrieve the card last four digits through the discovered tool, determine provisional-credit eligibility, and submit the internal dispute.
---

# Credit Card Transaction Dispute

## Required outcome
File the dispute only through `file_credit_card_transaction_dispute_4829`. First unlock it with `unlock_discoverable_agent_tool`, then invoke it using `call_discoverable_agent_tool` and a JSON-string argument object. A successful tool response is the filing confirmation; do not claim the dispute was filed before that response.

## Intake and record matching

1. Identify the customer and follow any runtime identity-verification requirement before accessing or acting on account information. If two identity fields are confirmed, obtain the current timestamp and call `log_verification` with the complete registered record.
2. Identify the exact completed transaction. Confirm the merchant, amount, purchase date, and the specific card where ambiguity is possible. Never select a transaction merely because its merchant name is similar.
3. Obtain the registered `full_name`, `user_id`, `phone`, `email`, and `address` from the verified customer record. Preserve their registered values for the filing.
4. Determine `card_action` from the customer's request:
   - `keep_active` when they only want the charge disputed and intend to keep the card usable.
   - `cancel_and_reissue` only when they want the affected card replaced/cancelled, including when replacement has already been ordered.
   Ask if this is unclear; do not cancel or replace a card solely because a dispute is being filed.
5. Obtain the last four digits for the account that made the transaction. The transaction's card type must match the selected card account. Unlock `get_card_last_4_digits` and call it with `credit_card_account_id`, then use its returned four digits as `card_last_4_digits`. If the runtime makes this tool customer-executable rather than agent-executable, pass the exact tool and selected account ID using `give_discoverable_user_tool` and wait for the result. Do not use a full card number or guess four digits.

## Gather filing facts

Collect or confirm all of the following before filing:

- `transaction_id` from the matched transaction.
- `purchase_date` in `MM/DD/YYYY` from that transaction.
- `issue_noticed_date` in `MM/DD/YYYY`; translate relative dates such as “today” using the runtime's current date, not the agent's assumed date.
- `contacted_merchant` as a boolean. Ask whether the customer tried to resolve the matter with the merchant; do not infer it unless the customer explicitly says so.
- `dispute_reason`, exactly one of:
  `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`.
- `resolution_requested`, exactly one of `full_refund`, `partial_refund`, or `reversal_of_charge`. Ask rather than treating a general complaint as a particular option when this is ambiguous.
- A numeric positive `partial_refund_amount` only for `partial_refund`; omit the field for the other resolution choices.

Do not file while a mandatory fact is unavailable or invalid. Explain the missing item and obtain it through the supported account/discoverable tool or from the customer. If the selected transaction cannot be confidently matched, ask the customer to clarify rather than filing a different transaction.

## Provisional-credit decision

Use `scripts/eligibility.py` to make the repeatable portion of the decision. It accepts JSON on stdin and returns JSON on stdout. The required input object is:

```json
{
  "account_open_date": "MM/DD/YYYY",
  "reference_date": "MM/DD/YYYY",
  "purchase_date": "MM/DD/YYYY",
  "transaction_amount": 0.0,
  "card_type": "card type from the account record",
  "dispute_reason": "one permitted reason",
  "contacted_merchant": true,
  "previous_disputes_12_months": 0
}
```

Example invocation in a Python-capable executor: send that object to `scripts/eligibility.py` through the supplied script runtime, then read `eligible_for_provisional_credit`, `blockers`, and `missing_fields` from its JSON result.

Pass `eligible_for_provisional_credit: true` only when every criterion is affirmatively established: account open at least 60 days; an eligible reason; amount at least $25 and no greater than the applicable tier limit; no more than two disputes in the prior 12 months; merchant contacted for non-fraud; and, for `goods_services_not_received`, the purchase was more than 30 days before the reference date. The helper is deliberately conservative: unknown required facts result in `false`, never a speculative `true`. Reasons outside the eligible set always yield false.

Tier limits are: $2,500 Entry (Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card); $5,000 Mid (Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card); $10,000 Premium (Gold Rewards Card, Business Gold Rewards Card); $15,000 Elite (Platinum Rewards Card, Business Platinum Rewards Card); and $25,000 Invitation (Diamond Elite Card). An unsupported card type is not sufficient to approve provisional credit.

## Submit and validate

Construct the tool arguments with exactly these required keys:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active or cancel_and_reissue",
  "card_last_4_digits": "four digits",
  "full_name": "registered name",
  "user_id": "registered user id",
  "phone": "registered phone",
  "email": "registered email",
  "address": "registered address",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "permitted enum",
  "resolution_requested": "permitted enum",
  "eligible_for_provisional_credit": false
}
```

Add `partial_refund_amount` as a JSON number only when requested. Before calling, validate enum values, exactly four card digits, parseable dates, booleans (not strings), the transaction/card match, and the conditional partial amount. Unlock `file_credit_card_transaction_dispute_4829`, call it with the serialized object, and inspect the response. If it reports a validation or system failure, do not represent the dispute as filed; correct only supported input errors or explain/escalate according to runtime procedures. After success, summarize the submitted dispute and accurately describe provisional credit as temporary and subject to investigation when it applies.
