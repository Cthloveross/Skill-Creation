---
name: file-credit-card-transaction-dispute
description: Handle a Rho-Bank request to formally dispute a credit-card transaction. Use to identify the exact charge, collect the dispute form facts, retrieve the required card last four digits using the supported customer card-details tool, decide provisional-credit eligibility, validate the payload, and file it through the internal dispute tool.
---

# File a Credit Card Transaction Dispute

Use this Skill for a customer asking to dispute a credit-card charge. Do not file until every required filing field is known from the customer or authoritative account data. Do not invent an ID, date, card digits, or requested remedy.

## Required filing payload

`file_credit_card_transaction_dispute_4829` requires these fields:

- `transaction_id` (string)
- `card_action`: `keep_active` or `cancel_and_reissue`
- `card_last_4_digits` (a string of exactly four digits)
- `full_name`, `user_id`, `phone`, `email`, `address`
- `contacted_merchant` (boolean)
- `purchase_date` and `issue_noticed_date` (`MM/DD/YYYY`)
- `dispute_reason`, one of `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`
- `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`
- `partial_refund_amount` only for `partial_refund`, and then as a positive number
- `eligible_for_provisional_credit` (boolean)

## Procedure

1. **Identify the customer, then locate the charge.** Use a supplied full name or registered email with the appropriate normal banking lookup. Before a consequential account action, confirm two of the registered identity fields (date of birth, email, phone, or address). After two fields match, obtain the current time and call `log_verification` with the canonical full profile and that timestamp. If identity cannot be verified, do not disclose account details or file the dispute. Retrieve the customer's credit-card transactions and accounts. Match the transaction by merchant, date, amount, and card type. If multiple transactions reasonably match, ask the customer to distinguish them. Take `transaction_id`, `purchase_date`, amount, and card type only from that matched record. Use the matching card type to select the card account.

2. **Obtain the card digits through the supported route.** The required `get_card_last_4_digits(credit_card_account_id)` is a *customer* discovered tool, not an agent-discoverable tool. Once the matched account ID is known, pass it to the customer using `give_discoverable_user_tool` with:

   ```json
   {"credit_card_account_id":"<matched account id>"}
   ```

   Also explicitly tell the customer the exact signature, `get_card_last_4_digits(credit_card_account_id: str)`, and identify the matched account ID as the value to use. This is particularly important when they say they do not have the physical card or cannot find the lookup; do not merely refer to a generic “card-details lookup.” Use the returned four digits only if available. Do **not** try to unlock or call this customer tool through `call_discoverable_agent_tool`, and do not substitute a last-four value from transaction history. If the customer cannot access the lookup and cannot provide four digits after being given the exact tool, explain that the formal filing cannot be submitted yet; do not submit a partial or guessed payload.

3. **Collect only unresolved dispute facts.** Record merchant contact as a boolean. Convert “today” to the date returned by `get_current_time` in `MM/DD/YYYY`; otherwise obtain an explicit noticed date. Map facts to the enum, rather than treating a customer narrative as an enum:
   - a materially different room, item, or service that was received is `goods_services_not_as_described`;
   - an item/service never received is `goods_services_not_received`.

   A request to get the whole transaction amount back is `full_refund`. Ask for a dollar amount for `partial_refund`. Use `keep_active` unless the customer asks for a replacement/cancellation; use `cancel_and_reissue` only when the card is actually being cancelled and replaced.

4. **Determine provisional credit.** Apply the documented criteria using the matched account and transaction. An account must be at least 60 days old; amount must be at least $25 and within the card tier limit; there must be no more than two disputes filed in the preceding 12 months; and non-fraud disputes require merchant contact. The only potentially eligible reasons are `unauthorized_fraudulent_charge`, `duplicate_charge`, and `goods_services_not_received` where purchase was more than 30 days ago. All other permitted reasons are categorically ineligible. Thus a known categorically ineligible reason can be sent as `eligible_for_provisional_credit: false` without making unnecessary historical lookups.

   For a reason that might be eligible, unlock and call `get_user_dispute_history_7291` with `user_id`, count records whose `dispute_date` falls in the 12 months before the evaluation date, and use `scripts/evaluate_provisional_credit.py`. An affirmative result requires every criterion to be known and true. If it is not conclusively eligible or ineligible, resolve the missing eligibility information before filing rather than assuming provisional credit.

   Tier ceilings are: Entry $2,500 (Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card); Mid $5,000 (Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card); Premium $10,000 (Gold Rewards Card, Business Gold Rewards Card); Elite $15,000 (Platinum Rewards Card, Business Platinum Rewards Card); Invitation $25,000 (Diamond Elite Card).

5. **Validate and file.** Construct the exact JSON object from live facts. Run `scripts/validate_dispute_payload.py`; it must return `valid: true`. Then unlock `file_credit_card_transaction_dispute_4829` and call it with the payload encoded as the `arguments` JSON string. Tell the customer only the actual filing result. If the tool errors or gives no confirmation, do not say the dispute was filed.

## Helper scripts

Both scripts take one JSON object on stdin and emit one JSON object on stdout. They recommend/validate data only; they do not execute bank actions.

### `scripts/evaluate_provisional_credit.py`

Input schema:

```json
{
  "account_open_date":"MM/DD/YYYY",
  "purchase_date":"MM/DD/YYYY",
  "evaluation_date":"MM/DD/YYYY",
  "dispute_reason":"permitted reason",
  "transaction_amount":100.00,
  "card_type":"card type",
  "prior_disputes_past_12_months":0,
  "contacted_merchant":true
}
```

Output includes `eligible_for_provisional_credit`, `determinate`, `checks`, `errors`, and the tier limit. A `determinate: false` result has insufficient valid facts. A categorically disallowed reason produces a determinate `false` result when the reason itself is valid.

### `scripts/validate_dispute_payload.py`

Send the exact proposed filing object. It emits `{"valid": boolean, "errors": [...]}` and checks required strings, dates, enums, booleans, four-digit format, and partial-refund conditionality. It cannot establish that an ID or profile field is correct; use the normal banking lookup results for that.

## Failure handling

- Never retry a banking operation reported as `UNKNOWN`.
- If a lookup or discovered tool is unavailable, do not guess its result. Obtain the missing required field or defer filing.
- Do not disclose a customer's account details to identify a merely similar record.
- Omit `partial_refund_amount` for non-partial remedies. Do not cancel a card merely because the customer has a merchant dispute.
