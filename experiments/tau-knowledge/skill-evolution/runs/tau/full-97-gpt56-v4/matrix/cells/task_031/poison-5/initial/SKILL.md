---
name: credit-card-transaction-dispute
version: 1.0.0
description: File a formal Rho-Bank credit-card transaction dispute when a customer reports an unauthorized charge, duplicate, billing error, or merchant/service problem. Use this Skill to verify the customer, identify the exact transaction and card, collect all required dispute data, determine provisional-credit eligibility, and submit the dispute through the designated discoverable agent tool.
---

# Credit Card Transaction Dispute

## Scope and safety

Use this Skill only for a credit-card transaction dispute. Do not substitute a statement-credit tool for the formal dispute process. Do not submit a dispute until the transaction is unambiguous, the customer has supplied or confirmed the required details, and identity verification has been completed according to the available banking tools.

Never invent a transaction ID, card digits, date, contact information, merchant-contact response, requested resolution, or eligibility fact. Interpret relative dates such as “today” using `get_current_time`, then convert them to `MM/DD/YYYY`.

## Required workflow

1. **Identify and verify the customer.**
   - Locate the customer with an available user lookup using the name or email they provide.
   - Obtain the user record and ask the customer to confirm two of the four identity fields: date of birth, registered email, registered phone number, and registered address. Do not reveal the stored values as prompts.
   - Compare the two supplied values to the user record. Once successful, call `get_current_time` and then call `log_verification` with all fields required by that tool and the current timestamp.
   - Stop and seek correction if identity cannot be verified.

2. **Find the exact completed transaction.**
   - Call `get_credit_card_transactions_by_user` for the verified `user_id`.
   - Match the customer’s merchant, amount, and/or date description to one completed transaction. If more than one candidate remains, present only the necessary non-sensitive transaction summaries and ask the customer to select one.
   - Record its `transaction_id`, amount, transaction date, and card type. The transaction date is the `purchase_date` in the required `MM/DD/YYYY` format.

3. **Identify the associated card and last four digits.**
   - Call `get_credit_card_accounts_by_user` and select the account whose card type matches the selected transaction. If that does not uniquely identify an account, ask for clarification; never guess.
   - Unlock `get_card_last_4_digits`, then call it through `call_discoverable_agent_tool` with the matching credit-card account ID, using the exact arguments the discovered tool requires. Use its returned four digits as `card_last_4_digits`.

4. **Collect and normalize every dispute fact.**
   - Confirm whether the customer wants `keep_active` or `cancel_and_reissue`. A replacement request maps to `cancel_and_reissue`; otherwise use `keep_active` only when the customer confirms the card should remain active.
   - Ask whether they attempted to resolve the issue with the merchant; preserve the answer as a boolean.
   - Ask when they first noticed the issue. Convert a relative answer using the current date.
   - Classify the issue into exactly one allowed reason:
     - `unauthorized_fraudulent_charge`
     - `duplicate_charge`
     - `incorrect_amount`
     - `goods_services_not_received`
     - `goods_services_not_as_described`
     - `canceled_subscription_still_charging`
     - `refund_never_processed`
   - Ask what resolution they want and map it to exactly one of `full_refund`, `partial_refund`, or `reversal_of_charge`. If it is `partial_refund`, obtain a positive dollar amount that is less than the transaction amount.
   - Use the verified registered `full_name`, `user_id`, phone, email, and address. Do not ask the customer to repeat them if already securely verified.

5. **Determine provisional-credit eligibility.**
   - Retrieve dispute history before deciding: unlock `get_user_dispute_history_7291`, then call it via `call_discoverable_agent_tool` with the verified user ID.
   - The customer is eligible only when **all** conditions hold:
     1. the selected account has been open at least 60 days;
     2. the reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` where the purchase was more than 30 days ago;
     3. the amount is at least $25 and no more than the maximum for that card tier;
     4. no more than two disputes were filed in the preceding 12 months; and
     5. for every non-fraud reason, the customer contacted the merchant first.
   - Limits: Entry $2,500 (Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card); Mid $5,000 (Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card); Premium $10,000 (Gold Rewards Card, Business Gold Rewards Card); Elite $15,000 (Platinum Rewards Card, Business Platinum Rewards Card); Invitation $25,000 (Diamond Elite Card).
   - If the reason is not one of the eligible categories, set `eligible_for_provisional_credit` to `false` even if other conditions are met. Do not promise that a provisional credit is permanent.

6. **Validate and submit.**
   - Optionally run `scripts/prepare_dispute.py` to validate normalized records and construct the payload. The script only validates and recommends a request; it cannot take banking actions.
   - Unlock `file_credit_card_transaction_dispute_4829`.
   - Call `call_discoverable_agent_tool` with `agent_tool_name` set to `file_credit_card_transaction_dispute_4829` and `arguments` set to a JSON string containing all required fields:
     `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`.
   - Include `partial_refund_amount` only for `partial_refund`.
   - Report the actual tool result to the customer. State that the dispute was filed only after a successful tool result. If it fails, do not claim success; explain the missing/correctable input and retry only after correcting it.

## Validator script

Run `python3 scripts/prepare_dispute.py` and send one JSON object on stdin. It emits one JSON object on stdout.

Input schema:
- `customer`: `{full_name, user_id, phone, email, address}`
- `transaction`: `{transaction_id, amount, purchase_date, card_type}`
- `account`: `{opened_date, card_type}`
- `card_last_4_digits`, `card_action`, `contacted_merchant`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `current_date`
- `history`: a list of objects with `dispute_date` values (or an empty list)
- `partial_refund_amount` only when applicable

Dates must be supplied as `MM/DD/YYYY`; `current_date` may also be ISO `YYYY-MM-DD` or a timestamp beginning with that date. The output has `ready`, `errors`, `eligibility`, and, when ready, `arguments`. Treat any nonempty `errors` or `ready: false` as a blocker. Independently confirm that the normalized facts match the customer and tool results before submitting.
