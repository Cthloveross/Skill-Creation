---
name: credit-card-fraud-replacement-and-cli
summary: Process a verified cardholder's fraud dispute, replacement-card request, and credit-limit-increase request while applying documented card tiers, eligibility gates, tool order, and required payloads.
---

# Credit-card fraud, replacement, and CLI workflow

Use this Skill when a credit-card customer reports an unauthorized transaction and may also need a replacement card or a credit-limit increase (CLI). Treat each as a separate workflow, prioritize account security, and use current tool results and customer-provided facts. Never invent a history result, eligibility fact, order result, or completed action.

## 1. Identity gate

Before filing a dispute, ordering a replacement, submitting a CLI, approving, or denying:

1. Look up the claimed customer record.
2. Compare customer-provided values against the record. Verify at least two of date of birth, registered email, registered phone number, and registered address.
3. Obtain the current timestamp and call `log_verification` with the verified record's `name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`, and `time_verified`.

If two fields do not match, collect another permitted identity field or use normal escalation. Do not take a sensitive account action first.

## 2. Determine the card tier before applying tier rules

Use the actual card product returned by the account lookup. **Gold Rewards Card is Premium tier** for CLI, provisional-credit, and replacement-shipping rules. Do not claim that Gold's tier is unknown when the card product is known.

Use `scripts/assess_case.py` for read-only classification, calculations, and message generation. It does not replace live bank-tool calls or required customer communication.

## 3. Fraud-dispute workflow

Confirm the selected completed transaction belongs to the verified customer and selected account. Obtain all required filing facts: transaction identifier, last four digits, registered contact details, transaction date, date noticed, merchant-contact answer, supported reason, and requested resolution.

1. Set `card_action` to `cancel_and_reissue` when the customer wants the compromised card replaced; otherwise set it to `keep_active`.
2. Determine provisional-credit eligibility before filing. Retrieve history with `get_user_dispute_history_7291` and evaluate all documented conditions:
   - account open at least 60 days;
   - reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` (and the last is only eligible when the purchase is more than 30 days old);
   - amount is at least $25 and no more than the tier cap: Entry $2,500, Mid $5,000, Premium $10,000, Elite $15,000, Invitation $25,000;
   - no more than two disputes in the prior 12 months; and
   - for a non-fraud dispute, the customer contacted the merchant.
3. Unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool`. Supply its arguments as a JSON string containing:
   `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`.
4. Use `MM/DD/YYYY` for both dates. Permitted reasons are `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed`. Resolutions are `full_refund`, `partial_refund`, or `reversal_of_charge`. Include numeric `partial_refund_amount` only for `partial_refund`.
5. If provisional credit is eligible, explain that it is temporary while the investigation is pending.

## 4. Replacement-card workflow

Before unlocking the replacement tool, verify identity is logged; confirm the account, shipping address, replacement reason, and shipping selection; and establish replacement eligibility.

1. Use `get_pending_replacement_orders_5765` with the credit-card account ID. Any order not clearly `delivered` or `cancelled` blocks another replacement order.
2. Establish the number of replacements in the preceding 60 days from an authorized source. Limits are Entry 2, Mid 3, and Premium-and-above 4. If that evidence is unavailable, do not state that the customer is eligible and do not order the card; obtain the record or provide a clear specialist handoff.
3. The exact reason must be one of `fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`. Standard shipping is free and takes 7–10 business days. Expedited shipping takes 2–3 business days and costs Entry $15, Mid $10, and Premium or above $0. Capture fee acknowledgement only when a fee applies. Recommend expedited shipping for fraud or theft.
4. If eligibility is established, unlock `order_replacement_credit_card_7291`, then call it through `call_discoverable_agent_tool`. Use the account-identifier field exposed by the unlocked tool and provide `reason`, `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and `notes`.
5. Do not create a duplicate order merely because the dispute used `cancel_and_reissue`. After a successful replacement order, explain that the old card is cancelled, the new card has a new number/CVV, the selected delivery timeframe, email notifications, and the need to review unauthorized transactions.

## 5. CLI workflow — strict order

### A. Mandatory pre-submission amount gate

Classify the tier and calculate the maximum permitted increase from the *current* credit limit:

- Entry: 25%
- Mid: 50%
- Premium: 50%

The requested increase must be a positive whole-dollar amount. If it exceeds the calculated maximum, **do not submit it and do not deny it**. Before a transfer or any other handoff, tell the customer all of the following:

- their requested increase exceeds the permitted maximum;
- the calculated maximum dollar increase; and
- ask whether they want to adjust the request and proceed with that permitted amount instead.

Use the helper's `customer_message` verbatim when available. This communication is mandatory even if other work is pending or the customer later asks for a transfer. Wait for an affirmative revised amount; do not interpret silence as consent.

### B. Submit only a confirmed in-limit amount

After the customer confirms a valid amount, first call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. Submission must occur before any CLI eligibility decision.

### C. Complete every post-submission check

After submission, check and record all of these before deciding:

- account age: Entry 120 days, Mid 90, Premium 60;
- cooldown since the most recent approved CLI: Entry 120, Mid 90, Premium 60, using `get_credit_limit_increase_history_4829`;
- no active disputes;
- no pending replacement order, using `get_pending_replacement_orders_5765`;
- no past-due balance;
- utilization strictly below Entry 70%, Mid 80%, or Premium 90%; and
- on-time payment history with `get_payment_history_6183`: Entry 6 months and Mid/Premium 3 months.

If all checks pass, call `approve_credit_limit_increase_5847` with account ID, user ID, and `new_credit_limit` equal to current limit plus the confirmed increase. If any check fails, call `deny_credit_limit_increase_5848` with the applicable documented reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`.

An active dispute or pending replacement blocks CLI approval. Explain known blockers without inventing a future eligibility date.

## Helper script

Run the read-only helper with a supplied case JSON file:

```sh
python3 scripts/assess_case.py < case.json
```

Input is one JSON object with optional `identity`, `cli`, `dispute`, and `replacement` objects. Output is one JSON object containing only validations, tier determinations, computed limits, and next actions. For `cli`, provide `card_type`, `current_credit_limit`, and `requested_increase_amount`; an above-limit result includes a ready-to-send `customer_message`. For `dispute`, provide the facts needed to assess provisional credit. For `replacement`, provide tier/card type, order statuses, and replacement count if authoritatively known.

Any `missing`, `errors`, `unknown`, or `eligible_to_submit: false` result is a stop signal for the affected action. The executor must still perform the documented live lookups, tool unlocks, calls, and customer communication.
