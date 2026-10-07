---
name: credit-limit-increase-workflow
description: Process a verified cardholder's credit-limit-increase request using the required submit-first workflow, tier-specific limits and eligibility checks, formal approval/denial tools, and customer communication. Use when normal banking tools can retrieve the account, CLI history, disputes, replacement orders, and payment history.
---

# Credit-limit increase workflow

## Scope and safety rules

Use this Skill only for a customer who requests an increase on a specific credit-card account.

1. Verify the customer's identity according to the available verification procedure before accessing or changing account information. Obtain confirmation of two of date of birth, email, phone number, and address; retrieve the customer record; then call `log_verification` with all required record fields and the current time. Do not treat information merely displayed in an internal record as customer confirmation.
2. Confirm the customer is the account owner or an authorized account manager.
3. Identify one card account belonging to the verified user. If there is more than one plausible account, ask which account is intended.
4. Obtain a positive whole-dollar increase amount. If the customer instead provides a desired total limit, calculate the increase from the retrieved current limit and confirm it is positive.
5. Never infer a CLI tier from a card product name, marketing description, or typical credit-limit range. The tier must be explicitly present in an authoritative account record or be supplied by an expressly authorized mapping. If no tier is available, explain that the request cannot be safely evaluated, do not submit it, and transfer to the specialized department if it cannot be resolved during the interaction.

The documented tier settings are:

| Tier | Minimum age | Cooldown after an approved request | Utilization must be | Consecutive on-time months | Maximum increase |
|---|---:|---:|---:|---:|---:|
| Entry-tier | 120 days | 120 days | below 70% | 6 | 25% of current limit |
| Mid-tier | 90 days | 90 days | below 80% | 3 | 50% of current limit |
| Premium-tier | 60 days | 60 days | below 90% | 3 | 50% of current limit |

Use `scripts/cli_assessment.py` to calculate dates, percentages, the maximum, and a conservative eligibility report after converting tool results to its JSON input. The script is an aid; its input must come from current authoritative tool results, not customer assumptions.

## Tool preparation

Unlock each discoverable tool before its first use:

- `submit_credit_limit_increase_request_7392`
- `get_credit_limit_increase_history_4829`
- `get_payment_history_6183`
- `get_pending_replacement_orders_5765`
- `get_user_dispute_history_7291`
- `approve_credit_limit_increase_5847`
- `deny_credit_limit_increase_5848`

Use the normal account lookup tools to obtain the account open date, current balance, current limit, and any explicit account-standing/past-due fields. Use `get_current_time` for the verification timestamp and date-based checks.

## Required execution order

### A. Check the requested amount before submitting

With an explicitly established tier and current limit, calculate the maximum permitted increase. Equality with the maximum is allowed; an amount greater than the maximum is not.

If the amount exceeds the maximum, tell the customer the maximum dollar increase and ask whether they want to request that amount or a smaller positive amount. **Do not call the submit tool and do not create a denial** for an over-limit amount. Recalculate after any changed amount.

If the tier, current limit, amount, authority, or identity verification is unavailable, do not submit a CLI request. Resolve it, or use `transfer_to_human_agents` with `specialized_department_required` for a tier/processing issue or `technical_system_error` when a required system record cannot be retrieved.

### B. Submit the valid request before eligibility review

Once the requested amount is within the tier maximum, call:

`submit_credit_limit_increase_request_7392({"credit_card_account_id": account_id, "user_id": user_id, "requested_increase_amount": integer_dollars})`

This submission is required before eligibility checks. Record that a formal request has been created, but do not promise approval.

### C. Check every eligibility criterion

After a successful submission, perform **all** of these checks even if an earlier check fails:

1. **Account age:** Compare the account-open date with current date; eligibility starts on the exact minimum-age day.
2. **Cooldown:** Call `get_credit_limit_increase_history_4829` with the account ID. A denied prior request does not trigger cooldown. Locate the most recent *approved* request and require the full tier cooldown to have elapsed from its submission date. If none was approved, this check passes.
3. **Disputes:** Call `get_user_dispute_history_7291` with the user ID. Any active/non-final dispute (such as `open` or `under_review`) fails the check. Closed disputes do not fail it. Treat an unfamiliar or missing status as unresolved rather than as closed.
4. **Replacement cards:** Call `get_pending_replacement_orders_5765` with the account ID. An empty list passes. Any non-final order (such as `pending` or `shipped`) fails. Only `delivered` and `cancelled` are final.
5. **Good standing:** Verify through an authoritative account status that the account is current and has no past-due amount. Do not infer this solely from total balance, a customer statement, or absence of transactions.
6. **Utilization:** Calculate current balance / current credit limit × 100. It must be strictly below the tier threshold; exactly at the threshold fails.
7. **Payment history:** Call `get_payment_history_6183` with the account ID and exactly the tier-required number of months. Verify the returned months are consecutive and all on time. A customer assertion is not a substitute for this tool check.

If any required response is unavailable, malformed, or ambiguous, do not treat it as a pass and do not approve. Since the submitted request cannot be fully adjudicated, explain that review could not be completed and transfer using `technical_system_error`; do not fabricate a denial reason.

### D. Record the decision

If all checks pass, calculate `new_credit_limit = current_credit_limit + requested_increase_amount` and call:

`approve_credit_limit_increase_5847({"credit_card_account_id": account_id, "user_id": user_id, "new_credit_limit": new_limit})`

If one or more checks fail, call `deny_credit_limit_increase_5848` once. Its `denial_reason` must be one of the allowed enum values. Because the tool accepts only one reason, use the first failed item in this fixed ordering while retaining all check results in the case narrative:

1. `insufficient_account_age`
2. `cooldown_period_active`
3. `pending_disputes`
4. `pending_replacement_card`
5. `past_due_balance`
6. `high_utilization`
7. `insufficient_payment_history`

`requested_amount_exceeds_limit` is only applicable to a previously submitted request if the platform somehow accepted an amount that had already been validated; under this Skill's normal pre-submit process, an over-limit request is not submitted. Use `other` only for a confirmed ineligibility not represented by the listed reasons, never to mask missing verification.

### E. Communicate clearly

For an approval, confirm that the increase was approved and state the new total credit limit. For a denial, state the applicable customer-facing reason and a useful next step: the eligibility date for age/cooldown, resolution of a dispute or replacement, curing past due status, lowering utilization, or building the required on-time payment history. Do not expose internal-only tool details or claim a check passed when it was unresolved.

## Assessment helper

`scripts/cli_assessment.py` reads one JSON object from stdin and emits one JSON report to stdout. It never contacts banking systems or performs actions.

Required inputs are `tier`, `current_limit`, `requested_increase`, `opened_on`, and `now`. Supply optional evidence only after the relevant tool check: `history`, `disputes`, `replacement_orders`, `account_current`, `past_due_amount`, `balance`, and `payment_months`. Missing evidence is reported as `unknown`, not passed. Dates accept ISO dates or timestamps whose first ten characters are an ISO date.

Run it with runtime-provided JSON, for example:

```sh
printf '%s' "$CLI_ASSESSMENT_JSON" | python3 scripts/cli_assessment.py
```

Validate the output before acting: confirm `amount_within_limit` is `true` before submission; after submission, confirm every entry in `checks` is `pass` before approval. A `fail` supports the mapped denial workflow, while `unknown` requires resolving the evidence or transfer.
