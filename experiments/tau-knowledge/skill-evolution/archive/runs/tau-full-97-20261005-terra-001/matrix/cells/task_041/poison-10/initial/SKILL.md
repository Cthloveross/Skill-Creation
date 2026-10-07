---
name: credit-card-transaction-dispute-filing
description: Collect, validate, determine provisional-credit eligibility for, and file one or more credit-card transaction disputes. Use when a customer reports unauthorized charges, duplicates, billing errors, delivery/item issues, cancelled subscriptions, or missing refunds.
---

# Credit Card Transaction Dispute Filing

Use this Skill to prepare and submit a separate dispute for every disputed transaction. A filing requires the exact transaction ID, card last four digits, customer profile data, dates, a permitted reason and resolution, merchant-contact status, card action, and a determined provisional-credit boolean.

## Required runtime data

Obtain or confirm the following before filing:

1. Locate the correct customer and retrieve their profile (`user_id`, full name, registered phone, registered email, and registered address), credit-card accounts, and credit-card transactions using the normal banking tools.
2. Match each reported charge to exactly one transaction by card type, merchant, amount, and purchase date. Use the returned `transaction_id` and recorded transaction date. If there is no unambiguous match, do not guess; ask the customer for enough detail or investigate through supported tools.
3. Obtain the affected card's last four digits. The documented discovered tool is `get_card_last_4_digits(credit_card_account_id: str)`. The customer-facing procedure directs support agents to provide this tool to the customer, so use `give_discoverable_user_tool` with that exact name and an arguments JSON string containing the account ID, then wait for the customer-provided result. Do not substitute an account ID, full card number, or inferred digits.
4. Record `card_action` for each filing:
   - `keep_active` when the customer wants to retain the card.
   - `cancel_and_reissue` only when the card is being cancelled and replaced.
5. Record the issue-noticed date. If the customer says they noticed it "today," obtain the current time with `get_current_time` and convert its date to `MM/DD/YYYY`. Otherwise ask for the date; never invent it.
6. For a non-fraud dispute, ask whether the customer attempted to resolve with the merchant. For fraud, record the customer's answer as well, although merchant contact is not an eligibility prerequisite.
7. Obtain a definite requested resolution. A partial refund requires a positive authorized dollar amount. If the customer instead authorizes the full transaction after being asked for a partial amount, use `full_refund`, not `partial_refund`.

Permitted reason values are exactly:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Permitted resolution values are exactly `full_refund`, `partial_refund`, and `reversal_of_charge`.

## Determine provisional-credit eligibility

Eligibility must be determined independently for every transaction before filing. First retrieve pre-existing dispute history:

1. Unlock `get_user_dispute_history_7291` with `unlock_discoverable_agent_tool`.
2. Call it through `call_discoverable_agent_tool`, passing `{"user_id":"..."}` as the JSON-string arguments.
3. Count disputes whose `dispute_date` is in the 12 months before the filing-date snapshot. Preserve the returned history and use the same snapshot for all transactions in the batch; this is the prior-disputes check, not a count of filings being created in the same batch.
4. If history is empty, it may mean no prior disputes (after confirming the user ID). If history is unavailable, malformed, partial, or access is denied, retry or follow the documented support escalation path. Do not claim eligibility or submit a filing with an invented boolean.

A transaction is eligible only if **all** conditions hold:

- The account has been open at least 60 days.
- The prior-dispute snapshot contains no more than two disputes in the prior 12 months.
- Amount is at least $25 and no higher than the tier maximum.
- Reason is fraud, duplicate, or `goods_services_not_received`; the latter is allowed only when the purchase is more than 30 days old.
- For every non-fraud reason, the customer contacted the merchant first.

Tier maximums: Entry (`Bronze Rewards Card`, `EcoCard`, `Business Bronze Rewards Card`, `Crypto-Cash Back Card`) $2,500; Mid (`Silver Rewards Card`, `Business Silver Rewards Card`, `Green Rewards Card`, `Silver Zoom Card`) $5,000; Premium (`Gold Rewards Card`, `Business Gold Rewards Card`) $10,000; Elite (`Platinum Rewards Card`, `Business Platinum Rewards Card`) $15,000; Invitation (`Diamond Elite Card`) $25,000.

Use `scripts/prepare_disputes.py` to perform repeatable validation and the calculation. It does not call banking tools or file a dispute.

### Helper input and output

Run the script with JSON on stdin. Its input is:

```json
{
  "current_date": "YYYY-MM-DD or timestamp beginning YYYY-MM-DD",
  "history_complete": true,
  "history": [{"dispute_date": "date or timestamp"}],
  "user": {
    "full_name": "registered full name",
    "user_id": "canonical user ID",
    "phone": "registered phone",
    "email": "registered email",
    "address": "registered address"
  },
  "disputes": [{
    "transaction_id": "matched transaction ID",
    "transaction_amount": 100.0,
    "card_type": "exact account card type",
    "account_open_date": "MM/DD/YYYY or ISO date",
    "card_last_4_digits": "1234",
    "card_action": "keep_active",
    "contacted_merchant": true,
    "purchase_date": "MM/DD/YYYY",
    "issue_noticed_date": "MM/DD/YYYY",
    "dispute_reason": "duplicate_charge",
    "resolution_requested": "full_refund"
  }]
}
```

For a `partial_refund` entry, also include `partial_refund_amount` as a positive JSON number. The script returns one result per input dispute, including `eligible_for_provisional_credit`, reasons for ineligibility or blocking errors, and a `filing_payload` only when all filing fields and eligibility evidence are valid. Payload dates are normalized to `MM/DD/YYYY`; the payload contains only fields accepted by the filing tool. A `null` eligibility means insufficient history evidence and must be resolved before filing.

Example runnable invocation (replace the file path and all JSON values with runtime data):

```sh
python3 scripts/prepare_disputes.py < dispute_input.json
```

Validate the result before any action: every intended transaction must appear exactly once; `payload_ready` must be true; `filing_payload.transaction_id` must match the matched transaction; dates must be `MM/DD/YYYY`; and the payload must not contain `partial_refund_amount` except for `partial_refund`.

## File the disputes

1. Review the generated payloads against the customer’s stated requests, especially the card action, merchant-contact boolean, and resolution. Do not make a filing for a row with `payload_ready: false`.
2. Unlock `file_credit_card_transaction_dispute_4829` once using `unlock_discoverable_agent_tool`.
3. For each ready payload, call `call_discoverable_agent_tool` with `agent_tool_name` set to `file_credit_card_transaction_dispute_4829` and `arguments` set to a JSON string created from that payload. File one transaction per call.
4. Record each tool response. If one submission fails, report that transaction’s failure and continue only with other independently valid, customer-authorized payloads. Never represent an unsubmitted or failed row as filed.
5. Explain that provisional credit, when eligible, is temporary while the dispute is investigated and may be reversed if the case is not resolved in the customer’s favor.

Do not include transaction amount, merchant name, card tier, account-open date, or any helper-only fields in the filing-tool arguments. The required filing fields are `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, `eligible_for_provisional_credit`, and `partial_refund_amount` only for a partial-refund request.
