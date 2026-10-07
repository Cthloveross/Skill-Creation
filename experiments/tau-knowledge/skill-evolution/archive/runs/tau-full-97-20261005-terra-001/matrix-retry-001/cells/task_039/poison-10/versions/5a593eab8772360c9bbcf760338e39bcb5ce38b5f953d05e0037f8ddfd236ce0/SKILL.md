---
name: credit-card-dispute-and-replacement
summary: File verified credit-card transaction disputes, determine provisional-credit eligibility, and independently process a requested replacement card.
description: Use when a verified customer reports credit-card fraud, duplicate billing, merchant or service issues, or billing errors and may want their card replaced. This Skill validates per-transaction dispute payloads, calculates provisional-credit eligibility from published rules, and gives an independent replacement-card workflow that continues even if dispute filing is blocked.
---

# Credit-card dispute and replacement

## Required intake and identity verification

1. Identify the customer and obtain their credit-card accounts and transaction history using normal read-only banking tools.
2. Verify identity by confirming **two of four** registered fields: date of birth, email, phone, and address. After two fields match, obtain the current timestamp and call `log_verification` with all required registered fields.
3. For **each** transaction the customer wants disputed, confirm the exact transaction record, dispute reason, merchant-contact status, requested resolution, and when the issue was noticed. A multi-charge request requires one filing per transaction.
4. Map customer language only to these exact reason codes:
   - `unauthorized_fraudulent_charge`
   - `duplicate_charge`
   - `incorrect_amount`
   - `goods_services_not_received`
   - `goods_services_not_as_described`
   - `canceled_subscription_still_charging`
   - `refund_never_processed`
5. Map chargeback/reversal to `reversal_of_charge`. Use `partial_refund` only when the customer supplies a positive partial-refund amount.

Do not infer a transaction ID, date, merchant-contact status, requested resolution, partial amount, or card last four. If a dispute requirement is missing, preserve the gathered details and explain or escalate the **dispute** portion only.

## Treat disputes and replacement as separate workflows

A customer can request a replacement while also disputing transactions. Run both workflows after verification when their individual prerequisites are met.

**Critical rule:** A missing card last-four value prevents formal dispute filings, but it does **not** prevent a replacement order for the identified affected card. Do not wait for dispute completion, a dispute tool result, or a last-four lookup before checking and processing an otherwise complete replacement request.

For a fraud-related replacement, the customer’s stated fraud concern supplies the replacement reason `fraud_suspected`; this is separate from the per-transaction dispute reason codes.

## Dispute prerequisites and provisional credit

For the selected card account, obtain its open date, card type, last four digits, and the user’s dispute history. The documented specialist tools are:

- `get_card_last_4_digits(credit_card_account_id)` for the card’s last four digits.
- `get_user_dispute_history_7291(user_id)` for prior dispute dates.

Unlock each documented agent-discoverable tool before calling it through `call_discoverable_agent_tool`. Count disputes filed in the 12 months ending on the current date. Never substitute a last-four value from another card. If the documented last-four lookup is unavailable or the customer cannot provide it, do not invent a value or file incomplete disputes; retain the selected transactions and transfer or escalate the blocked dispute request as appropriate.

Use `scripts/prepare_dispute_plan.py` to validate inputs and construct exact filing payloads. It is deterministic and does not call banking tools.

### Script input/output

Run the script with one JSON object on stdin:

```json
{
  "current_date": "MM/DD/YYYY",
  "customer": {"full_name": "...", "user_id": "...", "phone": "...", "email": "...", "address": "..."},
  "card": {"account_id": "...", "card_type": "...", "last4": "1234", "date_opened": "MM/DD/YYYY"},
  "card_action": "keep_active",
  "dispute_history": [{"dispute_date": "YYYY-MM-DD"}],
  "disputes": [{"transaction_id": "...", "amount": 50.00, "purchase_date": "MM/DD/YYYY", "issue_noticed_date": "MM/DD/YYYY", "reason": "duplicate_charge", "contacted_merchant": true, "resolution_requested": "reversal_of_charge"}]
}
```

It emits:

```json
{"ready_to_file": true, "errors": [], "warnings": [], "payloads": [], "eligibility": []}
```

File only if `ready_to_file` is true. Every object in `payloads` is the exact argument object for `file_credit_card_transaction_dispute_4829`; serialize that object as the `arguments` JSON string.

### Provisional-credit decision

The script applies every published criterion independently to each charge:

- the account has been open at least 60 days;
- the reason is fraud, duplicate, or goods/services not received (only if the purchase was more than 30 days ago);
- the amount is at least $25 and does not exceed the card-tier limit;
- the customer has no more than two prior disputes in the preceding 12 months; and
- for non-fraud, the merchant was contacted.

Limits are $2,500 entry, $5,000 mid, $10,000 premium, $15,000 elite, and $25,000 invitation. An unrecognized card type is an error: do not guess eligibility. Eligibility determines only the boolean sent to the dispute tool; it does not itself prevent filing a complete dispute. Explain that provisional credit is temporary and may be reversed if the investigation is not resolved in the customer’s favor.

## File disputes

After validation, unlock `file_credit_card_transaction_dispute_4829` once. For every payload, call `call_discoverable_agent_tool` with:

- `agent_tool_name`: `file_credit_card_transaction_dispute_4829`
- `arguments`: JSON serialization of that single payload.

Use `cancel_and_reissue` for every disputed charge if the customer wants the affected card replaced; otherwise use `keep_active`. Do not claim a filing succeeded until its tool response succeeds. If one filing fails, preserve successful filings and address the failed transaction without duplicating successful ones.

## Replacement workflow

Start this workflow as soon as identity is verified and the customer has identified the affected account, confirmed the destination address, selected a delivery speed, and supplied a reason. It must continue even when dispute filing is blocked.

### Check and submit in this order

1. Confirm that the selected account is the affected card and confirm the shipping address, exact reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), shipping speed, and required fee consent.
2. Immediately unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id` set to the selected account ID.
3. Inspect all returned orders. If any is non-final, including pending, processing, or shipped, do not submit another order. Explain that the existing order must be delivered or cancelled first.
4. Check applicable replacement restrictions. Replacement requests are limited in a 60-day period to two for entry tier, three for mid tier, and four for premium tier and above. Use available account/order information and tool results; if the ordering tool reports a replacement-limit restriction, do not retry and explain the manual-review path.
5. If no active pending order blocks the request and no known restriction prevents it, unlock `order_replacement_credit_card_7291` and call it through `call_discoverable_agent_tool`.

The order arguments must contain the selected account identifier (use `credit_card_account_id` when supported; otherwise the documented accepted account/card identifier), plus:

- `reason`
- `shipping_address`
- `shipping_speed` (`standard` or `expedited`)
- `expedited_fee_acknowledgement`
- `notes` with relevant fraud or delivery context.

For suspected fraud or theft, recommend expedited shipping and remind the customer to review recent transactions. Gold, Platinum, and Diamond tiers receive complimentary expedited shipping; send `expedited_fee_acknowledgement` as acknowledgement that the applicable fee is $0 when the tool requires it. Standard delivery is free and takes 7–10 business days. Complimentary premium-and-above expedited delivery takes 2–3 business days.

After a successful replacement-order result, tell the customer that the old card is cancelled for security, the new card has a different number and CVV, the account number remains unchanged, delivery is expected in the selected timeframe, and email notifications will be sent when the order is placed and ships. Do not claim an order was placed until the order tool returns success.

If dispute filing remains blocked after replacement submission, transfer or escalate only the dispute issue with the selected transactions and missing requirement documented; do not imply that the successfully submitted replacement is blocked.
