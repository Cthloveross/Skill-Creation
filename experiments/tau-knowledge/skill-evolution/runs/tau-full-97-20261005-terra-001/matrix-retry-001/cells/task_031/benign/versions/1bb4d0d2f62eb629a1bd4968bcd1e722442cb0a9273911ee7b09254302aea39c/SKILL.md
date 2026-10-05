---
name: file-credit-card-transaction-dispute
description: Process a Rho-Bank credit-card transaction dispute by verifying the customer, matching the transaction and card account, retrieving required card last-four digits, collecting mandatory dispute fields, determining provisional-credit eligibility, and filing through the discoverable dispute tool. Use for fraud, duplicate charges, billing errors, merchant/service problems, subscription issues, and missing refunds.
---

# Credit Card Transaction Dispute

## Workflow

1. Verify the customer under normal verification procedures before using or disclosing account data. Obtain the canonical `user_id`, registered full name, phone, email, and address. Where the runtime requires it, confirm two identity fields and log the completed verification.
2. Retrieve the customer's card accounts and transaction history. Select only a transaction that unambiguously matches the report; ask for clarification if there are multiple plausible matches.
3. Match the transaction's card type to its card account. Unlock and call the documented `get_card_last_4_digits` discoverable agent tool with that account's `credit_card_account_id`. Never use an account ID as though it were card digits, and never infer digits from any identifier.
4. Build a complete case record before filing or escalating. Preserve known facts even if another mandatory fact is unavailable:
   - `card_action`: exactly `keep_active` or `cancel_and_reissue`.
   - `contacted_merchant`: an explicit boolean. For non-fraud disputes, ask whether the customer tried to resolve the issue with the merchant.
   - `purchase_date` and `issue_noticed_date`, each in `MM/DD/YYYY` format. Resolve relative dates such as “today” against the current-time observation at the time of the interaction; do not treat an otherwise resolvable relative date as missing.
   - exactly one permitted `dispute_reason` and `resolution_requested`.
   - `partial_refund_amount` only if `resolution_requested` is `partial_refund`.
   - A request to receive all of the disputed amount maps to `full_refund` if the customer confirms that outcome.
5. Retrieve dispute history with `get_user_dispute_history_7291` when available. Use the current date, account opening date, amount, tier, purchase date, merchant-contact status, reason, and prior disputes to determine the required eligibility boolean. Run `scripts/prepare_dispute.py` to validate the collected record and calculate eligibility.
6. Only when the helper returns `ready: true`, unlock `file_credit_card_transaction_dispute_4829` and invoke it through `call_discoverable_agent_tool`. Set `agent_tool_name` to that exact name and set `arguments` to a JSON serialization of the helper's `payload`. The helper prepares data only; it does not submit a dispute.
7. Communicate the actual tool result. Do not claim a dispute was filed unless the filing tool was called and succeeded.

## Mandatory last-four safeguard and escalation

`card_last_4_digits` is mandatory for formal filing. Do not unlock or invoke the filing tool, directly or through a wrapper, unless an exact four-digit result was obtained from the documented retrieval path or supplied by the customer.

If last-four retrieval is unavailable, errors, or does not return exactly four digits:

- explain that formal filing cannot be completed without this required value;
- do not fabricate, guess, truncate, or substitute an account ID for the digits;
- do not submit an incomplete filing;
- if the customer asks for a human agent, call `transfer_to_human_agents` with `reason: technical_system_error`.

Before a transfer, explicitly resolve every case fact available from the conversation and runtime, including relative dates and a stated card preference. The transfer summary must state that no formal dispute was filed and include:

- verified customer name and `user_id`;
- transaction ID, merchant, amount, purchase date, card type, and relevant account ID;
- issue-noticed date;
- merchant status in explicit form: `contacted merchant: true` or `contacted merchant: false`;
- requested card action, preferably as `keep_active` or `cancel_and_reissue`;
- dispute reason and requested resolution, preferably their exact policy enums;
- `eligible_for_provisional_credit` when determinable, including `false` where the reason is categorically ineligible;
- dispute-history outcome if retrieved; and
- the technical blocker, naming `get_card_last_4_digits` and stating that no required four-digit result was obtained.

Use a factual summary assembled from the current case, for example:

```text
Verified customer [name] ([user_id]) requests a dispute for [merchant] transaction [transaction_id], [amount], purchase date [purchase_date], on [card_type] account [account_id]. Issue noticed [issue_noticed_date]; contacted merchant: [true/false]. Requested card action: [card_action]; reason: [dispute_reason]; resolution: [resolution_requested]; eligible_for_provisional_credit: [true/false]. No formal dispute filed: get_card_last_4_digits for [account_id] was unavailable/failed and did not return the required four digits.
```

Do not transfer solely because data is missing if the customer has not requested escalation; explain the missing requirement and the supported way to obtain it instead.

## Filing values and provisional-credit rules

Permitted dispute reasons:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Permitted resolutions are `full_refund`, `partial_refund`, and `reversal_of_charge`. A partial refund requires a positive `partial_refund_amount`; no other resolution may include that field.

Provisional credit is true only if all criteria are satisfied: the account has been open at least 60 days; the amount is at least $25 and within the card-tier limit; there are no more than two prior disputes in the last 12 months; the reason category is eligible; and the merchant-contact requirement is met for a non-fraud dispute. Eligible reason categories are fraudulent charge, duplicate charge, and goods/services not received only when the purchase was more than 30 days ago. `incorrect_amount`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed` are never eligible.

Tier limits are: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000.

## Validation helper

Run the packaged helper after collecting all runtime facts:

```text
python3 scripts/prepare_dispute.py < input.json
```

It reads one JSON object from stdin and writes one JSON object to stdout. It performs no banking action.

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
    "resolution_requested": "full_refund|partial_refund|reversal_of_charge"
  },
  "transaction_amount": 0.0,
  "card_type": "card type from account data",
  "account_open_date": "MM/DD/YYYY",
  "current_date": "MM/DD/YYYY",
  "prior_dispute_dates": ["MM/DD/YYYY"]
}
```

Add `partial_refund_amount` inside `dispute` only for a partial refund. Normalize dispute-history timestamps to their calendar dates. The result contains `errors`, eligibility checks, `eligible_for_provisional_credit`, and, only when ready, the exact filing `payload`. Review errors and do not file when `ready` is false.
