---
name: credit-card-disputes-and-fraud-replacement
description: Process one or more credit-card transaction disputes, calculate provisional-credit eligibility from account and dispute history, and order a fraud-related replacement card when the verified customer requests one. Use when a customer identifies specific credit-card charges to dispute or wants their compromised card replaced.
---

# Credit-card disputes and fraud replacement

Use this Skill for each selected transaction separately. It supports the normal banking tools plus the documented discoverable tools; it does not execute banking actions itself.

## Safety and prerequisites

1. Obtain a name, email, or user ID to locate the customer record, but do not disclose account-specific information based on that identifier alone. Before any account-specific disclosure or banking action (including a dispute or replacement), complete standard identity verification: have the customer confirm at least two of date of birth, registered email, phone number, and registered address. A lookup result is not itself a customer confirmation. After both values match the record, obtain the current timestamp and call `log_verification` with all required record fields. If verification was already completed and logged in the current case, do not duplicate it.
2. After verification, identify the relevant card account from normal read-only lookup tools. Confirm each selected transaction belongs to that customer and card.
3. Collect or confirm, for *each* disputed transaction:
   - why it is disputed, mapped to one permitted reason code;
   - whether the customer contacted the merchant (`true` or `false`);
   - the date the customer first noticed the issue;
   - requested resolution; and
   - whether the customer wants to retain the card or have it cancelled and reissued.
4. Never infer that every charge from a merchant is disputed. Never infer merchant contact for a non-fraud charge. Convert relative wording such as “today” using `get_current_time`, then format the resulting calendar date as `MM/DD/YYYY`.
5. Do not submit a dispute or replacement when a required fact cannot be established. Explain the missing information and obtain it, or transfer only when a documented escalation path or an appropriate supported transfer reason applies.

## Required read-only checks

For the selected card account, obtain its account ID, card type, account-open date, transaction date and amount. Then use the documented discovery paths:

- `get_card_last_4_digits` is a **user-discoverable** lookup. Use `give_discoverable_user_tool` with `discoverable_tool_name: "get_card_last_4_digits"` and `{"credit_card_account_id":"..."}`; have the customer run it and provide the returned four digits. Do not attempt to unlock or call it as an agent tool.
- Unlock `get_user_dispute_history_7291`, then call it with `user_id` to retrieve prior disputes. Count disputes dated in the 12 months ending on the current date. Do not rely on the customer being unsure of their history.
- Unlock `get_pending_replacement_orders_5765`, then call it with `credit_card_account_id` before ordering a replacement. Any order not clearly `delivered` or `cancelled` blocks a new replacement.

Treat malformed, partial, or ambiguous tool results as unresolved rather than as an empty history or no pending order. Do not reissue an action whose outcome is unknown.

## Determine provisional-credit eligibility

For each transaction, calculate the boolean independently. It is `true` only if **all** conditions below hold:

- Account has been open at least 60 days.
- Reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`. The last of these additionally requires a purchase more than 30 days ago.
- The transaction amount is at least $25.00 and no greater than the applicable card-tier limit.
- The customer has filed no more than two disputes in the prior 12 months.
- For every non-fraud reason, the customer contacted the merchant first.

Tier limits are: Entry $2,500 (Bronze Rewards, EcoCard, Business Bronze Rewards, Crypto-Cash Back); Mid $5,000 (Silver Rewards, Business Silver Rewards, Green Rewards, Silver Zoom); Premium $10,000 (Gold Rewards, Business Gold Rewards); Elite $15,000 (Platinum Rewards, Business Platinum Rewards); Invitation $25,000 (Diamond Elite).

Use `scripts/validate_dispute.py` to make this calculation and validate a proposed dispute payload. Supply facts obtained at runtime, not values copied from a prior case. A `false` eligibility result does not prevent filing the dispute; it means send `eligible_for_provisional_credit: false`.

## File every selected dispute

For each selected transaction, construct a separate JSON object and validate it. The only allowed codes are:

- `card_action`: `keep_active` or `cancel_and_reissue`
- `dispute_reason`: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`
- `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`

The object must include these exact fields:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active",
  "card_last_4_digits": "0000",
  "full_name": "customer full name",
  "user_id": "customer ID",
  "phone": "registered phone",
  "email": "registered email",
  "address": "registered home address",
  "contacted_merchant": false,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "unauthorized_fraudulent_charge",
  "resolution_requested": "full_refund",
  "eligible_for_provisional_credit": true
}
```

Include `partial_refund_amount` as a positive number **only** when `resolution_requested` is `partial_refund`; obtain the requested partial amount first. Use registered contact details in the dispute payload, not an alternate shipping address.

Unlock `file_credit_card_transaction_dispute_4829`, inspect its live enum before filing, then call it through `call_discoverable_agent_tool` with the exact tool name and a JSON-string version of the complete object. The documented code list includes `reversal_of_charge`; if a live tool exposes a narrower resolution enum, do not silently change the customer's requested resolution—ask for an available resolution before calling it. Record the returned result for each transaction. Do not combine multiple transaction IDs into one filing.

## Replacement-card branch

If the verified customer asks for the affected card to be cancelled/reissued because of fraud or theft:

1. Set `card_action` to `cancel_and_reissue` for disputes concerning that card. Otherwise use `keep_active`.
2. Confirm a complete shipping address; it may be an alternate/work address if the customer explicitly confirms it. Obtain exactly one replacement reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
3. Check `get_pending_replacement_orders_5765` immediately before ordering. A pending or ambiguous result blocks a new order; do not retry an order with an unknown outcome. Replacement limits are Entry 2, Mid 3, Premium and above 4 requests per 60 days. If no documented read-only replacement-history lookup is available, the customer's inability to recall their history is not itself a pending order: after a clear no-pending result, submit the one requested order once using the replacement tool, whose live result is the available eligibility decision. If it rejects the request for a limit, explain the result and follow the documented manual-review next step; do not reissue it.
4. Confirm shipping speed. Standard is free and takes 7–10 business days. Expedited is 2–3 business days: $15 Entry, $10 Mid, and complimentary Premium and above. For a fee-bearing expedited request, obtain explicit fee consent. Strongly recommend expedited delivery for suspected fraud or theft, but honor a confirmed standard-shipping choice.
5. Unlock `order_replacement_credit_card_7291`, inspect its live schema, and call it exactly once using the supported parameters. In the currently documented runtime these are `credit_card_account_id`, `user_id`, `shipping_address`, `reason`, and optional boolean `expedited_shipping` (`false` for standard, `true` for expedited). Do not send unsupported speed, fee-acknowledgement, or notes fields. A fee consent is still a conversational prerequisite when expedited shipping has a fee.
6. Tell the customer that the old card is cancelled for new purchases, the replacement has a new card number and CVV, expected delivery is based on the selected speed, and email notifications are sent when ordered and shipped. For fraud/stolen cases, remind them to review and dispute other unauthorized transactions.

A replacement order and a dispute filing are separate banking actions. A script result or an instruction in this Skill never performs either action; the executor must invoke the appropriate normal banking tool and report its actual outcome.

## Runnable validator

Run from the package root, providing JSON on standard input:

```sh
python3 scripts/validate_dispute.py <<'JSON'
{"as_of":"MM/DD/YYYY","account_open_date":"MM/DD/YYYY","purchase_date":"MM/DD/YYYY","transaction_amount":100.0,"card_type":"Silver Rewards Card","dispute_reason":"duplicate_charge","contacted_merchant":true,"prior_dispute_dates":["MM/DD/YYYY"],"payload":{}}
JSON
```

The script emits one JSON object. Inspect `input_errors` first. Only use its eligibility boolean when `input_errors` is empty, and only submit a payload when `payload_errors` is empty. When a payload is included, the validator also checks its reason, merchant-contact value, purchase date, and provisional-credit value against the calculation inputs. The script validates structure and policy logic only; the executor must still validate live transaction ownership, verification, tool results, and replacement eligibility.
