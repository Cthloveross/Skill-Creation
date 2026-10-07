---
name: credit-card-transaction-dispute
version: 1.0.0
description: File a credit-card transaction dispute when a customer identifies a posted card transaction. Use this Skill to verify the customer, collect and validate the required dispute facts, determine provisional-credit eligibility, and invoke the required discoverable banking tools.
---

# Credit-Card Transaction Dispute

## Purpose

Use this procedure to submit a formal dispute through
`file_credit_card_transaction_dispute_4829`. Do not submit a dispute until the
customer identity, transaction, required fields, and the provisional-credit
boolean have been determined.

A dispute can use only these reason codes:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Permitted requested resolutions are `full_refund`, `partial_refund`, and
`reversal_of_charge`. A partial-refund request also requires a positive dollar
amount as `partial_refund_amount`.

## Procedure

### 1. Identify and verify the customer

1. Locate the customer using a supplied full name or registered email with the
   appropriate normal banking lookup tool.
2. Obtain confirmation of at least two of the four identity fields: date of
   birth, registered email, registered phone number, and registered address.
   Do not count a database lookup itself as customer confirmation.
3. After two fields match the profile, get the current time and call
   `log_verification` with the complete profile values returned by the bank,
   the customer name and user ID, and that timestamp.
4. If identity cannot be verified, do not disclose account details or file the
   dispute. Ask for the needed verification information or transfer when the
   normal verification flow cannot proceed.

### 2. Locate the exact transaction and card

1. Retrieve the verified user's card transactions. Match the customer’s
   merchant, amount, and purchase date to a completed transaction. If more
   than one transaction might match, ask the customer to distinguish it; never
   guess a transaction ID.
2. Retrieve the user's credit-card accounts and select the account whose card
   type matches the chosen transaction's card type.
3. Obtain the disputed card's last four digits without asking for the full card
   number. The documented mechanism is the customer-accessible
   `get_card_last_4_digits(credit_card_account_id: str)` tool. Pass it with
   `give_discoverable_user_tool`, using the selected account ID in the JSON
   arguments, then have the customer execute it and use the returned last four
   digits. Do not substitute another card's digits.
4. Determine `card_action` from the customer's request:
   - `keep_active` when the customer will continue using the card.
   - `cancel_and_reissue` only when the card is being cancelled and replaced,
     including when replacement was separately ordered.

For an unauthorized-charge report, explicitly ask whether the customer wants
the card replaced rather than inferring a cancellation.

### 3. Gather the dispute facts

Collect or confirm all of the following before submission:

- transaction ID and card last four digits;
- registered full name, user ID, phone, email, and address from the verified
  profile;
- whether the customer contacted the merchant (`contacted_merchant`);
- purchase date and issue-noticed date, both in `MM/DD/YYYY`;
- exactly one permitted reason code;
- requested resolution and, for a partial refund, the dollar amount; and
- the customer's card-action preference.

Translate relative dates such as “today” using the current-time tool and
confirm the resulting `MM/DD/YYYY` date if there is ambiguity. For a hotel,
product, or service that was materially different from what was promised, use
`goods_services_not_as_described`; do not classify it as non-receipt merely
because the customer wants a refund. Merchant outreach is mandatory for
provisional credit on every non-fraud reason, though a dispute may still be
filed when it makes the customer ineligible for provisional credit.

### 4. Determine provisional-credit eligibility

Retrieve the dispute history before declaring a customer eligible:

1. Unlock `get_user_dispute_history_7291` with
   `unlock_discoverable_agent_tool`.
2. Call it through `call_discoverable_agent_tool` with
   `{"user_id": "..."}`.
3. Count disputes whose `dispute_date` falls in the 12 months ending on the
   current date. The customer meets this condition only when the count is at
   most two.

Use `scripts/assess_provisional_credit.py` to make the deterministic portion of
the decision. Its stdin is one JSON object with this schema:

```json
{
  "current_date": "MM/DD/YYYY",
  "account_open_date": "MM/DD/YYYY",
  "card_type": "card tier name",
  "transaction_amount": "numeric amount or currency-formatted string",
  "purchase_date": "MM/DD/YYYY",
  "dispute_reason": "one permitted reason code",
  "contacted_merchant": true,
  "prior_dispute_dates": ["MM/DD/YYYY or ISO date", "..."]
}
```

Run it by piping that JSON to `python scripts/assess_provisional_credit.py`.
It emits JSON with `eligible` (`true`, `false`, or `null`),
`disqualifying_reasons`, `missing_fields`, and `validation_errors`.

Eligibility is true only when all of these conditions hold:

- the selected card account has been open at least 60 days;
- the reason is fraud, duplicate charge, or goods/services not received;
- for goods/services not received, the purchase was more than 30 days ago;
- the amount is at least $25 and does not exceed the tier limit;
- no more than two prior disputes were filed in the last 12 months; and
- for a non-fraud reason, the customer contacted the merchant.

Tier limits are $2,500 for Entry (Bronze Rewards, EcoCard, Business Bronze
Rewards, Crypto-Cash Back), $5,000 for Mid (Silver Rewards, Business Silver
Rewards, Green Rewards, Silver Zoom), $10,000 for Premium (Gold Rewards and
Business Gold Rewards), $15,000 for Elite (Platinum Rewards and Business
Platinum Rewards), and $25,000 for Diamond Elite.

Pass `eligible_for_provisional_credit: false` when any known condition makes
eligibility impossible. If no known disqualifier exists but required eligibility
data is unavailable or malformed, do not guess `true`; resolve the missing data
or explain that filing cannot yet proceed.

### 5. Validate and submit

Before the irreversible filing call, verify:

- all dates are valid `MM/DD/YYYY` values;
- the transaction, selected account, card digits, and profile all belong to
  the verified customer;
- `card_action`, reason, and resolution exactly match the permitted values;
- `contacted_merchant` and provisional eligibility are JSON booleans, not
  strings;
- `partial_refund_amount` is included only for `partial_refund`; and
- the full-refund amount is not represented as a partial-refund request.

Unlock `file_credit_card_transaction_dispute_4829`, then call it through
`call_discoverable_agent_tool`. Send a JSON string with exactly the required
fields:

```text
transaction_id, card_action, card_last_4_digits, full_name, user_id, phone,
email, address, contacted_merchant, purchase_date, issue_noticed_date,
dispute_reason, resolution_requested, eligible_for_provisional_credit
```

Include `partial_refund_amount` only when `resolution_requested` is
`partial_refund`. Preserve the tool response and tell the customer the dispute
was filed only after a successful result. If an unlock or call fails, do not
claim submission; report the failure and use the normal technical-escalation
path when appropriate.
