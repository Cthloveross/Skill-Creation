---
name: atm-multiple-debit-card-declines
version: 1.0.0
description: Investigate one or more debit-card ATM declines safely, including cards belonging to a verified customer and a teen/dependent. Use when a customer reports a generic ATM decline, needs cash urgently, does not know the decline code, or asks about a withdrawal-limit increase.
---

# ATM Multiple Debit-Card Decline Investigation

Use this Skill to diagnose ATM cash-withdrawal declines without assuming that a decline is caused by a card limit. It is especially applicable when multiple cards fail at one ATM, since the ATM/operator or a temporary network issue may be relevant, but each card still needs its own account-and-card review.

## Safety and authorization boundaries

1. Identify the affected adult customer using a user ID, email, or full name. Do not treat a database lookup as identity verification.
2. Before revealing nonpublic account/card/transaction details or taking an account action, obtain and confirm two of four identity fields (date of birth, email, phone number, address). Retrieve the customer record, obtain the two confirmations from the customer, get the current timestamp, and call `log_verification` with all required record fields.
3. For another adult's card, do not investigate, disclose details, or act without that cardholder's verified authorization.
4. For a teen/dependent account, establish the relationship from the user records, but do not assume a parent may discuss or change the teen's account merely from the relationship. Ask whether the teen is present and willing to authorize discussion. If that authorization is absent, limit the response to general published information and do not retrieve or disclose the teen's account/card/transaction details or take an action on it.
5. Do not disclose internal fraud codes, fraud-alert rationale, security holds, or information that could assist a fraudster. Follow the prescribed customer-facing wording for bank-initiated security flags.
6. Do not submit a limit increase, freeze/unfreeze, PIN action, closure, or any other modifying action merely because it might help. Explain the option, collect an explicit request and the desired amount, verify every prerequisite, then use only the appropriate declared banking tool.
7. Never repeat an operation that a banking tool reports as `UNKNOWN`. Explain that the result needs review/escalation instead.

## Gather the incident facts

Ask or confirm, without delaying an urgent investigation unnecessarily:

- Which card/account each attempt used, requested withdrawal amount, whether a PIN was entered, whether an exact decline code/message appeared, and whether any fee/cash-back request was involved.
- Whether all attempts were at the same terminal, its operator/bank, city/location, and whether another terminal has been tried.
- Whether the customer recognizes recent ATM/card activity and whether the card is physically present/damaged.
- For a teen card, obtain the teen's authorization before account-specific investigation.

A generic “transaction declined” is not a confirmed decline code. Do not present a specific code as fact.

## Look up the verified customer's affected accounts

Unlock and use these internal tools as needed:

- `get_all_user_accounts_by_user_id_3847` with `user_id`
- `get_debit_cards_by_account_id_7823` with each checking `account_id`
- `get_bank_account_transactions_9173` with an affected checking `account_id`

Process only checking accounts for debit cards. Match the customer’s card description/last four digits to the returned card where possible; if it cannot be matched, say so and do not perform a card-specific change.

For each affected card, record the linked account, account class, account status, account opening date, balance, card status, card issue reason, date issued, daily ATM limit, and any returned security/restriction fields. Then retrieve recent transactions for each affected checking account. Review pending debits, recent ATM withdrawals, and overdraft-fee entries, including their dates and statuses. Do not equate a posted balance with available funds.

If a tool returns no record, missing fields, or an unsupported response, state the limitation rather than inventing a value. Continue with the facts available and use the safe fallback advice below.

## Diagnose each card separately

For an unspecified/generic debit-card decline, check in this order:

1. **Card status**
   - `FROZEN`: ask whether the verified owner wants it unfrozen. Only unfreeze after confirming the linked checking account is `OPEN` and following the unfreeze procedure.
   - `CLOSED`: explain it is no longer active; identify any active/pending replacement where authorized.
   - `PENDING`: explain that it is not activated and follow the correct activation procedure only if the customer requests it and has the physical-card details.
   - `ACTIVE`: continue.
2. **Linked account status**
   - If not `OPEN`, do not disclose the specific reason for `SUSPENDED` or `RESTRICTED`. Say: “Your account has a restriction that is preventing transactions. Please visit a branch or call our dedicated account services line at 1-800-RHO-ACCT for assistance.”
3. **Fraud alert**
   - A customer-initiated alert may be cleared only after the customer verifies recent transactions and confirms they are legitimate.
   - A bank-initiated alert must not be cleared. Say: “I see there's a security flag on your account that requires additional review. I'm transferring you to our security team.” Then transfer using `transfer_to_human_agents` with `fraud_or_security_concern`.
4. **Velocity block**
   - If reported as true, explain the temporary block normally lifts after 30 minutes. Offer early lifting only after identity verification and only through a supported procedure/tool.

Also evaluate the withdrawal request against the card’s daily ATM limit and ATM amount already used, if those fields are returned. Compute `remaining = max(0, daily_atm_limit - daily_atm_used)`. Explain the limit, used amount, and remaining amount clearly. A non-Rho ATM may impose an independent lower limit that Rho-Bank cannot override.

For Light Green/teen accounts, do not promise that a limit can be removed. Published guidance says daily ATM withdrawals are limited to $150 and safeguards for a minor cannot be removed. Parental controls may also limit transaction types; do not alter them without the primary account holder's authorization and the applicable supported process.

## Balance and pending-activity checks

For a possible insufficient-funds decline, review the current balance and recent activity. Explain that authorization holds and pending debits can reduce available funds before posting. If the balance appears sufficient, ask about recent hotel, gas, restaurant, rental, or other authorization holds, and identify pending transactions returned by the history tool. Check any returned POS-overdraft setting; do not claim it applies to an ATM unless the returned data or policy supports that conclusion.

If funds are genuinely insufficient, state only the authorized account’s relevant balance and offer a smaller withdrawal, funding the account, or a transfer if the customer requests and a supported procedure exists.

## Same-ATM pattern and technical fallback

When multiple otherwise eligible cards declined at exactly one unknown or third-party ATM, do not conclude that all accounts are defective. If the records show no card/account/security/balance/limit blocker, explain that the terminal, its operator limit, or a temporary network issue may be involved. Ask the customer to try a different ATM/terminal, or retry after a few minutes; if a temporary system issue persists, advise retrying in 10–15 minutes. Do not promise that a different terminal will approve a transaction.

If an ATM request is above the verified remaining limit, recommend retrying for an amount no greater than that remaining limit at a different/known ATM if needed. If a third-party ATM may have a lower limit, advise a smaller request or a Rho-Bank ATM; do not claim its limit is known.

## Temporary ATM-limit increase

Offer this only for an adult card when it is a potentially appropriate solution, the customer explicitly asks for it, and the request is not barred by account class/policy. Before submission, verify all of the following from current records:

- linked checking account is `OPEN`;
- account has been open at least 60 days;
- no overdraft-fee transaction in the past 30 days;
- card status is `ACTIVE`;
- no other temporary increase was granted for that card in the previous 24 hours;
- requested new ATM limit is no more than 150% of the current limit.

Explain that an approved temporary increase lasts 24 hours and cannot override another bank’s ATM limit. Obtain the exact requested new limit and explicit approval. Unlock `request_temporary_debit_card_limit_increase_8374` and call it with `card_id`, `limit_type: "atm"`, and `new_limit` only after every condition is met. Report the tool result faithfully. If any condition fails, explain the specific non-sensitive eligibility blocker and offer the smaller-withdrawal/different-ATM alternatives.

## Closing response and validation

Give a concise per-card outcome: whether it was investigated, its confirmed blocker (if any), the safe next action, and any action actually completed. Clearly separate confirmed findings from possibilities. For an unverified or unauthorized dependent card, explicitly say that no account-specific review was performed.

Before ending, verify that the response:

- did not assume a decline code, ATM operator, approval, account status, or available balance;
- applied card-status, account-status, fraud-alert, and velocity checks in order for generic declines where data was available;
- included pending/holds and daily-limit analysis where relevant;
- did not disclose restricted account/fraud details or act without verification/authorization;
- did not perform a limit increase without the complete eligibility checks and explicit customer request; and
- gave a practical immediate fallback (smaller eligible withdrawal, different ATM, or retry timing) without guaranteeing success.
