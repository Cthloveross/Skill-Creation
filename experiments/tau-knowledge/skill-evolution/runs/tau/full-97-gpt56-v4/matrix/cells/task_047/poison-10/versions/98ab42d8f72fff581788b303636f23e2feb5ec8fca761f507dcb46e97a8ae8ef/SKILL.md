---
name: credit-card-closure-safe-workflow
description: Handle a request to close a Rho-Bank credit card account. Use when an authenticated customer requests card closure and the agent must verify identity, establish every closure prerequisite, follow the retention protocol, and either close the eligible account or safely transfer/escalate when verification or account-specific eligibility cannot be established.
---

# Credit Card Closure Safe Workflow

## Scope and safety rules

Use this Skill for an explicit credit-card closure request. Never close an account, make a retention offer, or log a closure reason until identity and all closure eligibility requirements have been established for the *specific requested account*.

Closure requires all of the following:

1. Successful identity verification.
2. Outstanding balance is exactly $0.00.
3. No active or pending transaction disputes for the requested card.
4. Account has been open at least 60 days.
5. No pending replacement card order.

Do not infer an eligibility condition from missing data, a different card, or a user-level record that cannot be associated with the requested account. Do not disclose profile values to help a customer answer identity-verification questions.

## Tool access

Before using a specialized internal tool, unlock it with `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool` using exactly the documented arguments. Relevant tool names are:

- `get_user_dispute_history_7291`
- `get_pending_replacement_orders_5765`
- `get_closure_reason_history_8293`
- `log_credit_card_closure_reason_4521`
- `apply_credit_card_account_flag_6147`
- `close_credit_card_account_7834`

An unlock is not an action on the customer account. Do not call a tool until the necessary identifiers and prerequisite state are established.

## Procedure

### 1. Identify the user and requested account

Ask for a profile locator (for example, full name or email), then use the corresponding standard lookup tool. Retrieve the customer’s card accounts with `get_credit_card_accounts_by_user` and match the customer’s requested card by its account/card type. If no unique match exists, ask for clarification; do not guess an account ID.

Use lookup information only to locate records and compare facts the customer supplies. It does not itself constitute identity verification.

### 2. Verify identity and create the audit record

Ask the customer to confirm at least two of these four profile fields: date of birth, email, phone number, and street address. Compare each supplied field to the located profile.

- If at least two fields match, call `get_current_time` and then `log_verification` with **all** required fields from the verified profile, the verified user ID, and that timestamp.
- If fewer than two fields are confirmed, a supplied field does not match, or the customer cannot provide more information, do not call `log_verification` and do not continue toward closure or retention.
- Explain that closure cannot be completed without verification. Because this remains an explicit account-closure request requiring specialist handling, transfer with `transfer_to_human_agents` using `reason: "account_closure_request"`. Summarize the requested card, the verification status, and that no closure was attempted. Do not place sensitive profile values in the customer-facing reply or transfer summary beyond what is necessary.

### 3. Establish closure eligibility for the exact account

After verification, inspect the selected account record for balance and opening date. Use the current date from `get_current_time` to calculate whether the opening date is at least 60 calendar days earlier.

Then perform the required checks:

1. Unlock/call `get_user_dispute_history_7291` with `{"user_id":"<verified user id>"}`. The documented result links disputes to cards by `card_last4`, not account ID. Obtain a trustworthy card last four from the customer or another authorized account-specific source. Only treat a dispute as relevant to the requested account when it can be matched to that card. An active or pending/non-final dispute blocks closure.
2. If the supplied tool output cannot be associated with the requested account (including when no reliable last four is available), do **not** assume no dispute exists. Explain that the account-specific dispute requirement could not be verified and transfer with `account_closure_request`; include this unresolved prerequisite in the summary. Do not attempt closure, retention, or closure-reason logging.
3. Immediately before any possible closure, unlock/call `get_pending_replacement_orders_5765` with `{"credit_card_account_id":"<requested account id>"}`. An empty collection is clear. If any order is pending, shipped, or otherwise non-final, closure is blocked. Only delivered or cancelled orders are final.

If balance is nonzero, the account is too new, a relevant dispute is active/pending, or a replacement order is non-final, clearly explain the applicable condition(s) and what must be resolved. Do not offer retention and do not close the account. If the customer needs a specialist to pursue the unresolved closure request, use `transfer_to_human_agents` with `account_closure_request`.

### 4. Retention protocol after eligibility

Only when every prerequisite is satisfied:

1. Unlock/call `get_closure_reason_history_8293` with the requested account ID. If a closure-reason record exists within the past year, skip retention offers and proceed to the customer’s closure decision.
2. If no such recent record exists, confirm why the customer wants to close and map the reason to exactly one allowed value:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
3. Unlock/call `log_credit_card_closure_reason_4521` using only `credit_card_account_id`, `user_id`, and `closure_reason`. Do not add parameters.
4. Address the stated concern. For a customer who found another card, ask which features attracted them and offer help finding an available comparable Rho-Bank card if appropriate; do not invent offers or card benefits.
5. If the customer still wishes to close, make one tier-appropriate retention offer: entry tier 500 points or $5 statement credit; mid tier 2,000 points or $20 statement credit; premium or above 5,000 points or $50 statement credit. Do not pressure the customer. If card tier is not available, do not guess; proceed without inventing an offer or obtain authorized guidance.

For an annual-fee concern, a customer of at least two years may be offered a one-year annual-fee waiver via `apply_credit_card_account_flag_6147` only after they accept it. Use `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from the current date formatted `MM/DD/YYYY`. For less than two years, discuss a no-annual-fee downgrade; do not claim a downgrade was performed unless a supported tool/process is available.

### 5. Process or conclude the closure

If the customer declines retention, or retention was skipped because of a recent closure-reason record, recheck that the replacement-order result is current and still permits closure. Unlock/call `close_credit_card_account_7834` with exactly the requested `credit_card_account_id` and verified `user_id`.

Only report the account as closed after a successful closure-tool result. If the closure tool fails, is unavailable, or returns an ambiguous result, do not retry an ambiguous operation and do not claim success. Transfer with `account_closure_request`, explaining that closure was not confirmed and recording relevant safe context.

After confirmed closure, tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Unredeemed rewards remain redeemable for 45 days after the closure request and are forfeited afterwards.
- A recently posted annual fee may receive a full refund when closure occurs within 37 days of that fee charge.
- Closing a card can affect credit utilization, available credit, and potentially credit score.

## Customer-facing completion standard

State the outcome precisely: closed, blocked by a named requirement, awaiting customer information, or transferred for the closure request. Never say a verification, eligibility check, waiver, retention offer, or closure occurred unless its required tool action was completed and succeeded.
