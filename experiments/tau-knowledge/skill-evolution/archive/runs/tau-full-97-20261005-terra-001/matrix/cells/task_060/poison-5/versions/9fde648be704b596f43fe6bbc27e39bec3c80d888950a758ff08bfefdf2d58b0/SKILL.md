---
name: personal-checking-closure-and-savings-opening
description: Safely close a personal checking account and/or recommend and open a personal savings account. Use when a verified customer requests checking-account closure, debit-card closure needed before checking closure, savings-account selection, savings opening, or opening-deposit funding.
---

# Personal Checking Closure and Savings Opening

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do not treat a name, email address, account number, or a prior lookup as identity verification. Obtain and match at least two of the four identity fields (date of birth, email, phone number, address), then obtain the current time and call `log_verification` with every required profile field. Confirm the customer is authorized to close the identified account and to authorize any transfer. Do not take an irreversible action until verification, ownership, authority, and all applicable prerequisites are established.

## Available internal tools

Unlock a documented agent tool before calling it. Agent tools are never handed to the customer.

- `get_all_user_accounts_by_user_id_3847(user_id)`: retrieve account ID, type, class, status, balance, and opening date.
- `get_bank_account_transactions_9173(account_id)`: inspect account transactions, including pending status.
- `get_debit_cards_by_account_id_7823(account_id)`: list cards linked to a checking account.
- `close_debit_card_4721(card_id, reason)`: close an eligible debit card. Use `account_closing` when the stated reason is closure of the linked checking account.
- `close_bank_account_7392`: close an eligible checking account. After unlock, follow the exposed parameter schema; the knowledge base does not establish its arguments.
- `open_bank_account_4821(user_id, account_type, account_class)`: open a savings account only after the opening checks pass. Set `account_type` to `savings`; `account_class` must be the confirmed official class name ending in `Account`.
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`: fund the newly opened account only with explicit customer authorization.

## End-to-end workflow

### 1. Verify, identify, and retrieve

1. Locate a possible profile only from customer-provided identifying information. Ask for and match two identity fields against the profile, log the successful verification, and record the authenticated `user_id`.
2. Confirm which checking account is to be closed, the customer's authority, and whether another checking account is to remain open.
3. Retrieve all accounts using `get_all_user_accounts_by_user_id_3847`. Verify that each proposed source, closure target, and retained checking account belongs to the authenticated customer.
4. Use `scripts/evaluate_bank_request.py` to make date, balance, count, and status checks reproducible. Supply live account and transaction data; do not substitute assumed balances, tenure, or statuses.

### 2. Close a checking account safely

For the requested closure target, verify all of the following before calling the closure tool:

1. Its status is `OPEN`.
2. Retrieve its transaction history and confirm there are no pending transactions.
3. Determine its documented tier, early-closure window and fee, and notice period:
   - Light Blue Account, Light Green Account, Green Fee-Free Account: $15 if closed within 30 days; no notice.
   - Blue Account or Green Account (checking): $25 if closed within 60 days; 3 days' notice.
   - Evergreen Account: $50 if closed within 90 days; 7 days' notice.
   - Bluest Account: $100 if closed within 180 days; 14 days' notice.
4. If an early fee applies, the balance must be at least the fee; otherwise the balance must be exactly $0. The fee is deducted from that account and cannot be paid another way.
5. Calculate the earliest closure date from the customer’s closure notice/authorization. Do not call the closure tool before the required notice has elapsed. If no scheduling capability is exposed by the closure tool, explain the date and arrange the closure only when the customer returns after that date; do not invent a scheduling operation.
6. Retrieve every debit card linked to the checking account. Every associated active or pending card must be closed before the checking account closes. For each card, confirm ownership, ACTIVE/PENDING status, absence of pending/processing transactions and pending refunds, and that it has been active for at least 14 days. The lost/stolen/fraud age exception does not apply merely because the account is closing. If a card is ineligible, defer the checking closure and explain the blocking condition. When eligible, close it using reason `account_closing` and confirm it is permanently deactivated.
7. Recheck account/card prerequisites immediately before calling `close_bank_account_7392`. Follow its unlocked schema and report the result, applicable fee, and any remaining notice status accurately.

Never infer that an account is empty from the customer’s statement; validate its live balance. Do not close a checking account while linked cards, pending transactions, balance/fee requirements, or notice requirements remain unresolved.

### 3. Determine savings eligibility

Before opening a personal savings account, confirm all of the following from verified live information:

- The customer is verified.
- At least one customer-owned Rho-Bank checking account remains active and has been open at least 14 days. When a checking closure is also requested, evaluate the checking account(s) that will remain after closure.
- The customer holds fewer than five personal savings accounts.
- No customer account is in collections or has a negative balance.
- The exact savings account class has been selected and confirmed.

Stop and explain the failed condition if any check fails. For a checking tenure failure, provide the date eligibility begins. Do not infer collections information when it is unavailable; obtain the required account-status information or explain that opening cannot proceed until it is verified.

### 4. Recommend exactly one account when asked

Base a recommendation on stated expected balance, opening capacity, desired features, and documented terms. State only documented facts and disclose material requirements. For a customer expecting approximately $2,500–$4,000 and not expecting to maintain $10,000 or more, the documented fit among these offerings is **Green Account (savings)**: 4.0% APY, $100 minimum opening deposit, $500 ongoing minimum balance, eight free withdrawals monthly, and paperless statements required. The class value for opening must be the official name **`Green Account`**, which ends in `Account`.

Relevant comparison facts if requested: Silver Account requires a $500 opening deposit, $1,000 ongoing balance, and has a 2.5% lower tier below $10,000; Silver Plus Account requires a $1,000 opening deposit, $2,500 ongoing balance, and has a 3.0% Tier 1 rate below $15,000; Platinum Account requires $25,000 to open and a $50,000 ongoing balance. Do not claim a checking or card APY bonus without verifying that the qualifying product is active and linked. Multiple checking boosts do not stack; only the highest applicable checking boost applies. Multiple credit-card bonuses also do not stack; only the highest applicable card bonus applies.

A recommendation is not authorization. Restate the one recommended product, material opening/maintenance conditions, and exact official `account_class`, then obtain confirmation to open it. For Green Account (savings), also obtain confirmation that the paperless-statement requirement will be met. If no available tool can establish a required enrollment, do not represent enrollment as completed.

### 5. Open and fund the savings account

1. After all eligibility checks and product confirmation pass, unlock and call `open_bank_account_4821` with the authenticated user ID, `savings`, and the exact confirmed official class ending in `Account`.
2. Record the returned new account ID and verify the account was created for the authenticated customer.
3. Ask whether the customer wants to transfer the required opening deposit from a specified checking account now. Do not presume authorization from an earlier desire to open an account.
4. If authorized, verify the selected source and the new savings destination are distinct, customer-owned, and `ACTIVE` or `OPEN`; verify sufficient available funds; verify a positive USD amount at least equal to the required minimum; then call `transfer_funds_between_bank_accounts_7291`.
5. Confirm the transfer posted as expected and was not duplicated. If the customer declines immediate funding, state that they have 30 days to fund the account by internal transfer or external deposit or it will be closed.
6. Clearly summarize the new account details, whether it is funded, the amount/source if transferred, and either the funding completion or 30-day deadline.

## Validation helper

`scripts/evaluate_bank_request.py` performs deterministic preflight evaluation and does not call banking tools.

Input is a JSON object on stdin:

```json
{
  "now": "2025-01-01T12:00:00-05:00",
  "identity_verified": true,
  "authority_confirmed": true,
  "accounts": [{"account_id": "...", "account_type": "checking", "account_class": "Green Account", "status": "OPEN", "balance": "0", "date_opened": "2024-01-01", "in_collections": false}],
  "closure": {"account_id": "...", "has_pending_transactions": false, "notice_given_at": "2025-01-01T12:00:00-05:00", "all_linked_cards_closed": true},
  "savings": {"account_class": "Green Account", "opening_deposit": "100", "source_account_id": "...", "immediate_funding_authorized": true}
}
```

`in_collections` must be supplied for every account to make savings eligibility determinable. `closure` and `savings` are optional. The script emits JSON containing `closure`, `savings_opening`, and `funding` objects with `eligible`, `blocked_reasons`, `warnings`, computed fee/notice data, and selected account identifiers. Treat missing required evidence as a blocker, then obtain it through the appropriate live process rather than guessing.

Run it through the packaged-script runtime with the live JSON input. Validate that all relevant `eligible` values are true and that `blocked_reasons` is empty before taking the corresponding action. The helper does not replace identity logging, debit-card checks, live tool calls, explicit authorization, or post-action confirmation.
