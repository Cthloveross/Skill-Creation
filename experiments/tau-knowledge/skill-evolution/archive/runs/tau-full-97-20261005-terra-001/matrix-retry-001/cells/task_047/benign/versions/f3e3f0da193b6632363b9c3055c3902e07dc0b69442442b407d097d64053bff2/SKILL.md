---
name: credit-card-account-closure
version: 1.1.0
description: Safely handle a verified customer's credit-card closure request, including eligibility checks, mandatory retention handling, requested human transfers, and the final closure action. Use for any request to close a credit card account when internal account and discoverable banking tools are available.
---

# Credit Card Account Closure

Use this Skill to guide a closure request from identification through an approved closure or requested handoff. Do not close an account based only on a name, account type, or account lookup: complete standard identity verification first.

## Runtime inputs and helper output

At runtime, obtain the authenticated user's identity information, credit-card accounts, current date/time, and results from required banking tools. Never reuse account IDs, personal data, dates, balances, or tool results from a prior case.

`scripts/assess_closure.py` accepts a structured, already-observed case snapshot on stdin and emits a deterministic eligibility assessment on stdout. It makes no banking calls and never closes an account.

Example input:

```json
{"today":"YYYY-MM-DD","identity_verified":true,"account":{"account_id":"<account-id>","user_id":"<user-id>","date_of_account_open":"YYYY-MM-DD","current_balance":"0.00"},"disputes":[],"replacement_orders":[],"closure_reason_history":[]}
```

Validate `valid: true` before relying on the result. A `blocked: true` result means do not make retention offers or call the closure tool. Missing, malformed, stale, or ambiguous data is a blocker requiring a reliable current result.

## Procedure

### 1. Identify the account and verify identity

1. If needed, ask for a name or email, retrieve the user record, and retrieve that user's credit-card accounts. Confirm the intended account when more than one account could match.
2. Verify identity under standard procedures by confirming at least two of the stored date of birth, email, phone number, and address fields.
3. After successful verification, obtain the current timestamp and call `log_verification` with the authenticated `user_id`, timestamp, and all required stored identity fields. A name or account number alone is not verification.
4. Confirm that the target account belongs to the verified user and use its account-level identifier.

If identity cannot be verified, do not disclose account details or take closure actions. Request usable verification information or use the applicable human-transfer process.

### 2. Check every closure condition before retention

Perform and resolve these checks before any retention discussion or offer:

1. **Disputes:** unlock and call `get_user_dispute_history_7291` with `user_id`. Any active or pending dispute blocks closure. Treat statuses such as `open`, `pending`, `under_review`, or `active` as blocking. A missing or unclear status also blocks progress.
2. **Replacement cards:** unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id`. An empty order list passes. If any order is not clearly `delivered` or `cancelled`, closure is blocked.
3. **Account age:** calculate age from the account opening date; it must be at least 60 days.
4. **Balance:** the outstanding balance must be exactly $0.00.

If any requirement fails or is unknown, explain the specific condition to resolve and stop. Do not attempt retention offers or closure. Record check outcomes when that capability is available.

### 3. Mandatory retention decision sequence

Only after all closure conditions pass:

1. Unlock and call `get_closure_reason_history_8293` with the target `credit_card_account_id`.
2. If there is a record for that account within the past year, skip all retention offers. State that the closure request can proceed subject to the final replacement-order recheck, then continue to Step 4.
3. Otherwise, identify the reason and unlock and call `log_credit_card_closure_reason_4521` using **exactly** these arguments: `credit_card_account_id`, `user_id`, and a supported `closure_reason`. Supported values are `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, and `other`.
4. Address the stated concern accurately:
   - For `found_better_card`, ask which benefits matter most. Discuss only relevant, documented benefits of the current card or an available Rho-Bank alternative; do not claim that an unsupported feature exists.
   - For annual-fee concerns, customers of at least two years may receive a one-year waiver using `apply_credit_card_account_flag_6147` with the documented arguments. For shorter tenure, offer the documented same-category no-annual-fee downgrade if desired.
   - For other reasons, use the documented tailored discussion and escalate a service complaint where warranted.
5. **Retention-offer hard gate:** If there is no prior-year closure-reason record and the customer still wants to close after the concern discussion, make exactly one offer for the actual card tier **before** any closure processing, escalation, or human transfer. This is required even when the available benefits do not match the competing card and even if the customer asks for a specialist after explaining the competing card.
   - Entry tier: offer **500 bonus points or a $5 statement credit**.
   - Mid tier: offer **2,000 bonus points or a $20 statement credit**.
   - Premium and above: offer **5,000 bonus points or a $50 statement credit**.

   State the applicable amount explicitly in the customer-facing message. For example, for a mid-tier card: “Before we proceed, I can offer **2,000 bonus points** if you keep the account open. Would you like to accept that offer?” Alternatively: “I can offer a **$20 statement credit** if you keep the account open.” A verbal retention offer does not require inventing an application tool or claiming that points or credit have already been applied.
6. If the customer accepts a documented alternative, complete only the applicable documented action and do not close the account. If they decline the retention offer, respect the decision without pressure and continue. If history required skipping offers, continue without one.
7. If the customer requests a human or specialist at any point after the mandatory applicable offer has been made, call `transfer_to_human_agents` with the most applicable permitted reason and a concise summary. Confirm transfer only after the tool reports success. A requested transfer does not replace the required offer when the offer is otherwise due.

### 4. Close and communicate

1. Confirm that the customer still wants the specified account closed.
2. Immediately before closure, run a fresh `get_pending_replacement_orders_5765` check for the target account. Stop if it now blocks closure.
3. Unlock and call `close_credit_card_account_7834` with the verified `credit_card_account_id` and `user_id` only. Do not claim closure succeeded unless the tool reports success.
4. On successful closure, explain that a confirmation email and final statement arrive within several business days. Explain that remaining rewards may be redeemed for 45 days after the closure request and are then forfeited. If the annual fee posted within 37 days, advise that a full refund may apply; otherwise do not promise a refund.

## Error handling

- If a specialized tool cannot be unlocked, returns an access or technical error, or returns incomplete or ambiguous data, do not infer that its check passed. Retry only when appropriate; otherwise transfer or escalate with a concise summary.
- Do not use dispute results for a different user or replacement-order results for a different account.
- If the customer changes the target account, reconfirm it and repeat account-specific checks.
- Never invoke the closure tool before identity verification, all eligibility checks, prior-retention-history review, required reason logging and offer decision handling, and the final replacement-order check.
