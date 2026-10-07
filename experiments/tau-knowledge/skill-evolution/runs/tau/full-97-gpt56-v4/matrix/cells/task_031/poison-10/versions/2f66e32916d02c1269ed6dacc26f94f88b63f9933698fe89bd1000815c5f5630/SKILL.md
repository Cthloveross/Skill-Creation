---
name: file-credit-card-transaction-dispute
description: File a formal Rho-Bank credit-card transaction dispute after identifying the customer and transaction, retrieving the card last four digits when necessary, evaluating provisional-credit eligibility, and validating the required discoverable-tool payload. Use for unauthorized charges, duplicate charges, billing errors, merchant/service problems, cancellations still charging, and missing refunds.
---

# File a Credit Card Transaction Dispute

Use this Skill when a customer asks to formally dispute a credit-card transaction. A dispute is a consequential action: do not submit until the transaction and every required field are supported by the customer or authoritative account data.

## Required dispute payload

The final `file_credit_card_transaction_dispute_4829` request requires:

- `transaction_id`
- `card_action`: `keep_active` or `cancel_and_reissue`
- `card_last_4_digits` (exactly four digits)
- `full_name`, `user_id`, `phone`, `email`, `address`
- `contacted_merchant` (boolean)
- `purchase_date` and `issue_noticed_date` in `MM/DD/YYYY`
- `dispute_reason`, one of:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`
- `partial_refund_amount` only for `partial_refund`, as a positive dollar number
- `eligible_for_provisional_credit` (boolean)

## Workflow

1. **Identify and verify the customer.** Locate the user with a supplied name or registered email and obtain canonical profile details using the normal banking lookup tools. Before acting on the account, have the customer confirm two of the profile identity fields (date of birth, registered email, phone, or address). After two match, get the current time and call `log_verification` with the complete profile fields and timestamp. If identity cannot be verified, do not disclose account data or file the dispute.

2. **Find the exact transaction and card account.** Retrieve the customer's transactions and accounts. Match merchant, amount, date, and card type to the customer's description. If more than one plausible transaction remains, ask the customer to distinguish it. Use the matched transaction's ID and transaction date; do not manufacture either. Select the account with the matched card type.

3. **Get the card last four digits.** Do not block on the customer possessing the card if the matching account ID is known. Unlock `get_card_last_4_digits` and call it through `call_discoverable_agent_tool` with the credit-card account ID. Use its returned four digits. If the account cannot be matched or the lookup fails, ask for the needed identifying card information and do not submit without four digits.

4. **Collect and normalize dispute details.** Ask only for missing details.
   - Record whether the customer attempted merchant resolution. For fraud, merchant contact is not required; for all other reasons it affects provisional-credit eligibility.
   - Obtain the date the customer noticed the problem. If they say “today,” call `get_current_time` and convert that calendar date to `MM/DD/YYYY`; do not use a date from a previous interaction.
   - Map the facts to the exact reason enum. For example, a delivered hotel room, item, or service materially different from the booked/advertised description is `goods_services_not_as_described`, not `goods_services_not_received`.
   - Map an unambiguous request to the resolution enum. A request to receive all of the disputed transaction back is `full_refund`. Ask a clarifying question if the requested resolution is ambiguous. For partial refund, obtain the dollar amount.
   - Use `keep_active` when the customer only wants to dispute the charge and wants to keep using the existing card. Use `cancel_and_reissue` only when the card is being cancelled and replaced, including when a replacement has already been ordered. Do not cancel a card merely because a normal merchant dispute is filed.

5. **Determine provisional-credit eligibility.** Unlock and call `get_user_dispute_history_7291` with the canonical user ID. Count disputes filed in the 12 months preceding the evaluation date, using dispute dates. Obtain the account-open date, matched transaction amount, card type, and purchase date from account/transaction data. Use `scripts/evaluate_provisional_credit.py` to apply all conditions. A missing required eligibility fact means eligibility is not established; resolve it before filing where possible, and do not claim provisional credit based on an assumption.

   Eligibility requires **all** of the following:
   - the account has been open at least 60 days;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` where the purchase is more than 30 days old;
   - amount is at least $25 and does not exceed the tier limit;
   - no more than two disputes were filed in the prior 12 months;
   - for non-fraud reasons, the customer contacted the merchant.

   Tier maximums: Entry $2,500 (Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card); Mid $5,000 (Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card); Premium $10,000 (Gold Rewards Card, Business Gold Rewards Card); Elite $15,000 (Platinum Rewards Card, Business Platinum Rewards Card); Invitation $25,000 (Diamond Elite Card). Reasons other than the listed eligible categories are ineligible.

6. **Validate, submit, and report.** Construct the tool JSON from live evidence and run `scripts/validate_dispute_payload.py`. Do not submit if `valid` is false. Unlock `file_credit_card_transaction_dispute_4829`, then call it with the JSON payload string through `call_discoverable_agent_tool`. Report the actual tool result to the customer. Do not represent a dispute as filed if the tool returns an error or no confirmation.

## Helper scripts

Both scripts read one JSON object from standard input and emit one JSON object on standard output. They are decision/validation helpers only; their output never submits a bank action.

### Provisional-credit evaluator

Run `scripts/evaluate_provisional_credit.py` with:

```json
{
  "account_open_date": "MM/DD/YYYY",
  "purchase_date": "MM/DD/YYYY",
  "evaluation_date": "MM/DD/YYYY",
  "dispute_reason": "one permitted reason",
  "transaction_amount": 100.00,
  "card_type": "card type from account",
  "prior_disputes_past_12_months": 0,
  "contacted_merchant": true
}
```

It returns `eligible_for_provisional_credit`, `determinate`, per-condition results, and any validation errors. Use the boolean only when `determinate` is true.

### Payload validator

Run `scripts/validate_dispute_payload.py` with the exact object intended for the filing tool. It returns `valid` and a list of `errors`. It checks enum values, date and last-four formats, required contact fields, conditional partial-refund rules, and boolean fields. It does not verify that IDs or profile data exist; the agent must do that through the banking tools.

## Failure handling

- If a discoverable-tool call fails, do not guess its output or repeat an operation that was reported as unknown. Explain the issue and obtain the missing information or use the appropriate supported escalation path.
- Do not use a profile field from a merely similar user record, and do not substitute a card's last four digits from a transaction-history field when the discovered card lookup is available.
- Do not include `partial_refund_amount` for a non-partial resolution. For a partial resolution, require a positive amount before filing.
- If the customer asks to cancel/reissue the card, follow the supported replacement-card workflow if available, then use `cancel_and_reissue` in the dispute filing payload.
