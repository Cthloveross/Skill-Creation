---
name: credit-card-dispute-and-cli
version: 1.0.0
description: Handle a credit-card transaction dispute and/or credit-limit-increase (CLI) request. Use this for cardholders who need a formal dispute filed, provisional-credit eligibility determined, or a tier-based CLI processed through the required internal workflow.
---

# Credit-card dispute and CLI workflow

Use the supplied runtime tools to look up the customer and account; do not rely on values from prior conversations without confirming they match the current lookup. Treat every mutating action as consequential. Confirm the intended account, requested action, and amount before making a submission.

## Identity and data handling

1. Locate the customer by the name or email they supplied, then retrieve the relevant credit-card account and transaction list.
2. Before filing a dispute, submitting a CLI, or approving/denying a CLI, verify the customer by having them confirm **two of these four** account fields: date of birth, registered email, registered phone, or registered address. Do not ask the customer to disclose unnecessary full card-number information.
3. If two confirmed values match the retrieved user record, call `get_current_time`, then call `log_verification` with the complete retrieved identity record and that timestamp. Do not log a verification merely because the data was looked up.
4. If identity cannot be verified, explain that the requested account action cannot yet be completed. Do not use another customer's data or perform a mutating action.

## Dispute procedure

A formal dispute requires all required information before it can be filed:

- transaction ID and matching card account;
- `card_action`: exactly `keep_active` or `cancel_and_reissue`;
- card last four digits;
- full name, user ID, registered phone, registered email, and registered address;
- whether the customer contacted the merchant;
- purchase date and issue-noticed date in `MM/DD/YYYY` format;
- one valid dispute reason;
- one valid requested resolution; and
- provisional-credit eligibility.

### Gather and validate

1. Match the stated merchant, amount, date, and card type to an actual completed transaction. Use the transaction's ID and purchase date; do not invent either.
2. Ask only for missing dispute choices or dates. Normalize dates to `MM/DD/YYYY` and reject invalid or ambiguous dates rather than guessing.
3. Map the customer's facts to one exact reason code:
   - `unauthorized_fraudulent_charge`
   - `duplicate_charge`
   - `incorrect_amount`
   - `goods_services_not_received`
   - `goods_services_not_as_described`
   - `canceled_subscription_still_charging`
   - `refund_never_processed`
4. Map the requested remedy to `full_refund`, `partial_refund`, or `reversal_of_charge`. For `partial_refund`, obtain a positive numeric dollar amount and include it. Omit `partial_refund_amount` for every other resolution.
5. For a merchant/service dispute, explicitly ask whether they attempted to resolve it with the merchant. A statement that the merchant did not respond to outreach supports `contacted_merchant: true`; do not infer contact otherwise.
6. If card replacement is desired, use `cancel_and_reissue`; otherwise use `keep_active`. This choice is independent of whether the claim is fraud.

### Obtain card last four safely

The last four digits are mandatory. When the customer does not have them, offer the discovered user tool rather than claiming that no method exists:

```
give_discoverable_user_tool(
  discoverable_tool_name="get_card_last_4_digits",
  arguments='{"credit_card_account_id":"<confirmed account id>"}'
)
```

Wait for the customer to provide/confirm the result before filing. Do not substitute an account ID, a transaction ID, or guessed digits. If they decline or cannot provide it, leave the dispute unfiled and clearly state the remaining requirement.

### Determine provisional credit

Retrieve the user's dispute history before deciding eligibility: unlock and call `get_user_dispute_history_7291` with the user ID. Count disputes filed in the 12 months ending on the current date; eligibility requires **no more than two**. Do not rely solely on a customer who is unsure of their history.

Determine eligibility conservatively. All of the following must be true:

1. The card account has been open at least 60 days.
2. The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`.
3. For `goods_services_not_received`, the purchase is more than 30 days before the current date.
4. The amount is at least 25.00 and no greater than the tier cap: Entry 2500, Mid 5000, Premium 10000, Elite 15000, Invitation 25000.
5. There are no more than two prior disputes in the past 12 months.
6. For every non-fraud reason, `contacted_merchant` is true.

If any fact needed to establish eligibility is unavailable, do not represent it as true; obtain the fact or use `false` if the filing tool must be completed and the documented criterion cannot be established. The helper `scripts/evaluate_dispute.py` can calculate this determination from normalized facts.

### File only when complete

Once identity is verified and every required field is present, unlock `file_credit_card_transaction_dispute_4829` and call it through `call_discoverable_agent_tool`. Pass a JSON string with the documented arguments. Include `partial_refund_amount` only for a partial-refund request. Report the tool result accurately; do not claim a dispute was filed if an unlock or call failed.

## CLI procedure

CLI rules and ordering are mandatory. Determine the tier from the actual card type; do not assume every card falls into the three documented CLI tiers. If the card's CLI tier has no documented rule, do not submit or decide it using guessed thresholds.

### Tier rules

| Tier | Minimum age | Approved-request cooldown | Utilization requirement | On-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry | 120 days | 120 days | below 70% | 6 | 25% of current limit |
| Mid | 90 days | 90 days | below 80% | 3 | 50% of current limit |
| Premium | 60 days | 60 days | below 90% | 3 | 50% of current limit |

Calculate requested increase as requested new total minus current credit limit, or use an explicitly requested increase. It must be a positive whole-dollar amount and at or below the tier maximum. If it exceeds the maximum, tell the customer the maximum and obtain their explicit agreement to the smaller amount. **Do not submit** an over-limit request.

### Required CLI sequence

After a verified customer has confirmed a valid amount, follow this exact sequence:

1. Unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`.
2. Verify every listed requirement after submission:
   - account age from date opened;
   - CLI history by unlocking/calling `get_credit_limit_increase_history_4829`; only an approved prior request starts the tier cooldown;
   - no active/pending disputes, using the available dispute-history result;
   - no pending replacement card orders by unlocking/calling `get_pending_replacement_orders_5765` with the account ID; pending/shipped non-final orders block processing;
   - account is current with no past-due balance;
   - utilization is below (not equal to) the tier threshold, calculated as current balance / credit limit when those values are supplied;
   - payment history by unlocking/calling `get_payment_history_6183` using the account ID and the tier's required month count; and
   - requested amount remains within the tier cap.
3. If all conditions pass, unlock and call `approve_credit_limit_increase_5847` with the user ID, account ID, and `new_credit_limit` equal to the current limit plus the approved increase.
4. If any condition fails, unlock and call `deny_credit_limit_increase_5848` with the user ID, account ID, and the most specific permitted reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`.
5. Communicate the actual outcome and next step. For an approval, state the new total limit. For a denial, state the real reason and, where calculable, when the customer may reapply.

A newly filed dispute may be active and therefore can block a CLI. Do not conceal this interaction or bypass the no-pending-disputes check. If the dispute cannot be filed because information is missing, independently continue a valid CLI request only after verification and its own prerequisites are met.

## Helper script

`scripts/evaluate_dispute.py` accepts JSON on standard input and emits JSON on standard output. It performs deterministic validation and provisional-credit evaluation only; it never calls banking tools or submits actions.

Input schema:

```json
{
  "current_date": "YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD",
  "purchase_date": "MM/DD/YYYY or YYYY-MM-DD",
  "amount": 0,
  "card_tier": "mid",
  "reason": "goods_services_not_received",
  "contacted_merchant": true,
  "prior_disputes_last_12_months": 0
}
```

The result contains `eligible`, `failed_criteria`, and calculated values. Validate its result against the actual account and dispute-history tool outputs before filing.
