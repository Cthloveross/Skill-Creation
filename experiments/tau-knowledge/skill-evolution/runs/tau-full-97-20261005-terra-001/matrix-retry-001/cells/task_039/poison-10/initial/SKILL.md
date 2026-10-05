---
name: credit-card-dispute-and-replacement
summary: File one or more verified credit-card transaction disputes, determine provisional-credit eligibility, and process a requested replacement card.
description: Use when a verified customer reports credit-card fraud, duplicate billing, merchant/service issues, or billing errors and may want their card replaced. This Skill validates per-transaction dispute payloads, calculates provisional-credit eligibility from the published rules, and gives the required tool workflow for disputes and replacements.
---

# Credit-card dispute and replacement

## Required intake and verification

1. Identify the customer and obtain their credit-card accounts and transaction history using the normal read-only banking tools.
2. Verify identity by confirming **two of four** registered fields: date of birth, email, phone, and address. Retrieve the registered record as needed. After two fields match, obtain the current timestamp and call `log_verification` with all required registered fields.
3. For **each** transaction, confirm the exact transaction record, dispute reason, whether the merchant was contacted, the requested resolution, and when the issue was noticed. A single request involving multiple charges requires one dispute filing per transaction.
4. Map customer language only to these exact reason codes:
   - `unauthorized_fraudulent_charge`
   - `duplicate_charge`
   - `incorrect_amount`
   - `goods_services_not_received`
   - `goods_services_not_as_described`
   - `canceled_subscription_still_charging`
   - `refund_never_processed`
5. Map a requested chargeback/reversal to `reversal_of_charge`. Use `partial_refund` only when the customer supplies a positive partial-refund amount.

Do not infer a transaction ID, a date, merchant-contact status, a requested resolution, or a partial amount. If a required item is missing, ask for it before filing.

## Gather prerequisites for provisional credit

For the selected card account, obtain its open date, card type, last four digits, and the user's dispute history. The documented specialist tools are:

- `get_card_last_4_digits(credit_card_account_id)` for the card's last four digits.
- `get_user_dispute_history_7291(user_id)` for prior dispute dates.

Unlock a documented agent-discoverable tool before calling it through `call_discoverable_agent_tool`. Count disputes filed in the 12 months ending on the current date; no more than two is permitted. Get the current date/time with the normal time tool. Never substitute a last-four value from a different card.

Use `scripts/prepare_dispute_plan.py` to validate inputs and construct exact filing payloads. The script is deterministic and does not call banking tools.

### Script input/output

Run the script with JSON on stdin:

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

It emits `{ "ready_to_file", "errors", "warnings", "payloads", "eligibility" }`. File only when `ready_to_file` is true. Each object in `payloads` is an exact argument object for `file_credit_card_transaction_dispute_4829`; serialize that object as the `arguments` JSON string.

## Provisional-credit decision

The script applies all published criteria independently to each charge:

- account open at least 60 days;
- reason is fraud, duplicate, or goods/services not received (the latter only when purchase was more than 30 days ago);
- amount is at least $25 and no more than the card tier limit;
- no more than two prior disputes in the preceding 12 months; and
- for non-fraud, merchant contact is true.

Card limits are $2,500 entry, $5,000 mid, $10,000 premium, $15,000 elite, and $25,000 invitation. A card type outside the documented tiers is an error: do not guess eligibility. Eligibility only controls the boolean passed to the dispute tool; it does not prevent filing an otherwise complete dispute. Explain that provisional credit is temporary and can be reversed if the investigation is not resolved in the customer's favor.

## File disputes

After validation, unlock `file_credit_card_transaction_dispute_4829` once. For every payload, call `call_discoverable_agent_tool` with:

- `agent_tool_name`: `file_credit_card_transaction_dispute_4829`
- `arguments`: JSON serialization of that single payload.

Use `cancel_and_reissue` for every disputed charge if the customer wants the affected card replaced; otherwise use `keep_active`. Do not claim success until each tool response has succeeded. If a filing fails, preserve successful filings, report the failed transaction, and resolve the indicated error without duplicating successful filings.

## Replacement workflow

A replacement is a separate action from dispute filings. Before ordering:

1. Ensure identity is verified and the selected account is the affected card.
2. Confirm the shipping address, exact replacement reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), shipping speed, and any fee consent required by the card tier.
3. Unlock and call `get_pending_replacement_orders_5765` for the selected credit-card account. Do not submit another order while any returned order is non-final (such as pending or shipped). Also confirm the tier's 60-day replacement limit: entry 2, mid 3, premium-and-above 4. If required evidence for the limit is unavailable, do not state eligibility as confirmed; obtain it or escalate.
4. If eligible, unlock `order_replacement_credit_card_7291`, then call it with the account/card identifier, reason, confirmed `shipping_address`, `shipping_speed` (`standard` or `expedited`), `expedited_fee_acknowledgement`, and useful notes.

For suspected fraud or theft, recommend expedited shipping and remind the customer to review recent transactions. For Gold, Platinum, and Diamond tiers, expedited shipping is complimentary and estimated at 2–3 business days; standard delivery is free and estimated at 7–10 business days. Explain that ordering cancels the old card, creates a new card number and CVV, and leaves the account number unchanged.

If the customer declines or cannot provide a required dispute or replacement detail, clearly state what remains needed and do not make a tool call with invented values.
