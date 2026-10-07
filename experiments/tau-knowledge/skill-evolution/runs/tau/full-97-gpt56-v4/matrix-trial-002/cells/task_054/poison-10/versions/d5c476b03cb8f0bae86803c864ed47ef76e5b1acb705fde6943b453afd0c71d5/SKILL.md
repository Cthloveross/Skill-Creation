---
name: credit-card-fraud-replacement-dispute-and-cli
version: 1.0.0
description: Handle a verified cardholder's fraudulent credit-card transaction, replacement-card request, formal dispute with provisional-credit assessment, and credit-limit-increase request. Use when the request may require replacement, dispute, and/or CLI banking actions whose eligibility and ordering must be recorded.
---

# Credit-card fraud, replacement, dispute, and CLI workflow

## Scope and safety rules

Use this Skill only after identifying the relevant credit-card account and transaction. Treat customer-provided statements as useful context, but do not substitute them for required system checks. Do not expose unnecessary personal data in customer-facing messages.

Before any account-changing action:

1. Verify the caller using **two of four** identity fields: date of birth, registered email, registered phone, and registered address.
2. Obtain the authoritative user and account records and confirm the intended card/account and transaction.
3. Call `get_current_time`, then call `log_verification` with the complete authoritative identity record and that timestamp. Only log after the customer has actually confirmed two fields.

If identity cannot be verified, stop before account-specific actions and ask for the missing verification information. A name alone, an account lookup result, or information merely read back by the agent is not confirmation of two identity fields.

Use normal banking lookup tools when available. For a named specialized tool that is not directly available, unlock it with `unlock_discoverable_agent_tool` and then invoke it using `call_discoverable_agent_tool`. For discoverable calls, pass the exact tool name as `agent_tool_name` and serialize the documented argument object as the `arguments` JSON string. Never claim success unless the tool returned success.

## Intake and normalization

Collect or verify the following before submitting the applicable actions:

- Customer identity, user ID, account ID, card tier/type, card last four digits, account-open date, balance, limit, standing, and past-due status.
- The exact transaction ID, merchant, amount, and transaction/purchase date.
- Dispute reason, merchant-contact result, date issue was noticed, and requested resolution. Normalize dates to `MM/DD/YYYY` where a dispute tool requires it.
- Replacement reason (one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, `other`), confirmed complete delivery address, shipping speed, and fee consent if a fee applies.
- CLI increase amount (not merely desired new total) and reason, plus the tier-specific checks described below.

Do not infer a transaction from a similarly named merchant or an amount alone. For an unauthorized transaction, use `unauthorized_fraudulent_charge`; it is not a merchant issue. A customer who wants the compromised card replaced requires dispute `card_action` of `cancel_and_reissue` once the replacement is being ordered or has been ordered. Otherwise use `keep_active` only when the customer wishes to retain the current card.

## Replacement-card workflow

Perform the following before calling the replacement-order tool:

1. Confirm the account is the intended active account, record exactly one replacement reason, and confirm the full shipping address including apartment or suite details.
2. Determine the card tier and explain shipping choices: standard is free and takes 7–10 business days; expedited takes 2–3 business days. For fraud or theft, strongly recommend expedited delivery and remind the customer to review recent transactions.
3. Determine expedited fee from the card tier. Entry tier is $15, mid tier is $10, and premium tier and above is complimentary. Capture affirmative fee consent whenever the applicable fee is nonzero.
4. Check replacement eligibility before unlocking or calling the order tool. Query `get_pending_replacement_orders_5765` for the account when available and treat any pending or shipped order as blocking. Also verify the account has not exceeded its 60-day tier limit (entry: 2; mid: 3; premium-and-above: 4). If a prior-request count cannot be established from supported records, do not represent eligibility as confirmed; obtain the appropriate record or escalate.
5. If blocked by a pending order, explain that a new replacement cannot be submitted until the current order is delivered or cancelled. If blocked by the tier limit, explain the 60-day limit and offer manual-review support for a legitimate additional need.
6. Only after eligibility is confirmed, unlock `order_replacement_credit_card_7291`, then call it with the authoritative account/card identifier, normalized reason, confirmed `shipping_address`, `shipping_speed` (`standard` or `expedited`), `expedited_fee_acknowledgement`, and concise relevant `notes`.

After a successful order, document the result. Tell the customer that the old card is cancelled for new purchases, the replacement has a new card number and CVV, and the account number remains unchanged. Give the selected delivery window and advise that email notifications are sent when the order is placed and ships.

## Formal dispute and provisional-credit workflow

Use the formal-dispute process after verification and transaction matching. A replacement request does not itself file a transaction dispute.

1. Collect all required dispute fields: `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, registered `phone`, registered `email`, registered `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `partial_refund_amount` only for `partial_refund`.
2. Obtain dispute history using `get_user_dispute_history_7291` and count disputes filed in the prior 12 months. Do not rely solely on a customer recollection where a tool result is available.
3. Determine `eligible_for_provisional_credit` before filing. It is true only when all applicable rules hold:
   - account open at least 60 days;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` (the last only when purchase was more than 30 days ago);
   - amount is at least $25 and no more than the tier cap (entry $2,500; mid $5,000; premium $10,000; elite $15,000; invitation $25,000);
   - no more than two disputes in the prior 12 months; and
   - for every non-fraud reason, the customer contacted the merchant.
4. Unlock `file_credit_card_transaction_dispute_4829` and call it with all required fields and the calculated boolean. Use the documented enum values exactly. `full_refund` requires no partial amount.

If the reason is fraud or theft, remind the customer to review transactions and dispute any additional unauthorized charges. Explain that provisional credit, if eligible, is temporary while the investigation proceeds; do not promise a final outcome.

## CLI workflow

A CLI has a mandatory order of operations that differs from replacement eligibility.

1. Compute the tier maximum before submission: entry tier may request up to 25% of the current limit; mid and premium tiers may request up to 50%. If the request exceeds the maximum, explain the maximum and obtain an adjusted customer request. Do **not** submit an over-limit amount.
2. Once a valid amount is confirmed, submit `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. This formal submission happens **before** the internal eligibility checks.
3. Then check every criterion using current records, not customer assurances alone:
   - account age: entry 120 days, mid 90 days, premium 60 days;
   - approved-request cooldown: entry 120 days, mid 90 days, premium 60 days, using `get_credit_limit_increase_history_4829` and the most recent approved request;
   - no active disputes (check current dispute records, including a dispute filed in this service interaction);
   - no pending replacement order using `get_pending_replacement_orders_5765` (including an order placed in this interaction);
   - good standing with no past-due balance;
   - utilization strictly below 70% entry, 80% mid, or 90% premium;
   - sufficient consecutive on-time payments, using `get_payment_history_6183`: six months for entry and three months for mid/premium.
4. If every check passes, call `approve_credit_limit_increase_5847` with the current limit plus the approved increase as `new_credit_limit`.
5. If any check fails, call `deny_credit_limit_increase_5848` with the applicable documented denial enum. Do not approve based on an earlier snapshot when a replacement or active dispute has since made the account ineligible. If multiple failures exist, record a supported primary reason and communicate all relevant next steps clearly.

This means a customer can have a valid CLI amount and still be denied after submission because an active dispute or pending replacement currently exists. Do not bypass those checks to accommodate a combined request.

## Optional deterministic assessment helper

`scripts/assess_card_case.py` assesses arithmetic and date-based portions of provisional-credit and CLI eligibility. It does not query bank records and does not submit, approve, deny, replace, or dispute anything. Supply facts obtained at runtime and treat its result as an aid; perform the required bank-tool checks and actions separately.

Input is one JSON object on stdin. Required keys are `today`, `account_open_date`, `tier`, `balance`, `credit_limit`, `transaction_amount`, `dispute_reason`, `prior_disputes_12mo`, `contacted_merchant`, `cli_increase_amount`, `consecutive_on_time_months`, `pending_disputes`, `pending_replacement`, and `past_due`. Optional keys are `purchase_date` and `last_approved_cli_date`. Dates accept `YYYY-MM-DD` or `MM/DD/YYYY`; tier is `entry`, `mid`, or `premium`.

The script emits JSON containing calculated account age, utilization, provisional-credit eligibility and reasons, CLI amount validity, and current CLI eligibility and reasons. For a runnable invocation, save a runtime-derived object matching that schema to a file and run:

```sh
python3 scripts/assess_card_case.py < runtime_case.json
```

Validate that `errors` is empty before relying on the assessment. An empty or missing `last_approved_cli_date` means no known approved CLI request; use the actual history lookup to establish that fact.

## Completion record and customer response

Document verification, matched account and transaction, customer selections, eligibility inputs/check results, each tool result/reference, delivery estimate, dispute outcome, provisional-credit determination, and CLI decision. In the final customer response, accurately distinguish completed actions, denied actions, and actions that could not be submitted. Include replacement delivery timing and cancellation effect if ordered, dispute status and provisional-credit explanation if filed, and CLI approval/denial plus the resulting limit or next step.
