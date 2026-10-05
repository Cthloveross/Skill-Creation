---
name: credit-card-dispute-and-cli
version: 1.0.0
description: Process a verified customer's credit-card transaction dispute and credit-limit-increase (CLI) request together. Use when the request needs formal dispute filing, provisional-credit evaluation, and/or a tier-based CLI decision using internal banking tools.
---

# Credit Card Dispute and CLI Processing

Use this Skill for a customer who requests a credit-card transaction dispute, a CLI, or both. It separates non-mutating fact collection from irreversible actions and preserves the mandatory CLI submission/decision order.

## Guardrails

- Verify identity before account-specific actions. Obtain confirmation of at least two of date of birth, email, phone number, and address; retrieve the customer profile; compare the confirmed values; then call `get_current_time` and `log_verification` with the complete retrieved profile and timestamp. Do not treat a lookup alone as customer verification.
- Match the selected card account to the requested card product and the disputed transaction to that account, merchant, amount, and date. If multiple candidates remain, ask the customer to choose.
- Do not invent missing facts, infer a tool result from silence, or use a stale/ambiguous tool response as a passing check.
- Use `unlock_discoverable_agent_tool` before the first call to every named discoverable agent tool, then call it with `call_discoverable_agent_tool` and a JSON-string `arguments` value.
- Scripts in this package only calculate and validate. They do not invoke banking tools, submit requests, or make account changes.

## Recommended sequencing when both requests are present

A filed dispute may itself be an active dispute for the CLI requirement. Therefore:

1. Verify identity and resolve the user, card account, and transaction.
2. Collect dispute facts and run only read-only dispute checks (last four digits and dispute history). Do **not** file the dispute yet.
3. Validate the requested CLI amount. If valid, complete the entire CLI workflow, including its decision, before filing the dispute.
4. File the dispute after the CLI has reached an approval or denial decision.

If the requested CLI amount is invalid, do not submit or deny that CLI request; explain the allowed maximum and ask whether the customer wants a valid amount. The dispute may proceed independently once its required information is complete.

If a required CLI check cannot be completed after submission, do not approve or deny based on an assumption. Resolve the unavailable/ambiguous check or route it under the applicable operational procedure before filing a new dispute that could affect the pending CLI assessment.

## Read-only collection

After verification, obtain the customer and account facts with the standard account and transaction lookup tools available in the runtime. Collect, normalize, and retain:

- User ID, full name, registered phone, email, and address.
- Credit-card account ID, card product/tier, open date, current balance, current limit, and past-due amount.
- The exact transaction ID, transaction date, merchant, amount, and account ID.
- The current time for date-based calculations.

For dispute processing, unlock and call:

- `get_card_last_4_digits` with `credit_card_account_id`.
- `get_user_dispute_history_7291` with `user_id`.

Use every returned dispute filed in the preceding rolling 12 months for the provisional-credit dispute-count test, regardless of outcome. Also inspect the history for currently open/under-review disputes when performing the CLI no-active-disputes check. If account-specific status cannot be determined from the available result, treat that CLI check as unresolved rather than clear.

## Dispute workflow

Collect every required filing field before submitting:

1. `transaction_id` from the matched transaction.
2. `card_action`: use `keep_active` unless the customer asks to cancel/replace the card; use `cancel_and_reissue` only when replacement/cancellation is requested.
3. `card_last_4_digits` from `get_card_last_4_digits`.
4. Registered `full_name`, `user_id`, `phone`, `email`, and `address`.
5. `contacted_merchant`: an attempted contact counts as `true`, even if the merchant did not respond. Ask if this is not clear.
6. `purchase_date` and `issue_noticed_date`, formatted `MM/DD/YYYY`.
7. An exact allowed `dispute_reason`:
   `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, or `refund_never_processed`.
8. An exact allowed `resolution_requested`: `full_refund`, `partial_refund`, or `reversal_of_charge`. Include numeric `partial_refund_amount` only for `partial_refund`.
9. `eligible_for_provisional_credit`, determined before filing.

### Provisional-credit decision

All conditions must pass:

- Account is open at least 60 days.
- Reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received` where the purchase is **more than** 30 days old.
- Transaction is at least $25 and does not exceed the tier cap: Entry $2,500; Mid $5,000; Premium $10,000; Elite $15,000; Invitation $25,000.
- No more than two prior disputes were filed in the rolling previous 12 months.
- For every non-fraud reason, the customer contacted the merchant.

Pass `false` when a known criterion fails. If a required fact is missing or the history cannot be checked, do not guess; obtain it before filing.

When all fields are ready, unlock `file_credit_card_transaction_dispute_4829`, then call it with the complete JSON payload. Omit `partial_refund_amount` unless it is required. Report that the dispute was filed only after a successful tool result; explain that any provisional credit is temporary pending investigation.

## CLI workflow

### Tier policy

Normalize product tier to `entry`, `mid`, or `premium` for CLI policy:

| Tier | Minimum age | Cooldown after latest approved submission | Utilization requirement | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| entry | 120 days | 120 days | below 70% | 6 | 25% of current limit |
| mid | 90 days | 90 days | below 80% | 3 | 50% of current limit |
| premium | 60 days | 60 days | below 90% | 3 | 50% of current limit |

Calculate the requested increase as either the stated increase or requested new total minus current limit. It must be a positive whole-dollar amount because the submission tool requires an integer. If both forms are supplied, they must agree. The requested increase may equal, but not exceed, the tier maximum.

### Mandatory action order

1. **Before submission:** Validate the amount against the tier maximum. If it exceeds the maximum, do not submit and do not use the denial tool. State the maximum permitted increase and ask for a revised amount.
2. **Submit:** For a valid amount, unlock and call `submit_credit_limit_increase_request_7392` with `credit_card_account_id`, `user_id`, and integer `requested_increase_amount`. Submission must occur before eligibility evaluation and decision.
3. **Check every criterion after submission:**
   - Account age from the open date.
   - Cooldown using `get_credit_limit_increase_history_4829` with the account ID. Only a most recent **approved** request starts cooldown; denied requests do not. Count from its submission date and require the full tier interval.
   - Active/pending disputes using the retrieved dispute history or an authoritative account-specific result.
   - Replacement activity: unlock and call `get_pending_replacement_orders_5765` with the account ID. Any order not clearly `delivered` or `cancelled` blocks the CLI.
   - Good standing: no past-due balance.
   - Utilization: `current_balance / current_credit_limit * 100`, strictly below the tier threshold.
   - Payment history: unlock and call `get_payment_history_6183` with `credit_card_account_id` and the tier-required month count. Confirm all requested consecutive months are on time.
4. **Decide only after all checks are completed:**
   - If all pass, unlock and call `approve_credit_limit_increase_5847` with the account ID, user ID, and `new_credit_limit = current_credit_limit + requested_increase_amount` as a float.
   - If one or more known criteria fail and all checks were completed, unlock and call `deny_credit_limit_increase_5848`. Use one allowed reason: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, `insufficient_payment_history`, `requested_amount_exceeds_limit`, or `other`. Record all failures in case notes even though the tool accepts one reason. Prefer the policy-check order above when a single reason must be selected.

For a cooldown denial, provide the next eligible date based on the latest approved request submission date plus the tier cooldown. For other denials, state the concrete condition that must change. Confirm the resulting new limit only after a successful approval response.

## Calculator helper

`scripts/evaluate_card_requests.py` accepts normalized runtime data on stdin and emits a JSON assessment on stdout. It validates the CLI pre-submission amount, evaluates completed CLI checks, and evaluates provisional-credit eligibility. It never substitutes unknown data with a pass.

Run it with a real runtime JSON file:

```text
python3 scripts/evaluate_card_requests.py < /path/to/runtime_case.json
```

Input schema (all dates are `YYYY-MM-DD`, `MM/DD/YYYY`, or ISO timestamp strings):

```text
{
  "now": "required current date/time",
  "card": {
    "account_open_date": "date",
    "current_credit_limit": "number",
    "current_balance": "number",
    "past_due_amount": "number"
  },
  "cli": {
    "tier": "entry|mid|premium",
    "requested_increase_amount": "optional number",
    "requested_new_limit": "optional number",
    "history_checked": "boolean",
    "last_approved_submission_date": "date or null",
    "active_disputes_checked": "boolean",
    "active_dispute_count": "integer",
    "replacement_checked": "boolean",
    "replacement_orders": [{"status": "string"}],
    "payment_history_checked": "boolean",
    "consecutive_on_time_months": "integer"
  },
  "dispute": {
    "card_tier": "entry|mid|premium|elite|invitation",
    "transaction_amount": "number",
    "reason": "allowed dispute reason",
    "purchase_date": "date",
    "contacted_merchant": "boolean",
    "history_checked": "boolean",
    "prior_dispute_dates": ["date"]
  }
}
```

`history_checked`, `active_disputes_checked`, `replacement_checked`, and `payment_history_checked` distinguish a known empty result from an unperformed check. Review `unknown_checks` before any final action. Use `cli.next_eligible_date` only for a known cooldown failure.

## Completion communication

Give separate, clear outcomes for the two requests. State a successful CLI submission/approval/denial only after its tool response, and state a dispute filing only after its filing response. Do not promise a dispute outcome. Keep customer-facing explanations limited to the applicable condition and next step; do not expose internal eligibility mechanics beyond what is needed to explain the result.
