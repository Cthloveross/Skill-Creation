---
name: file-credit-card-transaction-dispute
description: File a formal Rho-Bank credit-card transaction dispute after identifying the exact transaction, retrieving the card's last four digits, collecting all mandatory customer/dispute fields, and determining provisional-credit eligibility. Use for unauthorized charges, billing errors, duplicate charges, merchant/service problems, and refund issues.
---

# Credit Card Transaction Dispute

## Required workflow

1. Identify and verify the customer under normal verification procedures before using or disclosing account data. Obtain the canonical `user_id`, registered full name, phone, email, and address. When required by the runtime, confirm two identity fields and log verification.
2. Retrieve the customer's card accounts and transactions. Select the transaction that matches the customer's report; do not infer a transaction where multiple candidates remain.
3. Identify the card account that owns that transaction. Retrieve its last four digits with the documented `get_card_last_4_digits(credit_card_account_id: str)` tool. Follow the runtime's discovered-agent-tool access pattern: unlock it first when applicable, then call it with the account ID, never a card number. Do not file until an exact four-digit result is obtained.
4. Collect or confirm every filing field:
   - `card_action`: exactly `keep_active` or `cancel_and_reissue`.
   - `contacted_merchant`: explicit boolean. For non-fraud disputes, ask whether they tried to resolve it with the merchant.
   - `issue_noticed_date` in `MM/DD/YYYY`; resolve relative dates such as “today” using the current-time tool.
   - one allowed `dispute_reason` and one allowed `resolution_requested`.
   - `partial_refund_amount` when, and only when, resolution is `partial_refund`.
   - A request for all money back can be confirmed/mapped to `full_refund`; otherwise ask the customer to choose the requested resolution.
5. Retrieve dispute history using `get_user_dispute_history_7291` and use the account opening date, transaction amount, card tier, purchase date, merchant-contact result, and current date to determine provisional-credit eligibility. Run `scripts/prepare_dispute.py` to validate inputs and calculate this value. Do not substitute an unknown value for the required boolean.
6. Only if the script reports `ready: true`, unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool` with `agent_tool_name` set to that exact name and `arguments` set to the JSON-serialized `payload` from the script. The script output is a recommendation/payload only; it does not file a dispute.
7. Report the actual filing result. If a required fact, card digits, transaction match, or eligibility input cannot be obtained, explain what is missing and do not unlock or call the filing tool.

## Retrieval failure and human escalation

The card last four digits are mandatory. Never fabricate them, infer them from an account ID, or send an incomplete direct or discoverable-wrapper filing.

If the documented last-four retrieval is unavailable or fails and the customer requests a human agent, call `transfer_to_human_agents` with reason `technical_system_error`. State that a formal dispute was **not filed** because the required card last four digits could not be obtained. The transfer summary must preserve actionable handoff context using the actual case values:

- verified customer name and `user_id`;
- transaction ID, merchant, amount, purchase date, and relevant card type/account;
- issue-noticed date;
- explicit merchant status using the phrase `contacted merchant: true` or `contacted merchant: false`;
- requested card action (`keep_active` or `cancel_and_reissue`);
- dispute reason and requested resolution, preferably their exact policy enums;
- provisional-credit result when determinable, including `eligible_for_provisional_credit: false` when the reason is ineligible;
- relevant dispute-history result, if obtained; and
- the exact technical blocker, including `get_card_last_4_digits` and that it was unavailable or did not return four digits.

For example, compose the summary from facts rather than fixed values: `Customer [name] ([user_id]) requests dispute of [merchant] transaction [transaction_id], [amount], purchase date [purchase_date]. Issue noticed [noticed_date]; contacted merchant: [true/false]. Requested card action: [card_action]; reason: [reason]; resolution: [resolution]; eligible_for_provisional_credit: [value]. No dispute filed: get_card_last_4_digits for [account_id] was unavailable/failed and no required four-digit result was obtained.`

Do not transfer solely because a field is missing when the customer has not requested escalation; instead explain the missing requirement and the supported way to obtain it.

## Reason and eligibility rules

Permitted reasons are:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Provisional credit is true only when all applicable criteria hold: account open at least 60 days; amount at least $25 and no greater than the tier limit; no more than two disputes in the preceding 12 months; an eligible reason; and merchant contact for a non-fraud reason. Eligible reason categories are fraudulent charge, duplicate charge, and goods/services not received only when its purchase is more than 30 days old. `goods_services_not_as_described`, incorrect amount, cancelled subscription, and unprocessed refund are never eligible. Limits are $2,500 for Entry, $5,000 for Mid, $10,000 for Premium, $15,000 for Elite, and $25,000 for Invitation cards.

## Validation helper

Run:

```text
python3 scripts/prepare_dispute.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. It performs no banking action.

Input schema:

```json
{
  "dispute": {
    "transaction_id": "string",
    "card_action": "keep_active|cancel_and_reissue",
    "card_last_4_digits": "four digits",
    "full_name": "string",
    "user_id": "string",
    "phone": "string",
    "email": "string",
    "address": "string",
    "contacted_merchant": true,
    "purchase_date": "MM/DD/YYYY",
    "issue_noticed_date": "MM/DD/YYYY",
    "dispute_reason": "allowed reason",
    "resolution_requested": "full_refund|partial_refund|reversal_of_charge",
    "partial_refund_amount": 0.0
  },
  "transaction_amount": 0.0,
  "card_type": "card tier name from account data",
  "account_open_date": "MM/DD/YYYY",
  "current_date": "MM/DD/YYYY",
  "prior_dispute_dates": ["MM/DD/YYYY"]
}
```

Omit `partial_refund_amount` unless applicable. `prior_dispute_dates` must contain dates from dispute history; normalize timestamps to calendar dates. The output contains `errors`, eligibility checks, `eligible_for_provisional_credit`, and, when valid, the exact filing `payload`. Review errors instead of filing when `ready` is false.
