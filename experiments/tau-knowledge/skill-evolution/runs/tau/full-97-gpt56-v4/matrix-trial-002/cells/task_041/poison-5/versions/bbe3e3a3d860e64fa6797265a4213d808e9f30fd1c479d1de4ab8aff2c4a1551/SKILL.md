---
name: credit-card-transaction-dispute
version: 1.0.0
description: File one or more credit-card transaction disputes after verifying the customer, matching each claimed charge to account records, retrieving card last-four values through the customer-facing discovered tool, checking prior disputes, and determining provisional-credit eligibility.
---

# Credit Card Transaction Disputes

Use this Skill when a customer wants to formally dispute one or more posted credit-card transactions, including fraud, duplicate charges, billing errors, delivery problems, subscription charges, and missing refunds. Process every transaction independently: a single card can have multiple disputes with different reasons and eligibility outcomes.

## Required information and permitted values

Each submission needs these values:

- `transaction_id`: verify it against the customer's transaction history.
- `card_action`: exactly `keep_active` or `cancel_and_reissue`.
- `card_last_4_digits`: retrieve it for the matching card account; never infer it from the account ID or transaction record.
- `full_name`, `user_id`, registered `phone`, registered `email`, and registered `address`.
- `contacted_merchant`: a Boolean. It is required for every reason; for eligibility it must be true for non-fraud claims.
- `purchase_date` and `issue_noticed_date`, both formatted `MM/DD/YYYY`.
- `dispute_reason`, exactly one of:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- `resolution_requested`, exactly `full_refund`, `partial_refund`, or `reversal_of_charge`.
- `partial_refund_amount`, a number, only when `resolution_requested` is `partial_refund`.
- `eligible_for_provisional_credit`, a Boolean determined by the rules below, not by customer preference.

Translate ordinary customer descriptions to the exact reason codes. In particular, an unrecognized charge is `unauthorized_fraudulent_charge`; a confirmed repeated purchase is `duplicate_charge`; undelivered goods are `goods_services_not_received`; a wrong bill is `incorrect_amount`; a materially different item is `goods_services_not_as_described`; continued billing after cancellation is `canceled_subscription_still_charging`; and an absent promised credit is `refund_never_processed`.

## End-to-end procedure

1. **Identify and verify the customer.** Locate the canonical user record using a customer-supplied identifying value. Confirm any two of date of birth, registered email, phone number, and address with the customer; do not treat a database lookup as confirmation. Once two fields are confirmed, get the current time and call `log_verification` with all fields from the canonical record and that timestamp. Use the canonical name, user ID, email, phone number, and address in filings.

2. **Collect and verify each disputed charge.** Get the customer's credit-card accounts and transaction history. Match every claimed merchant, amount, purchase date, and card to one unique posted transaction. Resolve ambiguity with the customer. Do not file against a transaction ID that is missing, mismatched, or already known to have an existing dispute.

3. **Obtain card last four digits.** The last-four value is mandatory. For every relevant account, provide the customer the discovered tool using `give_discoverable_user_tool` with:
   - `discoverable_tool_name`: `get_card_last_4_digits`
   - `arguments`: a JSON string containing that account's `credit_card_account_id`.

   Tell the customer to run the exact provided tool and wait for its result. Map each returned value to the corresponding account. Do not use a full card number, request a full card number, or guess missing digits. If the customer cannot obtain a value, leave that transaction unfiled until it is available.

4. **Gather customer choices.** For every transaction, ask when the issue was noticed, whether the merchant was contacted, and the desired resolution. Ask whether the card should remain active or be cancelled and replaced; use the answer for `card_action`. For a stated "today," get the current date and format it as `MM/DD/YYYY`. Fraud claims may use `contacted_merchant: false`; non-fraud claims should record the customer's actual merchant-contact answer.

5. **Check dispute history before determining eligibility.** Unlock `get_user_dispute_history_7291` with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` using the canonical `user_id` in the JSON-string arguments. Count disputes whose `dispute_date` falls in the 12 months before the filing date. Also inspect history for the same `transaction_id` so it is not filed twice. If history cannot be retrieved, do not claim the customer is eligible for provisional credit or submit a guessed result.

6. **Determine provisional-credit eligibility per transaction.** All conditions must be true:
   - The matching card account has been open at least 60 days as of the filing date.
   - The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`. For goods/services not received, purchase must be more than 30 days before the filing date.
   - Transaction amount is at least $25.00 and no higher than the tier maximum: $2,500 for Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, or Crypto-Cash Back Card; $5,000 for Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, or Silver Zoom Card; $10,000 for Gold Rewards Card or Business Gold Rewards Card; $15,000 for Platinum Rewards Card or Business Platinum Rewards Card; $25,000 for Diamond Elite Card.
   - The customer has filed no more than two disputes in the prior 12 months.
   - For every non-fraud claim, the customer contacted the merchant.

   Reasons not listed in the second bullet are ineligible. Use `scripts/dispute_helper.py` to make this repeated calculation and to validate payload shapes. Its input/output schema is documented below.

7. **Validate and submit.** For every complete, non-duplicate transaction, run payload validation locally. Unlock `file_credit_card_transaction_dispute_4829` before its first submission. Then call it through `call_discoverable_agent_tool` with `agent_tool_name` set exactly to `file_credit_card_transaction_dispute_4829` and `arguments` set to a JSON string for exactly one complete filing. Include `partial_refund_amount` only for a partial refund. Submit one call per transaction, recording transaction ID and tool result as each call succeeds.

8. **Handle outcomes safely.** Do not resubmit a transaction after a successful filing. If a filing reports an unknown/indeterminate state, do not retry it, because it may already have created a dispute. Preserve the response and arrange follow-up according to normal support process. Clearly tell the customer which disputes were filed, which could not be filed due to missing required information or verification, and that provisional credit is temporary while the investigation proceeds.

## Helper script

`scripts/dispute_helper.py` reads one JSON object from standard input and writes one JSON object to standard output. It never contacts bank systems and does not file disputes.

Invoke it against a JSON request file with:

```text
python scripts/dispute_helper.py < request.json
```

### `mode: "eligibility"`

Input fields: `current_date`, `account_open_date`, `card_type`, `transaction_amount`, `purchase_date`, `dispute_reason`, `contacted_merchant`, and `disputes_past_12_months`. Dates accept `MM/DD/YYYY` or ISO date input. Output contains `eligible_for_provisional_credit`, `reasons`, `account_age_days`, `purchase_age_days`, and `maximum_amount` when the tier is recognized. An empty `reasons` array means eligible.

### `mode: "validate_payload"`

Input field: `payload`, containing one prospective filing. Output contains `valid` and `errors`. This checks required fields, dates, exact code values, Boolean types, and the conditional partial-refund field. It validates format and completeness only; always perform the eligibility calculation separately.

A nonzero script exit or an output `error` means the supplied request is malformed. Correct the data rather than treating it as a negative eligibility decision.
