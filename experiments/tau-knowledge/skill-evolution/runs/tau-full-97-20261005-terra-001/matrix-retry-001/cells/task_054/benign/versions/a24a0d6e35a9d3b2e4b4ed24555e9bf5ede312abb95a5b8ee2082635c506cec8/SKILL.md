---
name: credit-card-fraud-replacement-and-cli
version: 1.1.0
description: Process a verified cardholder's unauthorized-transaction dispute, fraud-related replacement-card request, and credit-limit-increase request while preserving required tool order, eligibility checks, runtime-schema validation, and accurate customer communications.
---

# Credit-card fraud, replacement, and CLI workflow

Use this Skill when one verified customer needs an unauthorized credit-card transaction disputed, a replacement card, and/or a credit-limit increase (CLI). It is designed for the normal banking-tool executor: the included scripts calculate eligibility from supplied runtime facts only; they do not call tools or perform bank actions.

## Inputs to obtain at runtime

Use live account and transaction records, never identifiers or values from another conversation. Obtain or confirm:

- Identity verification: the customer must supply and match **two of four** profile fields: date of birth, email, phone number, and address.
- User ID, card account ID, card type/tier, account opening date, current balance, credit limit, past-due amount, and card last four digits.
- The disputed transaction ID, amount, merchant, and purchase date.
- Dispute details: full name, issue-noticed date, reason, whether the merchant was contacted, and requested resolution.
- Replacement reason, confirmed shipping address, shipping speed, and consent for an expedited fee where applicable.
- Requested CLI increase amount and explicit confirmation of any lower amount offered because the original request exceeded the tier maximum.

Do not treat an account lookup, a stated name, or a request to use an address on file as identity verification. Ask the customer to provide two profile fields, compare them with the profile, then call `log_verification` with the complete profile fields and current timestamp before any dispute filing, replacement order, or CLI action. If identity cannot be verified, do not perform account actions.

## Fraud dispute and replacement sequence

1. Look up the account and transaction, and verify that the transaction belongs to the selected account. Obtain current time for the verification audit record if needed.
2. After identity verification is logged, unlock and call `get_user_dispute_history_7291` with `user_id`. Count disputes filed in the prior 12 months for provisional-credit evaluation. Do not infer a count from an incomplete response.
3. Determine provisional-credit eligibility with `scripts/assess_provisional_credit.py` using fresh, verified facts. For an unauthorized fraud dispute, merchant contact is not required, but pass the actual customer response to the filing tool.
4. Before ordering a replacement, unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`.
   - Any order not clearly `delivered` or `cancelled` is pending. Do not submit another replacement order.
   - Enforce the tier's 60-day replacement limit when replacement-history data is available: Entry 2, Mid 3, Premium and above 4. If accessible records do not establish the count, do not invent eligibility; use an authorized eligibility record or explain/escalate the unavailable prerequisite.
5. If eligible, unlock and call `order_replacement_credit_card_7291`. Supply the account identifier, one permitted reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), confirmed shipping address, `standard` or `expedited` speed, expedited-fee acknowledgement, and useful notes.
   - Expedited delivery is 2–3 business days. It is complimentary for Premium tier and above; Entry costs $15 and Mid costs $10, so capture consent when a fee applies.
   - For `fraud_suspected` or `stolen`, strongly recommend expedited shipping and remind the customer to review transactions.
6. Unlock `file_credit_card_transaction_dispute_4829`, inspect the exposed runtime argument schema, then call it only if that schema supports every required customer-selected value. Supply every required argument. Use `cancel_and_reissue` when a replacement is being issued; otherwise use `keep_active` only when the customer keeps the card. Format dates as `MM/DD/YYYY`.
7. The policy-supported dispute resolution values are `full_refund`, `partial_refund`, and `reversal_of_charge`. A runtime schema can be more restrictive than policy. If the customer's requested value (for example, `reversal_of_charge`) is absent from the unlocked runtime schema, do **not** silently substitute another resolution and do not claim that a dispute was filed.
   - Tell the customer explicitly: **"I wasn't able to complete the dispute filing because the available filing form does not support your requested charge reversal."** Adapt only the final noun phrase if a different requested resolution is unsupported.
   - Offer a human-agent transfer to complete the unresolved dispute. If the customer accepts and the runtime exposes `transfer_to_human_agents`, call it with `reason: "fraud_or_security_concern"` and a concise summary of the transaction, requested resolution, schema incompatibility, and actions already completed.
   - If the runtime rejects a filing call, explain the concrete returned error when safe to disclose, offer the same handoff, and do not characterize the filing as complete.
8. Do not make up a transaction date, issue-noticed date, history count, provisional-credit result, runtime option, or tool success. If a tool fails or returns an ambiguous record, stop the affected action and resolve the missing prerequisite.

A successful replacement order cancels the old card for new purchases. Tell the customer the selected delivery window, that email notifications are expected when ordered and shipped, and, for fraud/stolen cases, to review and dispute other unauthorized transactions.

## CLI sequence and ordering

The following ordering is mandatory:

1. Classify the account tier and calculate the maximum permitted increase from the **current** limit:
   - Entry: 25%.
   - Mid and Premium: 50%.
2. If the requested increase exceeds that amount, tell the customer the maximum and obtain an explicit revised amount. **Do not submit** an excessive request and do not record a denial for the unconfirmed excessive amount.
3. Once the amount is valid and confirmed, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and the increase amount. Submission comes before internal CLI eligibility checks.
4. After successful submission, complete **every** check, even after a failure is found:
   - account age;
   - cooldown using `get_credit_limit_increase_history_4829` (only an approved prior request creates a cooldown, measured from its submission date);
   - active disputes, using `get_user_dispute_history_7291`;
   - pending replacement orders, using `get_pending_replacement_orders_5765`;
   - account current/no past-due balance;
   - current utilization; and
   - consecutive on-time payments, using `get_payment_history_6183` with 6 months for Entry or 3 months for Mid/Premium.
5. Use the tier thresholds below. Account age may equal its threshold; utilization must be strictly below its threshold.

| Tier | Age | Cooldown after approved request | Maximum utilization | On-time months |
|---|---:|---:|---:|---:|
| Entry | 120 days | 120 days | below 70% | 6 |
| Mid | 90 days | 90 days | below 80% | 3 |
| Premium | 60 days | 60 days | below 90% | 3 |

6. If all checks pass, unlock and call `approve_credit_limit_increase_5847` with `new_credit_limit` equal to current limit plus the valid requested increase.
7. If any check fails, unlock and call `deny_credit_limit_increase_5848` with one permitted reason. Preserve all failures in the case record. Where only one reason can be sent, use the first failed criterion in required-check order: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, then `insufficient_payment_history`. Use `requested_amount_exceeds_limit` only for a formally submitted invalid amount, which this workflow normally prevents.

A filed fraud dispute or a newly placed replacement may cause the subsequently submitted CLI to fail active-dispute and/or pending-replacement checks. Still complete every check and record the applicable denial. Never bypass those checks because the requested increase is within the tier maximum.

## Tool invocation discipline

Named banking tools are discoverable tools in this runtime. Before first use of each named tool, call `unlock_discoverable_agent_tool` with that exact tool name, then invoke it through `call_discoverable_agent_tool` with a JSON arguments object. Reuse an already unlocked tool rather than unlocking it repeatedly. Do not claim an action was completed until its tool reports success.

Known tool argument contracts:

- `get_user_dispute_history_7291`: `user_id`
- `get_pending_replacement_orders_5765`: `credit_card_account_id`
- `get_credit_limit_increase_history_4829`: `credit_card_account_id`
- `get_payment_history_6183`: `credit_card_account_id`, `months`
- `submit_credit_limit_increase_request_7392`: `credit_card_account_id`, `user_id`, `requested_increase_amount` (integer dollars)
- `approve_credit_limit_increase_5847`: `credit_card_account_id`, `user_id`, `new_credit_limit` (number)
- `deny_credit_limit_increase_5848`: `credit_card_account_id`, `user_id`, `denial_reason`

## Deterministic eligibility helpers

### Provisional-credit helper

Run after dispute-history retrieval with normalized, verified facts:

```json
{"as_of_date":"YYYY-MM-DD","account_open_date":"MM/DD/YYYY","card_tier":"Premium","purchase_date":"MM/DD/YYYY","transaction_amount":"487.50","dispute_reason":"unauthorized_fraudulent_charge","contacted_merchant":false,"disputes_past_12_months":0}
```

```text
python scripts/assess_provisional_credit.py < input.json
```

It emits JSON with `eligible`, individual criteria, and failed criteria. Set `eligible_for_provisional_credit` to this boolean only when the helper received complete, verified inputs. Supported reasons are the filing-tool reason values.

### CLI helper

After submission and all post-submission checks, normalize the tool outputs and run:

```json
{"as_of_date":"YYYY-MM-DD","account_open_date":"MM/DD/YYYY","card_tier":"Premium","current_balance":"0.00","current_credit_limit":"5000.00","past_due_amount":"0.00","requested_increase_amount":"2500","last_approved_request_date":null,"has_active_disputes":false,"pending_order_statuses":[],"consecutive_on_time_months":3}
```

```text
python scripts/assess_credit_limit_request.py < input.json
```

The output provides `can_submit`, `can_approve`, threshold calculations, each criterion, and the single denial code under the documented ordering. A null `last_approved_request_date` means the history result verified that no approved request establishes a cooldown; do not use null merely because history was unavailable. Validate that every criterion is present and passed before approval.

## Customer communication

Give an accurate result for each action actually completed:

- Dispute: confirm filing, selected resolution, and whether provisional credit applies only after a successful filing. If the selected resolution is unavailable, explicitly say the filing was not able to be completed and offer/perform the approved transfer flow.
- Replacement: confirm cancellation of the old card, delivery timing, shipping status, and fee.
- CLI approval: confirm the new total limit.
- CLI denial: state the actual reason and next step. For a pending replacement, explain that CLI processing cannot proceed until the replacement is delivered or cancelled. Do not promise a reapplication date unless records establish it.

Never expose internal-only eligibility mechanics beyond a customer-appropriate explanation, and never state that an unexecuted bank action has occurred.
