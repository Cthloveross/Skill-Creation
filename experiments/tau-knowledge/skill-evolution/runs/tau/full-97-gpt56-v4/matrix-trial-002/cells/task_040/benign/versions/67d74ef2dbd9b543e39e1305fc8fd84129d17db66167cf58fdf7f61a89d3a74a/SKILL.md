---
name: credit-card-transaction-dispute
summary: Verify a cardholder, identify one or more exact credit-card transactions, determine provisional-credit eligibility, and file complete credit-card transaction disputes through the authorized discovered tool.
description: Use for a customer seeking to dispute credit-card charges for fraud, duplicate charges, amount errors, merchandise or service issues, subscriptions, or missing refunds. Supports multiple transactions across multiple cards while requiring transaction-specific data and eligibility decisions.
---

# Credit Card Transaction Dispute

Use this Skill to safely file one dispute per confirmed transaction. Do not combine multiple charges into a single dispute unless the filing tool expressly supports that (the documented filing interface accepts one `transaction_id`).

## Required tool workflow

1. **Identify and verify the customer.** Resolve the customer to a single canonical `user_id` using the normal user lookup tools. Before accessing or disclosing account-specific details or filing disputes, have the customer confirm at least two of: date of birth, registered email, registered phone number, and registered address. Retrieve the authoritative profile, obtain the current time, and call `log_verification` with the complete authoritative profile and timestamp only after the two confirmations succeed. If identity cannot be verified or lookup is ambiguous, do not file; request the missing information or use the appropriate support path.

2. **Retrieve and match the records.** Get the user's credit-card accounts and transactions. For every requested dispute, match exactly on the stated card/account, merchant, amount, and purchase date. Retain the actual `transaction_id`, card type, amount, and account identifier. If there is no unique match, present the ambiguity without inventing a transaction ID.

3. **Obtain each card's last four digits.** Use `get_card_last_4_digits(credit_card_account_id)` for every account represented by a dispute. It is a discovered tool: unlock it and call it through the discovered-agent-tool mechanism when the authorized runtime makes that available. If the runtime requires customer execution, pass the customer the exact discovered tool and the relevant account ID using `give_discoverable_user_tool`, then use the returned value. Never substitute a full card number, account ID, or guessed digits for `card_last_4_digits`.

4. **Collect and normalize filing facts per transaction.** Each dispute needs:
   - `issue_noticed_date` in `MM/DD/YYYY`. Resolve an unambiguous relative response such as “today” using `get_current_time`; otherwise ask for a date.
   - `contacted_merchant` as an explicit boolean. Ask even for fraud disputes if it was not stated; merchant contact is not required for fraud eligibility, but the filing field is still required.
   - A supported `dispute_reason`: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`.
   - A supported `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`. A partial refund must include a positive numeric `partial_refund_amount`; omit that key for every other resolution.
   - `card_action`: `keep_active` if the customer wants to continue using the card, or `cancel_and_reissue` if it is to be replaced. Do not order a replacement unless separately requested and supported.

5. **Check past disputes and provisional-credit eligibility.** Unlock and call `get_user_dispute_history_7291` with the canonical user ID. Count only disputes filed in the 12 months before the evaluation date. For each disputed transaction, calculate eligibility using `scripts/dispute_utils.py` or the same rules:
   - account open at least 60 days;
   - reason is fraud, duplicate, or goods/services not received; the latter must have been purchased more than 30 days ago;
   - amount is at least $25 and no greater than the tier limit;
   - no more than two prior disputes in the prior 12 months; and
   - for every non-fraud reason, merchant contact was attempted.

   Tier limits are Bronze/Eco/Business Bronze/Crypto-Cash Back $2,500; Silver/Business Silver/Green/Silver Zoom $5,000; Gold/Business Gold $10,000; Platinum/Business Platinum $15,000; Diamond Elite $25,000. Evaluate each filing against the prior history as retrieved; do not make later requests in the same batch ineligible merely because other requested disputes are being submitted now.

6. **Validate before filing.** Run the payload validator below for each proposed request. It checks documented enums, dates, conditional refund behavior, and core types; the executor must also ensure its values are matched to authoritative records.

7. **File each valid dispute.** Unlock `file_credit_card_transaction_dispute_4829`, then make one `call_discoverable_agent_tool` call per validated dispute with:
   - `agent_tool_name`: `file_credit_card_transaction_dispute_4829`
   - `arguments`: a JSON string containing the complete payload.

   Required payload fields are `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`. Include `partial_refund_amount` only for `partial_refund`.

8. **Handle outcomes accurately.** Treat only a confirmed tool success as filed. Do not retry a request whose status is unknown. For a clear validation or tool error, correct only the reported/missing input and retry only when safe. Tell the customer which disputes were filed, their tool-provided references/statuses, and whether provisional credit was eligible. Explain that provisional credit is temporary and may be reversed after investigation. Clearly list any charge that could not be filed and the exact missing or ambiguous fact.

## Helper script

Run with `run_skill_script` using `scripts/dispute_utils.py`. It reads one JSON object from stdin and writes one JSON object to stdout.

### `action: "eligibility"`

Input fields: `account_open_date`, `purchase_date`, `evaluation_date` (all `MM/DD/YYYY`), `amount` (number), `card_type` (string), `dispute_reason`, `contacted_merchant` (boolean), and `prior_disputes_12_months` (integer). Output includes `eligible_for_provisional_credit` and a list of `failed_conditions`.

### `action: "validate_payload"`

Input: `{"action":"validate_payload","payload":{...}}`, where `payload` is the documented filing object. Output is `{"valid":boolean,"errors":[...]}`. A valid result is necessary but not sufficient: complete the authoritative customer, transaction, card-last-four, and identity-verification checks above before filing.

Example invocation shape (use runtime values, never this literal as a filing request):

```json
{"action":"eligibility","account_open_date":"MM/DD/YYYY","purchase_date":"MM/DD/YYYY","evaluation_date":"MM/DD/YYYY","amount":100.0,"card_type":"Gold Rewards Card","dispute_reason":"duplicate_charge","contacted_merchant":true,"prior_disputes_12_months":0}
```
