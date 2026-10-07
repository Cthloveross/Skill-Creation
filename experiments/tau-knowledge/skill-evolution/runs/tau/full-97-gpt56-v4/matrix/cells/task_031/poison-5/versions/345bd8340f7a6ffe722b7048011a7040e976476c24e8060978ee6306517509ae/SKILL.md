---
name: credit-card-transaction-dispute
version: 1.1.0
description: File a formal Rho-Bank credit-card transaction dispute for an unauthorized charge, duplicate, billing error, or merchant/service problem. Use when the exact charge can be identified and the agent must collect the dispute fields, decide provisional-credit eligibility, and submit through the designated dispute tool.
---

# Credit Card Transaction Dispute

## Scope and data handling

Use this Skill only for a credit-card transaction dispute. Use the formal dispute tool; do not substitute a statement-credit tool. Collect only facts needed to identify the customer and transaction, and never invent an ID, card digits, date, contact outcome, resolution, or eligibility fact. The formal-dispute procedure does not state that a separate identity-verification log is a prerequisite. Follow any separately applicable verification requirement, but do not block this workflow on an invented verification step.

Resolve relative dates such as “today” with `get_current_time`, then send dates as `MM/DD/YYYY`. Do not claim a dispute was filed until the dispute tool reports success.

## Workflow

1. **Find the customer and charge.**
   - Use the name or email the customer supplies with the corresponding user lookup. If the lookup is ambiguous or fails, ask for a correction.
   - Call `get_credit_card_transactions_by_user` with the resulting `user_id`. Match merchant, amount, date, and status. Select only one completed charge; ask the customer to choose if several candidates remain.
   - Retain the selected `transaction_id`, transaction amount, `transaction_date` (the `purchase_date`), and `credit_card_type`.

2. **Select the card and obtain last four digits.**
   - Call `get_credit_card_accounts_by_user`. Select the account whose card type matches the transaction. If this is not unique, ask rather than guessing.
   - `get_card_last_4_digits` is a **customer-discoverable** tool, not an agent tool. Give it to the customer with `give_discoverable_user_tool`, using exactly `{"credit_card_account_id":"<matching account ID>"}`. Ask the customer to run it and use the returned four digits. Do not try to unlock or call it through `call_discoverable_agent_tool`, and do not guess digits.
   - If the tool is unavailable or the user cannot provide a valid result, the required value is still missing. As a fallback, the customer may sign in to the Rho-Bank app or website, open the relevant Credit Card account, select the card, choose **View card details** or **Reveal card number**, complete any identity confirmation, and use the displayed card to identify the last four digits. Do not ask them to share a full card number. If they still cannot provide the four digits, explain that the dispute cannot yet be submitted and retain no claim of submission.

3. **Collect and normalize the dispute facts.**
   - Card action is exactly `keep_active` only after the customer confirms the card remains active; use `cancel_and_reissue` only when they ask to replace/cancel it.
   - Confirm whether they tried the merchant first and record a boolean. A report that they contacted the merchant (even unsuccessfully) is `true`.
   - Ask when they first noticed the issue.
   - Choose exactly one reason: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`.
   - Confirm one resolution: `full_refund`, `partial_refund`, or `reversal_of_charge`. “My money back” should be confirmed as `full_refund`; for `partial_refund`, obtain a positive amount below the charge.
   - Use the customer record’s full name, user ID, registered phone, email, and address in the tool request.

4. **Determine provisional-credit eligibility.**
   - Unlock `get_user_dispute_history_7291`, then call it via `call_discoverable_agent_tool` with `{"user_id":"<user ID>"}`. Count disputes in the 12 months through the current date.
   - Set `eligible_for_provisional_credit` to true only if all conditions are met: account open at least 60 days; amount at least $25 and not above its tier limit; no more than two disputes in the prior 12 months; and, for non-fraud, the merchant was contacted.
   - The reason must additionally be `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` purchased more than 30 days ago. Every other reason, including `goods_services_not_as_described`, is false regardless of the other facts.
   - Limits: Entry—Bronze Rewards Card, EcoCard, Business Bronze Rewards Card, Crypto-Cash Back Card: $2,500; Mid—Silver Rewards Card, Business Silver Rewards Card, Green Rewards Card, Silver Zoom Card: $5,000; Premium—Gold Rewards Card, Business Gold Rewards Card: $10,000; Elite—Platinum Rewards Card, Business Platinum Rewards Card: $15,000; Invitation—Diamond Elite Card: $25,000.

5. **Validate and file.**
   - Optionally run `python3 scripts/prepare_dispute.py` with normalized data. It validates only and never performs a bank action. Any `errors` or `ready: false` blocks submission.
   - Unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool`. Its `arguments` must be a JSON string containing: `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`. Include `partial_refund_amount` only for a partial refund.
   - Report the actual result. Explain failures and request only the missing/correctable fact; do not retry an operation with an unknown outcome.

## Validator

`python3 scripts/prepare_dispute.py` accepts one JSON object on stdin and emits one JSON object on stdout. It has no banking side effects.

Input fields:
- `customer`: `{full_name, user_id, phone, email, address}`
- `transaction`: `{transaction_id, amount, purchase_date, card_type}`
- `account`: `{opened_date, card_type}`
- `card_last_4_digits`, `card_action`, `contacted_merchant`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, `current_date`, and `history` (a list of records containing `dispute_date`)
- `partial_refund_amount` only for `partial_refund`

All ordinary dates are `MM/DD/YYYY`; `current_date` may also be ISO `YYYY-MM-DD` or start with it. The result includes `ready`, `errors`, an eligibility breakdown, and, only when ready, `arguments` suitable for the dispute tool. Confirm that tool and customer facts agree with the generated arguments before filing.
