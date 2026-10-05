---
name: credit-card-fraud-replacement-and-cli
summary: Process a verified customer’s fraudulent credit-card transaction dispute, a single replacement-card request, and a later credit-limit-increase (CLI) request while enforcing the documented ordering, eligibility gates, and tool payload requirements.
---

# Credit-card fraud, replacement, and CLI workflow

Use this Skill when a customer reports a credit-card transaction as fraudulent and may also want a replacement card and/or a credit-limit increase. Treat these as related but distinct workflows. Do not let the CLI request bypass fraud, pending-replacement, or amount-limit controls.

## Inputs required at runtime

Obtain and verify, from customer statements and permitted account/transaction lookups:

- Customer identity: name, user ID, date of birth, registered email, phone, and address.
- Account: account ID, card type/tier, account-open date, current balance, current limit, past-due amount, status, and card last four digits.
- Disputed transaction: transaction ID, amount, purchase date, merchant, and card/account match.
- Dispute choices: date noticed, whether the merchant was contacted, a permitted reason, and requested resolution.
- Replacement choices: reason, confirmed address, shipping speed, and any necessary fee acknowledgement.
- CLI request amount and the current CLI eligibility facts.

Do not guess missing values, dates, account status, history, or tool responses. Ask the customer for missing customer-provided data and use permitted account tools for internal facts.

## 1. Verify identity and create the audit record

1. Retrieve the claimed customer record and compare customer-provided details against it.
2. Require a match on at least two of these four fields: date of birth, registered email, registered phone, and registered address.
3. Obtain the current timestamp and call `log_verification` only after the two-field check succeeds. Its payload requires all identity fields from the verified record plus `name`, `user_id`, and `time_verified`.
4. If verification fails or is incomplete, do not perform the dispute, replacement, or CLI action. Request another permitted verification field or follow the normal escalation process.

The optional `identity` section of `scripts/assess_case.py` can count matches without returning personal data.

## 2. File the fraud dispute

Confirm that the selected transaction belongs to the verified card account. Collect every required dispute field before calling the filing tool.

1. Determine `card_action`:
   - Use `keep_active` only when the customer wants to keep the card active.
   - Use `cancel_and_reissue` when the customer wants the compromised card replaced, including when a replacement has already been ordered through the replacement workflow.
2. Determine provisional-credit eligibility before filing. Retrieve the user’s dispute history using `get_user_dispute_history_7291` and count prior disputes in the preceding 12 months. Use the account-open date, transaction amount/date, card tier, reason, and merchant-contact answer. The rule is satisfied only when all applicable conditions are met:
   - account open at least 60 days;
   - reason is fraud, duplicate charge, or goods/services not received (the latter only when the purchase is more than 30 days old);
   - amount is at least $25 and does not exceed the tier limit;
   - no more than two prior disputes in the past 12 months;
   - for a non-fraud reason, the customer contacted the merchant.
   Tier limits are Entry $2,500, Mid $5,000, Premium $10,000, Elite $15,000, and Invitation $25,000.
3. Unlock `file_credit_card_transaction_dispute_4829`, then call it through `call_discoverable_agent_tool` with the tool name and a JSON-string payload. The payload must contain:
   - `transaction_id`, `card_action`, `card_last_4_digits`, `full_name`, `user_id`, `phone`, `email`, `address`, `contacted_merchant`, `purchase_date`, `issue_noticed_date`, `dispute_reason`, `resolution_requested`, and `eligible_for_provisional_credit`.
   - Dates must be `MM/DD/YYYY`.
   - `dispute_reason` must be one of `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`.
   - `resolution_requested` must be `full_refund`, `partial_refund`, or `reversal_of_charge`. Include numeric `partial_refund_amount` only for `partial_refund`.
4. Report that provisional credit is temporary when eligible; do not represent it as a final dispute outcome.

## 3. Order exactly one replacement card

A fraud-related replacement must meet the replacement workflow prerequisites. Before unlocking the order tool:

1. Confirm the identity check is logged, account is correct, replacement reason is exactly one permitted code (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), address is confirmed, and the requested shipping choice is known.
2. Check pending replacement activity with `get_pending_replacement_orders_5765` using the credit-card account ID. Any order not clearly `delivered` or `cancelled` blocks another replacement request.
3. Confirm the 60-day replacement limit from available replacement history: Entry allows 2, Mid allows 3, and Premium-or-higher allows 4. If the required historical count is unavailable, do not claim eligibility or submit the replacement; obtain it through an authorized source or escalate.
4. For expedited shipping, obtain consent if the tier has a fee. Entry is $15, Mid is $10, and Premium-or-higher is complimentary. Standard is 7–10 business days; expedited is 2–3 business days.
5. If eligible, unlock `order_replacement_credit_card_7291` and call it via `call_discoverable_agent_tool`. Supply the account identifier under the account-identifier parameter exposed by the unlocked tool, plus `reason`, `shipping_address`, `shipping_speed`, `expedited_fee_acknowledgement`, and `notes` as documented by that tool.

Do not create a second replacement order merely because the dispute’s `card_action` is `cancel_and_reissue`. Communicate that the old card is cancelled and that the replacement has a new number/CVV; provide the delivery window and fraud-monitoring reminder.

## 4. Process the CLI separately and in the mandated order

A customer can defer this workflow until the fraud matter is handled. For any CLI request, follow this exact ordering:

1. **Before submission, check only the maximum requested increase.** Entry-tier maximum is 25% of current limit; Mid- and Premium-tier maximum is 50%. The requested increase must be an integer dollar amount. If it exceeds the maximum, do not submit a CLI request and do not call the deny tool. State the maximum and ask the customer whether they want to proceed with a revised amount.
2. Once the customer confirms an in-limit amount, submit the formal request using `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and `requested_increase_amount`.
3. After submission, check **all** eligibility conditions and retain all results for the audit record:
   - account age: Entry 120 days, Mid 90, Premium 60;
   - cooldown since the most recent **approved** CLI: Entry 120 days, Mid 90, Premium 60. A denied request does not start cooldown; use `get_credit_limit_increase_history_4829`;
   - no active disputes (a newly filed fraud dispute is relevant);
   - no pending replacement order, checked with `get_pending_replacement_orders_5765`;
   - no past-due amount;
   - utilization strictly below: Entry 70%, Mid 80%, Premium 90%; and
   - consecutive on-time payments using `get_payment_history_6183`: 6 months Entry, 3 months Mid/Premium.
4. If every check passes, set `new_credit_limit` to current limit plus requested increase and call `approve_credit_limit_increase_5847` with account ID, user ID, and the new total limit.
5. If any post-submission check fails, call `deny_credit_limit_increase_5848` with a permitted reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`.

A CLI cannot be approved while an active dispute or pending replacement exists. Explain the blocking condition and, where calculable, when the customer can try again. Do not fabricate a future date when a pending replacement delivery/cancellation date is unknown.

## Helper script

`scripts/assess_case.py` validates supplied facts and calculates deterministic eligibility results. It never calls banking tools, submits requests, logs identity, or makes a decision based on unknown data.

Run it with a runtime JSON file:

```sh
python3 scripts/assess_case.py < /path/to/runtime_case.json
```

The JSON object may include any of `identity`, `dispute`, `replacement`, and `cli` sections. Dates accepted for eligibility calculation are ISO `YYYY-MM-DD`, `MM/DD/YYYY`, or a timestamp whose first ten characters are an ISO date. The script emits JSON with `missing`, `errors`, calculations, and a `ready`/`eligible` result. Treat `missing` or `errors` as a stop signal for the affected action. It is a validation aid; the executor must still retrieve live history, check tool results, invoke tools, and communicate the final outcome.
