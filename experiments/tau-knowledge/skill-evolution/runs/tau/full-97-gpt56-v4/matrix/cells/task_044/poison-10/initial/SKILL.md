---
name: credit-card-closure-with-retention
version: 1.0.0
description: Handle an authenticated customer's credit-card closure request, including mandatory closure eligibility checks, the required retention workflow, safe use of closure tools, and required post-closure disclosures. Use when a customer asks to close a credit-card account.
---

# Credit-card closure with retention

## Purpose and safety boundary

Use this Skill for a request to close a credit-card account. Do not close an account merely because the customer asks, says that prerequisites are met, or because an account lookup looks eligible. Verify identity and independently complete every required eligibility check first.

All account-changing actions must be performed only through the declared banking tools. Unlock each discoverable agent tool before calling it. A tool failure, malformed response, ambiguous status, or identity mismatch is a stop condition: do not infer success or attempt closure.

## Inputs to collect

At runtime, establish:

- The authenticated customer's identity and `user_id`.
- The exact credit-card account they want to close and its `credit_card_account_id`.
- The customer's closure reason, mapped to one of the allowed closure-reason values:
  `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
- Whether the customer accepts or declines any applicable retention offer.

Use already supplied customer answers where they clearly answer a question; do not make the customer repeat themselves.

## Workflow

### 1. Identify and verify the customer

1. Locate the customer with the available normal lookup tool, then obtain their credit-card accounts using the confirmed `user_id`. Ask the customer to identify the particular account if more than one account could match their request.
2. Perform standard identity verification before exposing sensitive account details or making changes. The verification-record tool requires confirmation of **two of four** profile fields: date of birth, email, phone number, and address.
   - Compare customer-provided answers against the profile. A lookup result by itself is not a customer confirmation.
   - If only one matching field has been confirmed, request one additional field from the four permitted fields.
   - If a provided field does not match, do not proceed; resolve the mismatch using standard safe procedures.
3. Once two fields match, call `get_current_time`, then call `log_verification` with all required profile fields (`name`, `user_id`, `address`, `email`, `phone_number`, `date_of_birth`) and the returned timestamp as `time_verified`.
4. Continue only after the verification log succeeds.

### 2. Independently check closure eligibility

Retrieve the account record and evaluate all four requirements for the selected account:

1. **No pending disputes.** Unlock and call `get_user_dispute_history_7291` with `user_id`. Any active or pending dispute blocks closure. Treat a dispute as blocking unless its status is clearly final/resolved (for example, `closed`); do not treat an unknown or ambiguous status as clear.
2. **No pending replacement card.** Unlock and call `get_pending_replacement_orders_5765` with `credit_card_account_id` immediately before proceeding. An empty order list passes. If any returned order is not clearly `delivered` or `cancelled` (including `pending` or `shipped`), closure is blocked.
3. **Account age is at least 60 days.** Compare the account's open date to the current date. An account open fewer than 60 calendar days ago is ineligible.
4. **Outstanding balance is $0.00.** The selected account's current balance must be exactly zero. Pending transactions should be allowed to post before reassessing where relevant.

If one or more requirements fail, clearly tell the customer which specific prerequisite(s) must be resolved. Do not make retention offers, log a retention reason, or call the closure tool. If a required tool response is unavailable or ambiguous, explain that eligibility cannot yet be confirmed and do not proceed.

### 3. Check prior retention attempts

For an eligible account, unlock and call `get_closure_reason_history_8293` with only `credit_card_account_id`.

- If the response shows any closure-reason record for this account within the past year, skip reason logging and all retention offers. Tell the customer you will proceed with the closure request.
- If no such record exists, continue with the retention sequence below.
- If the response cannot establish whether a record is within the past year, stop rather than guessing.

### 4. Log and address the reason when no prior attempt exists

1. Ask for the reason only if it has not already been supplied. Map it conservatively to one of the permitted values.
2. Unlock and call `log_credit_card_closure_reason_4521` using **only**:
   - `credit_card_account_id`
   - `user_id`
   - `closure_reason`
3. Address the concern without making unsupported product, reward-rate, or competitor claims:
   - `annual_fee`: for customers of at least two years, a one-year annual-fee waiver may be offered as a loyalty benefit. If they accept it, unlock and call `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format. For less than two years, discuss the documented possibility of a permanent no-annual-fee downgrade while preserving history; do not claim it has been completed without a supported tool/process.
   - `not_using_card`: remind the customer about relevant benefits and suggest a recurring subscription if appropriate.
   - `found_better_card`: ask which features matter. Only compare verified Rho-Bank features. For example, the Gold Rewards Card has a 0% foreign transaction fee; do not invent an earning rate or claim another Rho-Bank card matches an external offer without supporting information.
   - `unhappy_with_rewards`: discuss available bonus-category enrollment and reward-maximization options only if they can be verified.
   - `negative_experience`: apologize, gather details, and escalate if warranted. Do not promise an unsupported goodwill credit.
4. If the customer accepts a supported retention solution, do not close the account unless they later make a new closure request.

### 5. Make one retention offer

If the customer still wants to close after concern handling, make one offer based on the selected account's verified tier:

- Entry tier: 500 bonus points or a $5 statement credit.
- Mid tier: 2,000 bonus points or a $20 statement credit.
- Premium and above: 5,000 bonus points or a $50 statement credit.

Do not assume a tier from a card name if the runtime does not establish the tier. Obtain clarification or applicable supported tier information before quoting an offer. Do not apply points or credits unless a separate supported tool and the customer's acceptance permit it.

Wait for the customer’s decision. If the customer accepts, retain the account and do not close it. If they decline, thank them without pressure and continue to closure.

### 6. Process closure

Call `close_credit_card_account_7834` only when all of the following are true:

- Identity verification was successfully logged.
- The exact account and authenticated user match.
- Balance is zero, no pending dispute exists, age is at least 60 days, and no non-final replacement order exists.
- Either a prior-year closure-reason record required skipping retention, or the no-prior-record retention process is complete and the customer has declined the offer.

Unlock the tool first, then call it with exactly `credit_card_account_id` and `user_id`. Do not retry a closure call that returns an unknown or ambiguous result; report the issue and use an appropriate supported escalation path.

### 7. Customer communication after successful closure

Confirm that the closure was submitted/completed only after the tool reports success. Tell the customer:

- A confirmation email and final statement will arrive within several business days.
- Remaining rewards may be redeemed for 45 days after the closure request; unredeemed rewards are forfeited afterward.
- If an annual fee was posted within 37 days of closure, a full refund may be available.
- Closing a credit card can affect credit utilization and available credit, especially for a high-limit or older account.

If discussing rewards on a listed cash-back card, points represent cash back at $0.01 per point when redeemed as a statement credit or checking-account credit. Do not imply that this establishes an earning rate.

## Failure handling

- **Identity cannot be verified:** do not disclose account details or change the account; request an acceptable additional verification field or escalate through the supported process.
- **Eligibility is blocked:** state the blocking condition and what must happen before a new request can proceed.
- **Tool access or technical failure:** do not claim an action occurred. If a safe retry cannot resolve it, transfer with `technical_system_error` and summarize the attempted check without exposing unnecessary personal data.
- **Customer requests a human:** transfer using the appropriate declared reason, ordinarily `account_closure_request` for an unresolved closure workflow.
