---
name: credit-card-fraud-replacement-and-cli
version: 1.0.0
description: Process a verified cardholder's unauthorized-transaction dispute, fraud-related replacement card request, and credit-limit-increase request while preserving required tool order, eligibility checks, and customer communications.
---

# Credit-card fraud, replacement, and CLI workflow

Use this Skill when one verified customer needs an unauthorized credit-card transaction disputed, a replacement card, and/or a credit-limit increase (CLI). It is designed for the normal banking-tool executor: the included scripts only calculate eligibility from supplied runtime facts; they do not call tools or perform bank actions.

## Inputs to obtain at runtime

Use the live account and transaction records rather than values from a previous conversation. Obtain or confirm:

- Identity verification: the customer must supply and match **two of four** profile fields: date of birth, email, phone number, and address.
- User ID, card account ID, card type/tier, account opening date, current balance, credit limit, past-due amount, and card last four digits.
- The disputed transaction ID, amount, merchant, and purchase date.
- Dispute details: full name, date issue was noticed, reason, whether the merchant was contacted, and requested resolution.
- Replacement reason, confirmed shipping address, shipping speed, and consent for any applicable expedited fee.
- Requested CLI increase amount and explicit confirmation of any lower amount offered because the original request exceeded the tier maximum.

Do not treat account lookup data, a stated name, or a request to use an address on file as completion of identity verification. Ask the customer to provide two profile fields, compare them to the profile, then call `log_verification` with all required profile fields and the current timestamp before any dispute filing, replacement order, or CLI action.

If identity cannot be verified, do not perform account actions.

## Fraud dispute and replacement sequence

1. Look up the account and transaction and confirm the transaction belongs to the selected account. Obtain current time for the audit record if needed.
2. After identity verification is logged, unlock and call `get_user_dispute_history_7291` with `user_id`. Count disputes filed in the prior 12 months for provisional-credit evaluation. Do not infer a count from an incomplete response.
3. Determine provisional-credit eligibility with `scripts/assess_provisional_credit.py`, using fresh facts. For an unauthorized fraud dispute, merchant contact is not required, but pass the actual boolean to the filing tool.
4. Before ordering a replacement, unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`.
   - Any order not clearly `delivered` or `cancelled` is pending. Do not submit another replacement order.
   - Enforce the tier's 60-day replacement limit when replacement-history data is available: Entry 2, Mid 3, Premium and above 4. Do not invent an eligibility result if the accessible records do not establish the count; use the available authorized replacement-eligibility record or explain/escalate the unavailable prerequisite according to normal procedures.
5. If eligible, unlock and call `order_replacement_credit_card_7291`. Supply the account identifier, one permitted reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`), confirmed shipping address, `standard` or `expedited` speed, expedited-fee acknowledgement, and useful notes.
   - Expedited delivery is 2–3 business days. It is complimentary for Premium-tier and above; Entry costs $15 and Mid costs $10, so capture consent where a fee applies.
   - For `fraud_suspected` or `stolen`, strongly recommend expedited delivery and remind the customer to review transactions.
6. Unlock and call `file_credit_card_transaction_dispute_4829` with every required argument. Use `cancel_and_reissue` as `card_action` when a replacement is being issued (including when the replacement was just ordered); otherwise use `keep_active` only if the customer wants to retain the card. For fraud use `unauthorized_fraudulent_charge`; use `reversal_of_charge` only after the customer confirms that resolution. Dates must be formatted `MM/DD/YYYY`.
7. Do not make up a transaction date, issue-noticed date, history count, provisional-credit result, or tool success. If a tool fails or returns an ambiguous record, stop the affected action and resolve the missing prerequisite.

A replacement order cancels the old card for new purchases. Tell the customer the selected delivery window, that email notifications are expected when ordered and shipped, and, for fraud/stolen cases, to review and dispute other unauthorized transactions.

## CLI sequence and ordering

The following ordering is mandatory:

1. Classify the account tier and calculate the maximum permitted increase from the **current** limit:
   - Entry: 25%.
   - Mid and Premium: 50%.
2. If the requested increase exceeds that amount, tell the customer the maximum and obtain an explicit revised amount. **Do not submit** an excessive request and do not record a denial for the unconfirmed excessive amount.
3. Once the amount is valid and confirmed, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and the increase amount. Submission comes before internal CLI eligibility checks.
4. After a successful submission, complete **every** check, even after a failure is found:
   - account age;
   - cooldown using `get_credit_limit_increase_history_4829` (only an approved prior request creates a cooldown, measured from its submission date);
   - active disputes, using `get_user_dispute_history_7291`;
   - pending replacement orders, using `get_pending_replacement_orders_5765`;
   - account current/no past-due balance;
   - current utilization; and
   - consecutive on-time payments, using `get_payment_history_6183` with 6 months for Entry or 3 months for Mid/Premium.
5. Use the tier thresholds below. `at least` account age is permitted; utilization must be strictly below its threshold.

| Tier | Age | Cooldown after approved request | Maximum utilization | On-time months |
|---|---:|---:|---:|---:|
| Entry | 120 days | 120 days | below 70% | 6 |
| Mid | 90 days | 90 days | below 80% | 3 |
| Premium | 60 days | 60 days | below 90% | 3 |

6. If all checks pass, unlock and call `approve_credit_limit_increase_5847` with `new_credit_limit` equal to current limit plus the valid requested increase.
7. If any check fails, unlock and call `deny_credit_limit_increase_5848` with one permitted reason. Preserve all failures in the case record. Where only one reason can be sent, use the first failed criterion in the required check order: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, then `insufficient_payment_history`. Use `requested_amount_exceeds_limit` only for a formally submitted invalid amount, which this workflow normally prevents.

A fraud dispute or a newly placed replacement may cause the subsequently submitted CLI to fail the active-dispute and/or pending-replacement checks. Still complete every check and record the applicable denial. Never bypass those checks because the requested increase is within the tier maximum.

## Tool invocation discipline

The named banking tools are discoverable tools in this runtime. Before first use of each named tool, call `unlock_discoverable_agent_tool` with that exact tool name, then invoke it through `call_discoverable_agent_tool` with a JSON arguments object. Do not claim an action was completed until its tool reports success. Reuse an already unlocked tool rather than unlocking it repeatedly.

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

Run with normalized, current facts after dispute history retrieval:

```json
{"as_of_date":"YYYY-MM-DD","account_open_date":"MM/DD/YYYY","card_tier":"Premium","purchase_date":"MM/DD/YYYY","transaction_amount":"487.50","dispute_reason":"unauthorized_fraudulent_charge","contacted_merchant":false,"disputes_past_12_months":0}
```

```text
python scripts/assess_provisional_credit.py < input.json
```

It emits JSON with `eligible`, all individual criteria, and reasons. Set the dispute tool's `eligible_for_provisional_credit` to this boolean only when the helper received complete, verified inputs. Supported reasons are the filing-tool reason values.

### CLI helper

After submission and all post-submission checks, normalize the tool outputs and run:

```json
{"as_of_date":"YYYY-MM-DD","account_open_date":"MM/DD/YYYY","card_tier":"Premium","current_balance":"0.00","current_credit_limit":"5000.00","past_due_amount":"0.00","requested_increase_amount":"2500","last_approved_request_date":null,"has_active_disputes":false,"pending_order_statuses":[],"consecutive_on_time_months":3}
```

```text
python scripts/assess_credit_limit_request.py < input.json
```

The output provides `can_submit`, `can_approve`, threshold calculations, each checked criterion, and the correct single denial code under the documented ordering. A `null` last approved date means the history response verified that no approved request establishes a cooldown; do not use null merely because history was unavailable. Validate that every criterion is present and passed before approval.

## Customer communication

Give a concise, accurate result for each action actually completed:

- Dispute: confirm filing, the selected resolution, and whether provisional credit applies (temporary and subject to investigation).
- Replacement: confirm cancellation of the old card, delivery timing, and shipping status/fee.
- CLI approval: confirm the new total limit.
- CLI denial: state the actual reason and applicable next step. For a pending replacement, explain the CLI cannot proceed until the replacement is delivered or cancelled. Do not promise a reapplication date unless the relevant date is established by the records.

Never expose internal-only eligibility mechanics beyond a customer-appropriate explanation, and never state that an unexecuted bank action has occurred.
