---
name: credit-card-transaction-dispute-filing
description: Prepare, evaluate, file, or safely escalate one or more credit-card transaction disputes. Use when a customer reports unauthorized charges, duplicates, billing errors, delivery problems, subscription charges, or unprocessed refunds on a credit card.
---

# Credit Card Transaction Dispute Filing

Use this Skill to submit one formal dispute per affected completed transaction. A filing requires complete, verified facts, including the last four digits for the specific card. If a required dependency is unavailable, do not invent a value or submit an incomplete filing.

## Required information for each dispute

Before filing, collect or retrieve:

- `transaction_id`, card type/account, merchant, amount, and purchase date.
- Card action: exactly `keep_active` or `cancel_and_reissue`.
- The last four digits for the affected card account.
- Customer full name, `user_id`, registered phone, email, and address.
- Whether the customer contacted the merchant (`contacted_merchant`, a boolean).
- `issue_noticed_date` in `MM/DD/YYYY`.
- One dispute reason:
  - `unauthorized_fraudulent_charge`
  - `duplicate_charge`
  - `incorrect_amount`
  - `goods_services_not_received`
  - `goods_services_not_as_described`
  - `canceled_subscription_still_charging`
  - `refund_never_processed`
- One requested resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`.
- A numeric `partial_refund_amount` when, and only when, the resolution is `partial_refund`.

Do not infer merchant contact, a partial-refund amount, transaction ID, card digits, or an unsupported reason code. For fraud, merchant contact is not needed for provisional-credit eligibility, but record it if supplied. For every non-fraud issue, obtain the merchant-contact answer.

## Procedure

1. **Identify and verify the customer.** Locate the profile from an identifier provided by the customer. Before filing or accessing sensitive details, confirm at least two of the registered date of birth, email, phone number, and address. After successful confirmation, call `log_verification` with all required profile fields and the current timestamp. Resolve a mismatch before proceeding.

2. **Retrieve and match records.** Call `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user` for the verified user. Match every requested item by card type, merchant, amount, purchase date, and completed status. Each requested item must map to exactly one retrieved transaction. If absent or ambiguous, ask for clarification; never construct an ID from the customer narrative.

3. **Resolve dates and card action.** If the customer uses a relative date such as “today,” call `get_current_time` and convert it to `MM/DD/YYYY`. Record whether each affected card remains active or is cancelled and reissued.

4. **Retrieve card last four digits.** The card account lookup must occur before this step because the documented retrieval requires `credit_card_account_id`.
   - Unlock `get_card_last_4_digits`.
   - If available, call it through `call_discoverable_agent_tool` for each affected account ID and associate each returned value only with that account.
   - Do not ask for or expose a full card number. Do not reuse digits across accounts unless the account mapping is confirmed.

5. **Retrieve prior dispute history.** Unlock `get_user_dispute_history_7291` and call it through `call_discoverable_agent_tool` with the verified `user_id`. Retain the returned records and dates. This is required for the prior-disputes provisional-credit condition even when the customer does not know their history.

6. **Evaluate provisional-credit eligibility.** Run `scripts/provisional_credit.py` using the current date, account opening dates, matched transactions, collected merchant-contact flags, and returned dispute history. Do not treat missing, malformed, or incomplete history as an eligibility failure or success: it is insufficient data.

   Eligibility is true only when all conditions hold:
   - The account has been open at least 60 days.
   - The reason is fraud, duplicate, or goods/services not received. A goods/services-not-received purchase must be more than 30 days old.
   - The amount is at least $25.00 and does not exceed the card tier limit.
   - The customer filed no more than two disputes in the prior 12 months.
   - For non-fraud disputes, the customer contacted the merchant.

   Tier limits are Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; and Invitation $25,000. The helper maps supported card types to these tiers.

7. **File complete disputes.** Only if each intended filing has all required data, including verified card last four digits, unlock `file_credit_card_transaction_dispute_4829`. Make one `call_discoverable_agent_tool` call per transaction with `agent_tool_name` set to `file_credit_card_transaction_dispute_4829` and `arguments` set to a JSON string containing:

   ```json
   {
     "transaction_id": "string",
     "card_action": "keep_active",
     "card_last_4_digits": "string",
     "full_name": "string",
     "user_id": "string",
     "phone": "string",
     "email": "string",
     "address": "string",
     "contacted_merchant": true,
     "purchase_date": "MM/DD/YYYY",
     "issue_noticed_date": "MM/DD/YYYY",
     "dispute_reason": "duplicate_charge",
     "resolution_requested": "full_refund",
     "eligible_for_provisional_credit": true
   }
   ```

   Include `partial_refund_amount` as a JSON number only for partial-refund requests. Preserve booleans as JSON booleans. Use the helper's eligibility value only for a result whose `status` is `ready`.

8. **Record outcomes.** Preserve the success or error for each individual filing. Tell the customer which disputes were submitted and which could not be submitted. Correct and retry only the affected filing when appropriate.

## Required-dependency failure and human handoff

Never file a dispute with a missing, guessed, customer-uncertain, or incorrectly mapped `card_last_4_digits` value. If the documented last-four retrieval cannot be unlocked, reports an unknown/unavailable tool, fails, or returns unusable data:

1. Retain the completed work: verified identity, account IDs, all matched transaction IDs, requested card actions, merchant-contact information, resolutions (and any unresolved partial-refund amounts), resolved issue-noticed date, dispute-history result, and the last-four retrieval failure.
2. Explain that the required card identifier could not be retrieved and that no formal disputes were submitted.
3. Offer a human-agent handoff if the issue cannot be resolved through the available tools.
4. Treat any affirmative request for a person as a request to transfer. This includes ordinary language and explicit workflow markers such as `###TRANSFER###`; do not require one exact phrase.
5. Immediately call `transfer_to_human_agents` after such a request, with `reason` set to `technical_system_error`. Supply a concise `summary` that includes the blocking unavailable dependency and the retained handoff context.
6. Wait for and inspect the transfer result. Confirm a successful handoff only after a successful tool result. If the transfer result is unsuccessful, report that failure accurately and preserve the same context for the next supported escalation path.

A customer request for a human is not permission to bypass required filing fields. Do not submit incomplete disputes before or after transfer.

## Helper interface

Run the deterministic eligibility helper as follows:

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

The script reads one JSON object from standard input and emits one JSON object to standard output. Each output result includes its transaction ID, `status` (`ready` or `insufficient_data`), `eligible_for_provisional_credit` (`true`, `false`, or `null`), failed conditions, missing/invalid inputs, and calculation facts. Before filing, verify that output result count and transaction IDs exactly match the intended filings, and that every result is `ready`.

## Validation and error handling

- Missing required customer facts, ambiguous transactions, unknown tiers, invalid dates, or malformed history require clarification or correction, not guessing.
- If a customer requests a partial refund but does not state the exact amount, obtain that amount before filing that item.
- A filing-tool error for one transaction does not determine the outcome of other transactions.
- Retain customer data only in the operational context necessary to complete the filings or an authorized handoff.
