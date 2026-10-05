---
name: checking-account-transition
version: 1.0.0
description: Verify and execute a customer-requested transition from an existing personal checking account to a new personal checking account, including required debit-card closure, account-closure eligibility, and new-account opening eligibility. Use when a verified customer wants to close, replace, or upgrade a checking account.
---

# Checking Account Transition

Use this Skill for a requested checking-account closure followed by an optional new personal checking account opening. A customer may generally close the old account first; do not require a replacement account to be opened before closure unless an applicable requirement says so. Explain that associated debit cards must be closed before the linked checking account can close.

Do not open a savings account when the customer has deferred it. Do not infer account selection, closure reason, verification facts, pending-transaction status, or confirmation from incomplete data.

## Mandatory controls

Before every banking action, verify customer identity, authority, ownership, product eligibility, available balance, fees, limits, cutoffs, recipient and card details, and any confirmation requirement. Preserve the checks and their results in the action record.

For identity verification, obtain and confirm two of the four identity fields (date of birth, email, phone number, address) against the customer record. Retrieve the current timestamp and create the verification audit record using `log_verification` before closure or opening actions. A name lookup or a user ID alone does not complete identity verification.

## Runtime inputs and retrieval

1. Identify the customer through a supplied name or email, retrieve the customer record, and obtain the two verification fields from the customer.
2. Retrieve all customer bank accounts with `get_all_user_accounts_by_user_id_3847`. Select the specifically requested personal checking account; if more than one account could match the request, ask the customer to identify it.
3. Retrieve every debit card attached to the selected checking account with `get_debit_cards_by_account_id_7823`.
4. Obtain reliable current status for pending card transactions, pending refunds, and pending account transactions. A card's `PENDING` status is not, by itself, proof of whether pending transactions or refunds exist.
5. Use the current date/time to assess account and card age. Recheck volatile information immediately before each mutating action.

The named banking operations may be discoverable tools. Unlock the named tool before calling it, then call it using its documented parameters. Do not treat this Skill or its helper output as authorization to make a banking action.

## Explain the closure-first sequence

If the customer asks why the checking account cannot yet close, explain plainly: it can be closed first if it qualifies, but any associated debit cards must be closed first. The customer has not been denied the requested sequence. State the actual unresolved condition (for example, verification, card age, a pending transaction, a refund, balance, notice period, or account status) rather than guessing.

## Debit-card closure workflow

For every attached card that is not already CLOSED:

1. Confirm the verified customer owns the card (`card.user_id` matches the verified customer), and that its status is ACTIVE or PENDING.
2. Confirm there are no pending or processing transactions and no pending refunds. A pending refund may proceed only if the customer provides the required written acknowledgement that it will be credited to the linked checking account; retain that acknowledgement. Do not close the card otherwise.
3. Obtain a closure reason from: `lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`. When the checking account is being closed, `account_closing` is appropriate if that is the customer's stated purpose.
4. Check that the card was issued at least 14 days ago. `lost`, `stolen`, and `fraud_suspected` bypass only this minimum-age requirement; they do not bypass ownership or pending-transaction/refund checks. For a card that is too new, give the earliest eligible date.
5. After the above checks pass, call `close_debit_card_4721` with `card_id` and `reason`.
6. Confirm the result and tell the customer that closure is permanent, recurring payments need updated payment details, and refunds to a closed card credit the linked checking account. For loss, theft, or suspected fraud, mention that pending transactions still process; for suspected fraud, recommend reviewing transactions, disputing unauthorized charges, and changing the online-banking password.

Do not begin checking-account closure until all associated cards are confirmed CLOSED.

## Checking-account closure workflow

Assess the selected account against all of these requirements immediately before calling `close_bank_account_7392`:

- The customer is verified and owns/has authority over the account.
- Account status is exactly OPEN.
- There are no pending account transactions.
- All associated debit cards are CLOSED.
- Determine the tier from the exact account class and apply its early-closure fee and notice period:

| Tier | Exact account classes | Early closure fee | Fee window | Notice |
|---|---|---:|---:|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 | first 30 days | 0 days |
| Mid | Blue Account; Green Account (checking) | $25 | first 60 days | 3 days |
| Premium | Evergreen Account | $50 | first 90 days | 7 days |
| Elite | Bluest Account | $100 | first 180 days | 14 days |

If the account is within its fee window, its balance/current holdings must be at least the fee; the fee is deducted directly from the account and cannot be paid another way. If outside the fee window, balance/current holdings must be exactly $0. Do not suggest transferring out a balance that is needed to pay an applicable closure fee.

For a tier with notice, ensure the documented notice has been given and the required number of calendar days has elapsed before closing. If the runtime has no supported notice-recording process, do not assume notice was given; explain the limitation and defer the closure rather than calling the closing tool.

When every condition passes, call `close_bank_account_7392` with the parameters required by the discovered tool. Confirm the closure result before proceeding. If any condition fails or is unknown, do not call the tool; state the concrete prerequisite and next step.

## New personal checking account workflow

Only open a replacement after the requested closure is confirmed if the customer requested closure first. Confirm the desired exact official `account_class`; do not silently select a product. The documented checking classes include `Light Blue Account`, `Light Green Account`, `Green Fee-Free Account`, `Blue Account`, `Green Account (checking)`, `Evergreen Account`, and `Bluest Account`.

For an Evergreen recommendation, disclose that eligible direct deposits can arrive up to two days early and that it has a $6 monthly maintenance fee, waived with a $500 minimum daily balance. Confirm that the customer wants this specific account before opening it; early direct-deposit timing depends on payer transmission and standard processing.

Before calling `open_bank_account_4821`, verify all opening requirements:

- customer remains verified;
- customer is at least 18;
- the customer will not exceed four personal checking accounts after the new account is opened; and
- the customer has no checking account closed for cause in the last six months.

Then call `open_bank_account_4821` with the verified user and selected official account class as required by the discovered tool. Confirm the returned account details. Do not promise a direct-deposit posting date or claim that a deferred savings-account request was completed.

## Deterministic assessment helper

`scripts/assess_transition.py` assesses supplied facts without making banking calls. It accepts one JSON object on stdin and returns one JSON object on stdout.

Input fields:

- `as_of` (required): ISO date or timestamp used for date calculations.
- `customer`: object containing `user_id` and `identity_verified`.
- `target_account`: selected account object with `account_id`, `owner_user_id`, `account_class`, `status`, `date_opened`, `balance` or `current_holdings`, and `pending_transactions`.
- `cards`: all cards returned for the target account. Each card should include `card_id`, `account_id`, `user_id`, `status`, `date_issued`, `pending_transactions`, and `pending_refunds`.
- `card_reasons`: object mapping a card ID to a documented closure reason.
- `notice_given_on` (optional): ISO date when closure notice was recorded.
- `opening` (optional): object with `requested`, `account_class`, `customer_age`, `open_personal_checking_count_after_closure`, and `closed_for_cause_last_6_months`.

Missing or invalid facts are reported as blockers rather than assumed to be favorable. Its output contains tier/fee/notice calculations, card-specific blockers, account blockers, opening blockers, and an ordered next-action plan.

A runtime invocation can use the declared stdin/stdout contract, for example:

```sh
printf '%s' "$INPUT_JSON" | python3 scripts/assess_transition.py
```

Validate the output before acting: `account.can_close_now` must be true to call the account-closure tool; every nonclosed card must first be successfully closed; and `opening.can_open` must be true to call the opening tool. Re-run the assessment using fresh records after any card closure and immediately before each banking action.
