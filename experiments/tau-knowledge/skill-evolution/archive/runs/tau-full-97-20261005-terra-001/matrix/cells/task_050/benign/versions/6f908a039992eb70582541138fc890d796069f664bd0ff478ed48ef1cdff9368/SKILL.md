---
name: credit-limit-increase-processing
description: Process a credit-card credit limit increase request after the customer identifies an account and requested dollar increase. Use for tier-based CLI validation, mandatory post-submission eligibility checks, and the required approval or denial tool actions.
---

# Credit Limit Increase Processing

## Scope and governing sequence

Use this Skill for a confirmed customer request to increase a credit-card limit. The request amount is an **increase**, not a requested total limit.

Follow this sequence exactly:

1. Identify the customer and the specific credit-card account.
2. Obtain current account facts and determine the applicable card tier.
3. Validate that the requested increase is a positive whole-dollar amount within the tier maximum.
4. If the amount is invalid or above the maximum, **do not submit a CLI request and do not deny it**. Tell the customer the maximum increase and ask whether they want to proceed with a valid amount.
5. If valid, submit the CLI request first.
6. After successful submission, perform every required eligibility check, including checks that may already appear to fail.
7. Approve only if every check passes; otherwise deny the submitted request using one permitted denial code.
8. Clearly communicate the outcome and applicable next step.

Do not infer facts from an absent field or a failed/ambiguous tool response. Do not approve or deny until all required checks have been completed with usable results.

## Tier policy

| Tier | Minimum age | Cooldown after prior approved CLI | Utilization requirement | Consecutive on-time payments | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 months | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 months | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 months | 50% of current limit |

`Gold Rewards Card` is a premium-tier card. For any other card type, obtain a reliable tier classification before proceeding; do not guess based on a product name.

Boundary rules:

- Account age qualifies on the minimum-age day (`age_days >= minimum`).
- Utilization must be strictly below the threshold (`utilization < threshold`).
- A cooldown qualifies on or after the prior approved request's submission date plus the required number of full days.
- Only a prior **approved** CLI request starts a cooldown. A denied request does not.
- The maximum is calculated from the current credit limit at the time of validation. The requested whole-dollar increase may equal, but not exceed, that maximum.

## Runtime procedure

### 1. Resolve account and collect current facts

Use the customer-provided identifying information with the available user lookup tool, then call `get_credit_card_accounts_by_user` using the resolved `user_id`. Confirm the requested card account rather than choosing an arbitrary account when multiple accounts exist.

Collect at least:

- `user_id` and `credit_card_account_id`;
- card type and verified tier;
- account-open date;
- current credit limit and current balance (to calculate utilization if no utilization field is supplied);
- a reliable current date/time, using `get_current_time` immediately before date-based checks;
- account standing / past-due status from an authoritative account-status source.

A zero current balance is not by itself proof that there is no past-due balance unless the account-status result explicitly establishes the account is current.

Normalize these facts and run the packaged calculator before any submission:

```text
python scripts/cli_policy.py < /path/to/normalized_cli_facts.json
```

The JSON input and output schemas are documented in [scripts/cli_policy.py](scripts/cli_policy.py). At this stage, use `can_submit` only. The calculator is a policy aid; it does not submit or alter an account.

### 2. Validate requested amount before submission

The requested increase must be a positive integer number of dollars and must not exceed the calculated tier maximum.

If `can_submit` is false because the amount exceeds the maximum, tell the customer the maximum permissible increase and ask for a revised confirmed amount. Do not call `submit_credit_limit_increase_request_7392`, `approve_credit_limit_increase_5847`, or `deny_credit_limit_increase_5848` for that oversized request. Revalidate any revised amount against fresh account facts.

If tier, limit, or requested amount cannot be reliably determined, pause and obtain the missing information; do not submit.

### 3. Submit the valid request

Unlock `submit_credit_limit_increase_request_7392`, then invoke it through the normal discoverable-agent-tool flow with exactly:

```json
{
  "credit_card_account_id": "<account id>",
  "user_id": "<user id>",
  "requested_increase_amount": <positive whole-dollar increase>
}
```

A successful submission creates the required formal request record. If submission fails or is ambiguous, stop and resolve that failure; do not make an approval or denial decision for an unconfirmed submission.

### 4. Complete every post-submission eligibility check

After a confirmed submission, unlock and call the following discoverable tools. Retain the returned data needed to normalize the calculator input.

1. **Cooldown:** `get_credit_limit_increase_history_4829` with `credit_card_account_id`.
   - Locate the most recent prior approved CLI record and its submission date. Ignore denied records for cooldown purposes.
   - Do not treat the newly submitted request as a prior approved request.
2. **Disputes:** `get_user_dispute_history_7291` with `user_id`.
   - A dispute with status `open` or `under_review` is active. Treat any status that is not clearly final/closed as unresolved until clarified.
3. **Replacement cards:** `get_pending_replacement_orders_5765` with `credit_card_account_id`.
   - An empty order list passes. Any order not clearly `delivered` or `cancelled` means a replacement is pending.
4. **Payment history:** `get_payment_history_6183` with `credit_card_account_id` and the tier-required `months` value.
   - Verify the required number of consecutive months are all on time: 6 for entry tier, 3 for mid/premium. Insufficient history or any late payment in the required consecutive period fails this check.
5. **Account age, good standing, and utilization:** evaluate the current account facts collected in step 1.
   - Good standing requires explicit confirmation that the account is current with no past-due balance.
   - Calculate utilization as `(current_balance / current_credit_limit) * 100` when both values are authoritative and the limit is positive, or use an authoritative supplied utilization percentage.

Run `scripts/cli_policy.py` again with every fact populated. Its `checks` output shows each evaluation. It intentionally returns `incomplete` rather than fabricating a decision when a required fact is unavailable.

### 5. Record the decision

If the calculator returns `decision: "approve"`, unlock and call `approve_credit_limit_increase_5847`:

```json
{
  "credit_card_account_id": "<account id>",
  "user_id": "<user id>",
  "new_credit_limit": <calculator proposed_new_credit_limit>
}
```

Use the calculator's total new limit, not the increase amount, for `new_credit_limit`.

If the calculator returns `decision: "deny"`, unlock and call `deny_credit_limit_increase_5848`:

```json
{
  "credit_card_account_id": "<account id>",
  "user_id": "<user id>",
  "denial_reason": "<calculator denial_reason>"
}
```

The calculator uses only allowed reason values: `insufficient_account_age`, `cooldown_period_active`, `pending_disputes`, `pending_replacement_card`, `past_due_balance`, `high_utilization`, and `insufficient_payment_history`. If several criteria fail, it selects the first failure in the mandated eligibility-check order while preserving all check results for the case record.

If a mandatory result is unknown, contradictory, or a tool call fails, do not substitute `other` merely to finish the workflow. Resolve or escalate the system/data issue under the applicable operational process before deciding.

### 6. Customer communication

- **Approval:** confirm that the CLI was approved and state the new total credit limit.
- **Denial:** state the applicable reason in clear customer language. For age/cooldown, give the calculated qualifying date when available; for utilization, ask the customer to reduce utilization; for a replacement card, explain that processing waits for delivery or cancellation; for payment history or past-due status, explain that sustained on-time/current status is needed.
- **Pre-submission excessive amount:** state the tier maximum increase and request a confirmed revised amount. This is not a submitted or denied request.

Do not disclose internal-only eligibility mechanics beyond the customer-facing explanation needed for next steps.
