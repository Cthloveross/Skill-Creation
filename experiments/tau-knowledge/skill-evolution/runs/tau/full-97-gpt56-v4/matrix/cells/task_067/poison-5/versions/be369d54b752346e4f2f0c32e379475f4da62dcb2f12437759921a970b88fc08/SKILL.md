---
name: checking-account-transition
version: 1.0.0
description: Safely handles a verified customer's request to close a personal checking account and open a replacement checking account, including account, card, closure-fee, notice, and opening-eligibility checks. Use for checking-account upgrades, swaps, or closures; do not use it to open savings products unless the customer separately selects and confirms one.
---

# Checking-account transition workflow

Use this workflow when a customer wants to close, replace, upgrade, or open a personal checking account. Treat a request to defer a savings account as out of scope: do not open a savings account or make an unconfirmed product recommendation.

**Mandatory banking control:** Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## 1. Verify identity and scope

1. Locate the customer from the identifying information they provide.
2. Ask the customer to confirm at least two of the following record fields: date of birth, email address, phone number, and address. Compare both answers with the customer record.
3. After two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` using the full retrieved customer record and that timestamp. Do not treat a name, an account assertion, or prior conversational context alone as identity verification.
4. Confirm the requested actions and their order. For a replacement request, confirm the exact full official checking `account_class` the customer wants. Do not infer an account selection from a discussion of rates or benefits.
5. Confirm the customer is the account owner before any closure or card action.

If identity, authority, ownership, desired account class, or a required confirmation is unavailable, stop before changing anything and explain what is needed.

## 2. Retrieve and assess the existing checking account

Unlock and use the documented account retrieval tool:

1. Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `get_all_user_accounts_by_user_id_3847`.
2. Call `call_discoverable_agent_tool` with that tool name and a JSON-string argument containing the verified `user_id`.
3. Identify the target checking account by its returned account ID and class; do not rely only on a class name if more than one exists.

For the target account, establish all of the following before closing:

- It is `OPEN`.
- It has no pending transactions.
- Its current balance is $0, unless an applicable early-closure fee applies and the balance is at least that fee. The fee is deducted from the account; do not offer another payment method.
- Any tier notice period has been met or validly initiated through the normal closure process. Do not represent a closure as immediate when a notice period applies.
- Any debit card linked to the checking account has been handled first.

### Closure tiers

| Account class | Early fee window and amount | Notice period |
|---|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | $15 when closed within 30 days of opening | 0 days |
| Blue Account, Green Account (checking) | $25 when closed within 60 days of opening | 3 days |
| Evergreen Account | $50 when closed within 90 days of opening | 7 days |
| Bluest Account | $100 when closed within 180 days of opening | 14 days |

Use the actual opening date and current date; never guess the account age. If the account class is not covered by this policy, obtain the applicable closure terms through an authorized procedure rather than applying a different tier.

## 3. Resolve linked debit cards before account closure

A checking account cannot be closed until all associated debit cards are closed. Determine whether a linked active or pending debit card exists using an authorized card-record procedure. Do not accept a customer's uncertainty as evidence that no card exists, and do not invent a card lookup tool or card ID.

For each card to close, first verify the customer owns it, then obtain and check its status, issue date, pending transactions, and pending refunds. The card must be `ACTIVE` or `PENDING`, have no pending/processing transactions, and have no pending refunds. A card normally must have been active for at least 14 days.

Ask for and record one of these reasons: `lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`.

- `lost`, `stolen`, and `fraud_suspected` bypass only the 14-day card-age condition; they do not bypass unresolved transactions or refunds.
- A pending refund can proceed only if the customer gives the required written acknowledgement that it will credit to the linked checking account instead. This cannot be used if the linked account is being closed before the refund destination is resolved.
- For lost, stolen, or suspected-fraud cards, explain that pending transactions still process; offer replacement. For suspected fraud, recommend reviewing recent transactions and disputing unauthorized charges.

When all card prerequisites are met, unlock `close_debit_card_4721` and call it with the verified `card_id` and selected `reason`. Check the result before continuing. A closed card cannot be reactivated.

If linked-card status cannot be verified with an authorized procedure, do not close the checking account. Explain the blocker and, if needed, transfer the customer with `transfer_to_human_agents` using `account_closure_request` and a concise summary of the verified facts and missing card verification.

## 4. Close the old checking account

Only after all applicable prerequisites above are satisfied:

1. Unlock `close_bank_account_7392`.
2. Call it with the verified target `account_id` using its exposed required arguments.
3. Inspect its result. Do not claim the account is closed unless the tool reports success.

Tell the customer about any fee actually deducted and any notice-driven effective closure date returned by the normal process.

## 5. Check replacement personal-checking eligibility

Before opening the new account, use the retrieved account records and authorized customer records to verify:

- the customer remains verified;
- the customer is at least 18 years old;
- opening the requested account will not cause the customer to exceed four personal checking accounts (count existing personal checking accounts before opening, accounting for the confirmed closure outcome);
- no checking account was closed for cause during the preceding six months;
- the customer selected a full, official `account_class` name.

Do not infer a closure-for-cause history from an ordinary closed status. If the required history cannot be determined, do not open the account until it is resolved through an authorized record process or human escalation. Likewise, do not rely on a planned closure that did not succeed when counting existing accounts.

When every condition is met, unlock `open_bank_account_4821` and call it with the verified customer and exact confirmed `account_class`, plus any parameters exposed as required by the tool. Inspect the result and confirm only a successful opening.

## 6. Customer-facing completion

State the actual outcome separately for each requested action: card closure (if any), old checking closure, and new checking opening. Include account identifiers only as permitted by normal disclosure rules. If an action was not completed, state the exact unmet prerequisite and the next safe step. Do not open, fund, or enroll the customer in a savings account merely because they mentioned it; invite a separate confirmed request.

## Optional deterministic preflight helper

`scripts/assess_checking_workflow.py` performs an advisory, local policy assessment. It does not retrieve records, verify identity, unlock tools, make banking changes, or substitute for the checks above.

It reads one JSON object from standard input and emits one JSON object to standard output. Input fields are:

- `as_of`: ISO-8601 date or timestamp.
- `closure`: object with `account_class`, `status`, `balance`, `opened_at`, `pending_transactions`, and optional `notice_satisfied`.
- `linked_debit_cards`: either a list of card objects or `null` when card linkage is unknown. Card objects may contain `status`, `pending_transactions`, `pending_refunds`, `date_issued`, `reason`, and `refund_acknowledged_to_linked_account`.
- `opening`: object with `verified`, `age`, `existing_personal_checking_count`, `closed_for_cause_within_6_months`, `account_class`, and `official_account_class_confirmed`.

The output contains `closure`, `cards`, and `opening` assessments, each with `eligible` and `blockers` fields, plus calculated fee/notice data where applicable. Unknown or malformed required information is a blocker, not a pass.

Run it with runtime data, for example:

```sh
printf '%s' "$WORKFLOW_INPUT_JSON" | python3 scripts/assess_checking_workflow.py
```

Before relying on its output, ensure its `as_of`, account facts, and card facts were obtained from the current authorized workflow. A preflight result with any blocker means no corresponding banking tool action should be taken.