---
name: credit-card-transaction-dispute-filer
description: File one or more supported credit-card transaction disputes after matching transactions, collecting the required card and customer details, retrieving prior-dispute history, and determining provisional-credit eligibility. Use for unauthorized, duplicate, billing, merchant, delivery, subscription, and refund disputes.
---

# Credit Card Transaction Dispute Filer

Use this Skill to prepare and file **one separate dispute per transaction**. Do not file a dispute until all required form fields are known and the transaction has been matched to the customer's card transaction history.

## Required information

For every dispute, obtain or verify:

- transaction ID, purchase date, amount, merchant, and card from transaction history;
- card last four digits for the card on which the transaction occurred;
- full name, user ID, registered phone, email, and address;
- whether the customer contacted the merchant (`true` or `false`), including an explicit answer for fraud disputes;
- issue-noticed date in `MM/DD/YYYY`;
- one permitted dispute reason;
- one permitted resolution; if `partial_refund`, also a positive numeric partial-refund amount;
- card action: `keep_active` or `cancel_and_reissue`;
- whether the dispute is eligible for provisional credit.

Permitted reason codes:

- `unauthorized_fraudulent_charge`
- `duplicate_charge`
- `incorrect_amount`
- `goods_services_not_received`
- `goods_services_not_as_described`
- `canceled_subscription_still_charging`
- `refund_never_processed`

Permitted resolution codes: `full_refund`, `partial_refund`, and `reversal_of_charge`.

## Workflow

1. **Identify and match the customer.** Look up the customer from the supplied identifying information. Retrieve their card accounts and transaction history. Match each requested dispute to exactly one transaction using card, merchant, amount, and date. If no unique match exists, ask the customer to clarify; never guess a transaction ID.

2. **Collect missing customer choices and dates.** Ask for any unspecified issue-noticed dates, merchant-contact answers, requested resolution, partial amount where applicable, and fraud-card action. If the customer says they noticed an issue “today,” use the date returned by `get_current_time`, convert it to `MM/DD/YYYY`, and confirm that interpretation when necessary. Do not use a relative date without resolving it.

3. **Obtain card last four digits.** The customer can retrieve these with `get_card_last_4_digits(credit_card_account_id: str)`. For each needed account, use `give_discoverable_user_tool` with that exact tool name and an arguments JSON string containing the account ID, then wait for the customer's tool result. Associate each returned four-digit value with its account. Do not substitute a full card number, an account ID, or an inferred value for `card_last_4_digits`.

4. **Retrieve dispute history.** Unlock `get_user_dispute_history_7291`, then call it through `call_discoverable_agent_tool` using `{"user_id":"..."}`. Count disputes whose filing date is within the preceding 12 months relative to the current date. This is the count of *previous* disputes: retrieve it once before filing the requested set and do not increment the count merely because other disputes in the same requested batch have been filed.

5. **Determine provisional-credit eligibility independently for each transaction.** It is `true` only if all conditions below hold:
   - card account has been open at least 60 days as of the current date;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`;
   - for `goods_services_not_received`, the purchase was more than 30 days ago;
   - transaction amount is at least 25.00 and no greater than the card-tier maximum;
   - previous disputes in the past 12 months are no more than 2;
   - for a non-fraud reason, the customer contacted the merchant.

   Tier caps are: 2,500 for Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, and Crypto-Cash Back Card; 5,000 for Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, and Silver Zoom Card; 10,000 for Gold Rewards Card and Business Gold Rewards Card; 15,000 for Platinum Rewards Card and Business Platinum Rewards Card; 25,000 for Diamond Elite Card. An unrecognized card type cannot establish eligibility; set eligibility to `false` and retain the reason for review.

6. **Optionally use the packaged planner.** Create structured case records from the collected runtime facts and run `scripts/plan_disputes.py`. It validates form-level conditions and returns one payload-ready record per case with eligibility and explanations. Review all `errors` before filing. The script only computes and validates; it does not access banking systems or file disputes.

7. **File each complete dispute.** Unlock `file_credit_card_transaction_dispute_4829` once. For each case, call `call_discoverable_agent_tool` with `agent_tool_name` set to that exact name and `arguments` set to a JSON string containing:

```json
{
  "transaction_id": "string",
  "card_action": "keep_active",
  "card_last_4_digits": "1234",
  "full_name": "string",
  "user_id": "string",
  "phone": "string",
  "email": "string",
  "address": "string",
  "contacted_merchant": true,
  "purchase_date": "MM/DD/YYYY",
  "issue_noticed_date": "MM/DD/YYYY",
  "dispute_reason": "duplicate_charge",
  "resolution_requested": "reversal_of_charge",
  "eligible_for_provisional_credit": false
}
```

Include `partial_refund_amount` only when `resolution_requested` is `partial_refund`. Preserve JSON booleans and numeric partial-refund amounts; do not send them as strings. Record each tool outcome. If one filing fails, correct only that case if possible and continue with other independent, complete cases; never retry an outcome reported as unknown.

8. **Close the interaction.** Tell the customer which disputes were filed and, if known from the filing outcome, their identifiers or next steps. Explain that provisional credit is temporary while an investigation proceeds. Clearly identify any transactions not filed and the exact missing information needed.

## Validation helper

Run the planner with JSON on standard input, for example:

```bash
python3 scripts/plan_disputes.py <<'JSON'
{
  "as_of_date": "MM/DD/YYYY",
  "previous_disputes_last_12_months": 0,
  "customer": {"full_name":"...","user_id":"...","phone":"...","email":"...","address":"..."},
  "cases": [
    {
      "transaction_id":"...", "card_type":"...", "account_open_date":"MM/DD/YYYY",
      "card_last_4_digits":"....", "amount": 0.0, "purchase_date":"MM/DD/YYYY",
      "issue_noticed_date":"MM/DD/YYYY", "contacted_merchant":true,
      "dispute_reason":"...", "resolution_requested":"...", "card_action":"..."
    }
  ]
}
JSON
```

Input schema: the top-level fields are `as_of_date`, `previous_disputes_last_12_months`, `customer`, and `cases`. Each case has the fields shown above; `partial_refund_amount` is additionally required for partial refunds. Dates must be `MM/DD/YYYY`. Output is JSON with `valid`, `errors`, and `plans`. Each plan contains `eligible_for_provisional_credit`, `eligibility_reasons`, and a `payload` suitable for the filing tool when no errors are present.

The helper does not replace transaction matching, card-digit retrieval, prior-history retrieval, or the actual tool calls. Use runtime-supplied data rather than embedding any customer, account, transaction, or answer in this Skill.
