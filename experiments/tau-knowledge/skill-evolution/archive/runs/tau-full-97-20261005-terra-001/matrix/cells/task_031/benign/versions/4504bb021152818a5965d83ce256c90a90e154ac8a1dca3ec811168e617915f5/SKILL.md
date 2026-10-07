---
name: credit-card-transaction-dispute
description: File a formal Rho-Bank credit-card transaction dispute after identity verification, transaction/card confirmation, required fact collection, and a documented provisional-credit eligibility determination. Use for unauthorized charges, merchant/service disputes, duplicate charges, billing errors, and refund issues.
---

# Credit Card Transaction Dispute

Use this Skill when a customer asks to dispute a posted credit-card transaction. The executor performs the banking-tool actions; the packaged script only validates data and prepares the exact dispute-tool payload.

## Required information

Collect or retrieve and confirm the following before filing:

- The exact disputed `transaction_id`, its amount, purchase date, and the card account that made it.
- Customer: `full_name`, `user_id`, registered `phone`, registered `email`, and registered `address`.
- The card's last four digits.
- Whether the customer contacted the merchant (`contacted_merchant`). For suspected fraud, record the customer's answer but do not delay the dispute for merchant contact.
- `issue_noticed_date` in `MM/DD/YYYY`. Convert relative answers (for example, “today”) using the current date obtained from `get_current_time`.
- One permitted reason and requested resolution:

| Field | Exact permitted values |
|---|---|
| `dispute_reason` | `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed` |
| `resolution_requested` | `full_refund`, `partial_refund`, `reversal_of_charge` |
| `card_action` | `keep_active`, `cancel_and_reissue` |

Use `keep_active` if the customer will continue using the existing card. Use `cancel_and_reissue` only when the card is being cancelled and replaced, including where a replacement was already ordered. Ask rather than infer this for a potential fraudulent charge. For `partial_refund`, also collect a positive numeric `partial_refund_amount`; omit that field for all other resolutions.

## Workflow

1. **Identify and verify the customer.** Locate the customer using supplied identifying information. Before proceeding with account-specific dispute work, have the customer confirm at least two of the four identity fields (date of birth, email, phone, address). Obtain `get_current_time` and call `log_verification` with the complete retrieved record and the verification timestamp. Do not treat an unconfirmed database lookup as a customer confirmation.

2. **Find the exact transaction and card.** Use `get_credit_card_transactions_by_user` and `get_credit_card_accounts_by_user` for the verified `user_id`. Match the customer's merchant/date/amount description to a single transaction. If there is more than one plausible transaction, present only the minimum non-sensitive distinguishing details and ask the customer to select one. Do not file against an ambiguous transaction.

3. **Obtain the last four digits.** The prescribed card-number procedure is the discovered tool `get_card_last_4_digits(credit_card_account_id: str)`. Per that procedure, give the customer this tool with `give_discoverable_user_tool`, using the selected card account ID, and wait for the returned last four digits. Do not request or expose the full card number. Confirm that the returned digits correspond to the selected card.

4. **Record the dispute facts.** The customer’s statement that they contacted the merchant is sufficient for `contacted_merchant`; do not replace it with a guess. Map their description to the exact reason code. A hotel providing a materially different room or service than booked is generally `goods_services_not_as_described`, not `goods_services_not_received`. Confirm whether “money back” means `full_refund`, `partial_refund`, or `reversal_of_charge` if the requested outcome is unclear.

5. **Determine provisional-credit eligibility.** Unlock `get_user_dispute_history_7291` with `unlock_discoverable_agent_tool`, then call it through `call_discoverable_agent_tool` with the verified `user_id`. Count prior credit-card disputes filed during the 12 months before the current date. Determine eligibility only when all of these are known:
   - account open for at least 60 days;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`; the last is eligible only when the purchase was more than 30 days ago;
   - transaction amount is at least $25.00 and no more than the card-tier limit;
   - no more than 2 prior disputes in the past 12 months;
   - for every non-fraud reason, the customer contacted the merchant.

   Tier limits are: Entry $2,500 (Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card); Mid $5,000 (Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card); Premium $10,000 (Gold Rewards Card, Business Gold Rewards Card); Elite $15,000 (Platinum Rewards Card, Business Platinum Rewards Card); Invitation $25,000 (Diamond Elite Card). Treat `Crypto-Cash Back` as the displayed-name variant of `Crypto-Cash Back Card` when returned by account data.

   The following reasons are never eligible: `incorrect_amount`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed`. Do not claim or send an eligibility value based on unknown account age, amount, tier, merchant-contact answer, or dispute history. Resolve missing data or a tool failure first; if an independently confirmed rule already makes the customer ineligible, the value is `false`.

6. **Prepare and validate the payload.** Run `scripts/prepare_dispute.py` using the schema below. Address every reported error. The script emits a ready-to-send object containing the 15 dispute-tool fields and an eligibility explanation. Review that the transaction and card still match the customer's selection.

7. **File once.** Unlock `file_credit_card_transaction_dispute_4829` with `unlock_discoverable_agent_tool`. Then call `call_discoverable_agent_tool` with `agent_tool_name` set to `file_credit_card_transaction_dispute_4829` and `arguments` set to a JSON string serialization of the script's `payload`. Do not call the filing tool until the payload is ready, and do not submit duplicates after a successful response. Tell the customer the filing outcome and any case/reference information returned by the tool. Provisional credit, when eligible, is temporary while the investigation proceeds.

## Payload preparation script

Run `scripts/prepare_dispute.py` with one JSON object on standard input. It writes one JSON object to standard output and performs no banking action.

### Input schema

Required fields are:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active | cancel_and_reissue",
  "card_last_4_digits": "four digit string",
  "full_name": "string",
  "user_id": "string",
  "phone": "string",
  "email": "string",
  "address": "string",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "exact reason code",
  "resolution_requested": "exact resolution code",
  "partial_refund_amount": "number; required only for partial_refund",
  "transaction_amount": "number",
  "card_type": "account card type",
  "account_open_date": "MM/DD/YYYY",
  "current_date": "MM/DD/YYYY or ISO date/timestamp",
  "prior_disputes_past_12_months": 0
}
```

`transaction_amount`, `card_type`, `account_open_date`, `current_date`, and `prior_disputes_past_12_months` are eligibility inputs and are never included in the filing payload. `partial_refund_amount` may be absent or `null` when it does not apply.

### Output schema and validation

The output contains `ready` (boolean), `errors` (list), `eligibility` (an object with `eligible` and evaluated conditions when possible), and `payload` when `ready` is true. `payload` contains exactly the arguments for `file_credit_card_transaction_dispute_4829`, with `partial_refund_amount` only for a partial refund. Only use `payload` if `ready` is true. A false `eligible` is a valid completed determination and does not itself block filing; missing or invalid eligibility inputs do block it.
