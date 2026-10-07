---
name: credit-card-transaction-dispute-filing
description: File one or more formal credit-card transaction disputes after identity verification, transaction matching, card-last-four retrieval, dispute-history review, and provisional-credit eligibility determination. Use when a customer reports unauthorized, duplicate, billing, delivery, subscription, or refund problems on a credit card.
---

# Credit Card Transaction Dispute Filing

Use this Skill to prepare and submit a separate formal dispute for each affected credit-card transaction. It supports all permitted reason codes and calculates provisional-credit eligibility from account, transaction, and dispute-history facts.

## Required inputs per dispute

Collect or retrieve the following before filing:

- Transaction: `transaction_id`, card type/account, merchant, amount, and purchase date.
- Card decision: `keep_active` or `cancel_and_reissue`.
- Card last four digits.
- Customer: full name, `user_id`, registered phone, registered email, and registered address.
- `contacted_merchant` boolean.
- `issue_noticed_date` in `MM/DD/YYYY`.
- One permitted `dispute_reason`:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- One permitted `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`.
- A numeric `partial_refund_amount` only when the requested resolution is `partial_refund`.

Do not infer a merchant-contact answer. For fraud, record whether the customer contacted the merchant if they provide it; the eligibility rule does not require merchant contact for fraud. For non-fraud disputes, explicitly obtain the answer.

## Procedure

1. **Identify and verify the customer.** Locate the profile using an identifier supplied by the customer. Before filing or accessing sensitive card/dispute details, have the customer confirm at least two of date of birth, registered email, phone number, and address against the profile. Call `log_verification` after successful confirmation, supplying the profile's required identity fields and a current timestamp. Stop and resolve an identity mismatch before proceeding.

2. **Retrieve and match source records.** Use `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user` with the verified `user_id`. Match each requested merchant, amount, purchase date, and card type to exactly one completed transaction. Ask for clarification if a transaction is absent or ambiguous; never construct a transaction ID from narrative details.

3. **Resolve dates and card action.** Obtain a current date with `get_current_time` when a customer says “today” or gives another relative date, then store the resolved `issue_noticed_date` in `MM/DD/YYYY`. Record the customer’s chosen card action for each affected card. If replacement is chosen, the dispute value is `cancel_and_reissue`; otherwise use `keep_active`.

4. **Get card last four digits.** Unlock `get_card_last_4_digits`, then call it through `call_discoverable_agent_tool` for each affected credit-card account ID. Associate the returned four digits with that specific account. Do not ask for a full card number and do not reuse digits across cards without confirming the account mapping.

5. **Review dispute history.** Unlock `get_user_dispute_history_7291` and call it through `call_discoverable_agent_tool` with the verified `user_id`. Retain the returned dispute dates. This step is required to determine the prior-disputes eligibility condition even if the customer is unsure of their history.

6. **Determine provisional-credit eligibility.** For every matched transaction, evaluate all conditions below using the current date as the assessment date. Run `scripts/provisional_credit.py` to make the repeated date, tier-limit, amount, and history calculations consistent. Do not file until its status is `ready` for each dispute.

   A dispute is eligible only if all apply:
   - The account has been open at least 60 days.
   - The reason is fraud, duplicate, or goods/services not received. For goods/services not received, the purchase must be more than 30 days old.
   - The amount is at least $25 and no higher than the card-tier maximum: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000.
   - The customer has filed no more than two disputes in the twelve months ending on the assessment date.
   - For every non-fraud reason, the customer contacted the merchant.

   Card types map to tiers as follows: Entry—Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card; Mid—Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card; Premium—Gold Rewards Card, Business Gold Rewards Card; Elite—Platinum Rewards Card, Business Platinum Rewards Card; Invitation—Diamond Elite Card. An unknown card type, malformed date, or incomplete history is insufficient data, not a reason to guess `false`.

7. **File each dispute.** Unlock `file_credit_card_transaction_dispute_4829` once, then make one `call_discoverable_agent_tool` call per transaction. Its `arguments` must be a JSON string containing:

   ```json
   {
     "transaction_id": "string",
     "card_action": "keep_active | cancel_and_reissue",
     "card_last_4_digits": "string",
     "full_name": "string",
     "user_id": "string",
     "phone": "string",
     "email": "string",
     "address": "string",
     "contacted_merchant": true,
     "purchase_date": "MM/DD/YYYY",
     "issue_noticed_date": "MM/DD/YYYY",
     "dispute_reason": "permitted_reason_code",
     "resolution_requested": "full_refund | partial_refund | reversal_of_charge",
     "eligible_for_provisional_credit": true
   }
   ```

   Include `partial_refund_amount` as a JSON number only for `partial_refund`; omit it for all other resolutions. Preserve booleans as JSON booleans, not quoted text. Use the script output's `eligible_for_provisional_credit` value only when it is `true` or `false` and status is `ready`.

8. **Handle results.** Record the success or error returned for each filing, clearly distinguish successful submissions from failures, and provide the customer a concise per-transaction outcome. A failed filing is not evidence that another filing failed; correct the reported issue and retry only that transaction when appropriate.

## Script interface

Run:

```bash
python3 scripts/provisional_credit.py <<'JSON'
{
  "as_of_date": "MM/DD/YYYY",
  "dispute_history": [{"dispute_date": "MM/DD/YYYY"}],
  "disputes": [{
    "transaction_id": "transaction identifier",
    "card_type": "Gold Rewards Card",
    "account_open_date": "MM/DD/YYYY",
    "transaction_amount": "123.45",
    "purchase_date": "MM/DD/YYYY",
    "dispute_reason": "duplicate_charge",
    "contacted_merchant": true
  }]
}
JSON
```

The script emits JSON with one result per submitted dispute. Each result has `status` (`ready` or `insufficient_data`), `eligible_for_provisional_credit` (`true`, `false`, or `null`), `failed_conditions`, `missing_or_invalid`, and calculation facts. Only `ready` results are valid for the filing tool. Verify that the number of results equals the number of intended filings and that every result has the correct transaction ID before making any action calls.

## Failure handling

- Ask for missing required dispute facts rather than filing a partial payload.
- If profile lookup produces multiple people or identity confirmation fails, do not continue with account access or filing.
- If card-last-four or dispute-history retrieval fails, retry or resolve that retrieval before determining eligibility; do not substitute customer uncertainty for history.
- If an item is not a completed transaction on the identified card, explain that it cannot yet be submitted as that transaction and obtain clarification.
- If the filing tool rejects a payload, preserve the returned error, correct only the invalid field(s), and resubmit that individual dispute if appropriate.
