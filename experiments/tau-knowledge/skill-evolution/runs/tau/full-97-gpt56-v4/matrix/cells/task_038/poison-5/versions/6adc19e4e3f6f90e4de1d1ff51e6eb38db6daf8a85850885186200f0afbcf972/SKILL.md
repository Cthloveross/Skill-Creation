---
name: credit-card-dispute-and-replacement
version: 1.0.0
description: Safely files one or more credit-card transaction disputes and, when requested, coordinates a replacement card. Use for fraud, duplicate, billing, delivery, description, subscription, or refund disputes that require the internal dispute tool and a provisional-credit determination.
---

# Credit Card Dispute and Replacement

Use this Skill when a customer wants to dispute credit-card transactions, especially when fraud also creates a request to replace the card. Treat every disputed transaction as a separate dispute submission. Do not treat a repeated amount alone as proof of either fraud or a duplicate; obtain or confirm the applicable single reason for each transaction.

## Safety and identity prerequisites

1. Locate the customer and the relevant credit-card account using the normal banking lookup tools.
2. Complete standard identity verification before accessing card details or performing an action. Confirm two of the four identity fields (date of birth, email, phone number, and address) with the customer rather than merely reading them aloud. Retrieve the verified record, get the current timestamp, then call `log_verification` with all fields required by that tool.
3. Confirm that each selected transaction belongs to the verified customer and selected card. Record its transaction ID, amount, merchant, and purchase date.
4. Obtain the card last four digits using the account ID, not a full card number. Unlock `get_card_last_4_digits` and call it with `{"credit_card_account_id": "<account_id>"}`. This is preferable to asking the customer to disclose card information.
5. Do not unlock or call a submission tool while any mandatory item is unknown. Ask a compact follow-up question covering all missing customer-provided fields.

## Required collection for each dispute

For every transaction, collect and validate:

- the transaction ID and purchase date from transaction history;
- the selected card's last four digits;
- the verified customer's full name, user ID, registered phone, email, and address;
- the date the customer noticed the issue, converted to `MM/DD/YYYY`; if they say “today,” use the current-time tool's date;
- whether they contacted the merchant (`true` or `false`);
- exactly one reason code:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- exactly one resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`;
- a positive numeric `partial_refund_amount` only for `partial_refund` (omit it for other resolutions); and
- the card action: `keep_active` or `cancel_and_reissue`.

Use `scripts/build_dispute_payload.py` as a local validation and payload builder. It does not perform bank actions.

### Reason and merchant-contact interpretation

- Fraud means the customer says they did not authorize the charge. Merchant contact is not required for provisional-credit eligibility in that case.
- Use `duplicate_charge` only when the customer identifies it as a duplicate charge, rather than silently reclassifying it as fraud.
- For all non-fraud reasons, obtain whether the customer tried to resolve the issue with the merchant. A “no” does not necessarily block filing, but it makes the dispute ineligible for provisional credit.
- If the customer's narrative could map to multiple reason codes, ask them which of the permitted descriptions best reflects that transaction before filing.

## Determine provisional-credit eligibility

Before submission, unlock and call `get_user_dispute_history_7291` with the verified `user_id`. Count credit-card disputes filed in the 12 months preceding the current date. Use the selected card's account-open date, tier, the transaction amount, merchant-contact answer, and dates to evaluate every dispute individually.

A dispute is eligible only when **all** conditions below hold:

1. The account has been open at least 60 days as of the current date.
2. Its reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`.
3. For `goods_services_not_received`, the purchase is more than 30 days before the current date.
4. The amount is at least $25.00 and no greater than the tier cap.
5. The customer has filed no more than two disputes during the prior 12 months.
6. For a non-fraud qualifying reason, the customer contacted the merchant.

Tier caps are: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000. The packaged helper recognizes the card names in the eligibility policy and reports `undetermined` if essential evidence is missing or the tier is unsupported. Do not convert an undetermined result into `false`; obtain the evidence or escalate according to normal procedures.

Run it as follows (JSON is supplied on standard input and JSON is emitted on standard output):

```sh
python3 scripts/evaluate_provisional_credit.py <<'JSON'
{"account_open_date":"MM/DD/YYYY","as_of_date":"MM/DD/YYYY","purchase_date":"MM/DD/YYYY","amount":"0.00","card_type":"<card type>","reason":"<reason code>","contacted_merchant":true,"prior_disputes_last_12_months":0}
JSON
```

Interpret `decision: "eligible"` as `eligible_for_provisional_credit: true`; interpret `decision: "ineligible"` as `false`. Resolve all reported `missing` fields when the decision is `undetermined`.

## Replacement-card branch

If the customer asks to cancel the card and receive a replacement, use `cancel_and_reissue` for disputes on that card. A dispute card action does not waive the replacement-order prerequisites.

Before ordering a replacement:

1. Verify identity, confirm the relevant account, and confirm the complete shipping address.
2. Record exactly one reason: `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`.
3. Check for outstanding replacement orders by unlocking and calling `get_pending_replacement_orders_5765` with `{"credit_card_account_id":"<account_id>"}`. Do not order if any order is pending or shipped; wait for delivery or cancellation.
4. Confirm eligibility, including the tier's 60-day replacement limit. The limits are two (entry), three (mid), and four (premium and above). If the available records cannot establish the limit, do not guess or order; follow the normal manual-review path.
5. Ask for standard (7–10 business days, free) or expedited (2–3 business days). State the tier-specific expedited fee and obtain explicit consent when a fee applies. Fraud or stolen cards should be offered expedited shipping.
6. Only after all checks pass, unlock `order_replacement_credit_card_7291` and submit the account identifier, reason, confirmed shipping address, shipping speed, fee acknowledgement (when required), and relevant notes.

Tell the customer that ordering a replacement cancels the old card for new purchases and the new card has a different number and CVV. Do not promise an order or replacement until the order tool reports success. Never repeat an operation whose outcome is reported as unknown.

## Submit disputes

For each fully validated transaction, unlock `file_credit_card_transaction_dispute_4829` immediately before use and call it through `call_discoverable_agent_tool`. Its `arguments` must be a JSON string containing this exact schema:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active or cancel_and_reissue",
  "card_last_4_digits": "string",
  "full_name": "string",
  "user_id": "string",
  "phone": "string",
  "email": "string",
  "address": "string",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "one permitted reason code",
  "resolution_requested": "full_refund, partial_refund, or reversal_of_charge",
  "partial_refund_amount": 0,
  "eligible_for_provisional_credit": true
}
```

Omit `partial_refund_amount` unless the requested resolution is `partial_refund`. Submit exactly one call per intended transaction, retain each tool result, and summarize which disputes were successfully filed, their requested resolutions, whether provisional credit was eligible, and any unresolved next steps. If a submission returns an error, do not claim success; correct only the identified missing or invalid data and avoid duplicate submissions.

## Local helper interfaces

- `scripts/evaluate_provisional_credit.py`: Reads an object with `account_open_date`, `as_of_date`, `purchase_date`, `amount`, `card_type`, `reason`, `contacted_merchant`, and `prior_disputes_last_12_months`. It emits `{ok, decision, eligible_for_provisional_credit, checks, missing}`.
- `scripts/build_dispute_payload.py`: Reads `{dispute, provisional_decision}`. `dispute` uses the submission schema above; `provisional_decision` is `eligible` or `ineligible`. It emits `{ok, payload, errors}` and checks enums, dates, four-digit card suffixes, required identity fields, and partial-refund consistency.
