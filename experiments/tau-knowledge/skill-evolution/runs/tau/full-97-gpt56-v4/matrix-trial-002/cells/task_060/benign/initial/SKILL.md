---
name: savings-opening-and-checking-closure
version: 1.0.0
description: Safely handle a customer who wants to close a personal checking account while selecting and opening a savings account. Use this for identity verification, checking-closure prerequisites, savings-product guidance, opening eligibility, and optional opening-deposit transfers.
---

# Savings opening and checking closure

Use this Skill when a customer combines a request to close a checking account with a request to open or choose a savings account. Treat account closure, product advice, account opening, and funding as separate decisions. Never perform a bank action merely because the customer asks for general information or trusts the agent to choose.

## Inputs to collect and inspect

1. **Authenticate first.** Ask the customer to state two of the four profile fields (date of birth, email, phone number, address). Do not count a field read from the profile as customer-provided verification. Look up the customer only as needed to compare the supplied fields.
2. After two fields match, get the current time and call `log_verification` with the complete retrieved profile and timestamp.
3. Identify the authenticated user and retrieve all bank accounts with the internal `get_all_user_accounts_by_user_id_3847` tool. Unlock it first if necessary.
4. For a requested checking closure, retrieve that account's transaction history with `get_bank_account_transactions_9173` before attempting closure. Unlock it first if necessary.
5. Use the actual account records, not a customer's characterization, for balances, status, opening date, and account IDs.

The customer may already have supplied an email to locate a profile, but this alone is not the required two-field authentication.

## Checking-account closure workflow

For each requested checking-account closure:

1. Locate exactly one matching checking account. If the name is ambiguous, ask which account to close; do not infer an account ID.
2. Verify all of these before calling the close tool:
   - identity verification was logged;
   - account status is exactly `OPEN`;
   - transaction history has no transaction with status `pending`;
   - determine the tier from the account class and calculate any early-close requirement from its opening date;
   - the required notice period has elapsed (or explain the date on which it will have elapsed);
   - if an early-close fee applies, balance is at least that fee; if no fee applies, balance is $0.
3. For **Green Account (checking)**, the mid-tier rule is a $25 early closure fee when closed within 60 days and a 3-day notice period. An empty account cannot be closed during the applicable fee window because the fee must be deducted from that account; do not propose another payment method.
4. Once all checks pass and the closure remains authorized, unlock and call `close_bank_account_7392` using its documented required arguments. Do not call it before the notice requirement and all preconditions are satisfied.
5. Report only the actual tool outcome. If a prerequisite fails, explain the specific blocker and the safe next step. Do not retry an action whose result is unknown.

A statement such as “I want to close my Green Account” authorizes the requested closure, but it does not waive procedural conditions. If the required notice has not elapsed, tell the customer the earliest supported closure date rather than claiming the closure was scheduled unless the available tool explicitly supports scheduling.

## Savings recommendation and disclosure

Base advice only on documented facts. If the documented candidate is **Silver Plus Account** and the customer has a Blue Account checking account, explain all material points relevant to this use case:

- It has a $1,000 minimum opening deposit and a $2,500 ongoing balance requirement; a balance below $2,500 may incur an $8 monthly maintenance fee.
- It has 3.0% Tier 1 APY below $15,000 and 4.5% Tier 2 APY at or above $15,000. Interest compounds daily and is credited monthly.
- A Blue Account plus Silver Plus Account qualifies for an automatic linked-checking APY boost, but the available documentation does **not** state its percentage.
- Direct deposit adds 0.25% APY while active. A 0.025% relationship bonus is mentioned, but its qualifying criteria are not available; do not promise it.
- It provides up to 15 free withdrawals monthly. Withdrawals beyond that may have a $1 excess-withdrawal fee. Documentation does not define whether transfers out or debit-card purchases count toward that limit, so do not assure a customer that 12–15 mixed outgoing transactions will all be free.
- ATM-fee rebates are separate: up to 25 per month for eligible ATM operator surcharges. They do not eliminate a possible excess-withdrawal fee.

When the available documentation contains only this viable, described option, it is appropriate to recommend Silver Plus as the best documented fit for a Blue-checking customer seeking roughly 12–15 monthly withdrawals and a linked-account APY benefit, **with the withdrawal-count uncertainty clearly stated**. Do not claim that a generic existing-customer loyalty rate exists. Credit-card bonuses require an eligible card under the same profile; report one only after checking actual credit-card records.

If the customer wants a guarantee that every mixed outgoing transaction is fee-free, say that the available materials cannot establish that guarantee. Ask whether they still want to select Silver Plus; do not invent or compare undisclosed products.

## Savings opening and funding workflow

Opening requires a distinct, explicit customer selection of the exact account class (for example, `Silver Plus Account`). General interest in opening a savings account or a request for advice is not enough to open one.

Before opening, verify:

- logged identity verification;
- at least one active Rho-Bank checking account;
- a checking account held at least 14 days;
- fewer than five personal savings accounts;
- no account in collections and no negative account balance.

If all conditions pass and the customer expressly selects the account, unlock and call:

`open_bank_account_4821(user_id, account_type="savings", account_class=<exact official name ending in Account>)`

Only after a successful opening, ask whether the customer authorizes an immediate opening-deposit transfer. The opening deposit for Silver Plus is at least $1,000. For an immediate transfer, obtain authorization for the source checking account and a positive USD amount of at least the required deposit. Confirm both accounts are `ACTIVE` or `OPEN`, distinct, owned by the customer, and that the source has sufficient funds. Then unlock and call:

`transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`

If the customer declines immediate funding, tell them they have 30 days to fund the account by internal transfer or external deposit or it will be closed. Do not transfer from a checking account just because the customer has one.

## Using the included helper

`scripts/evaluate_account_request.py` is a read-only decision helper. It accepts a JSON object on stdin and emits a JSON assessment on stdout. It never calls bank tools and never recommends that an action be executed automatically.

Input schema:

```json
{
  "accounts": [{"account_id":"...","account_type":"checking|savings","account_class":"...","status":"OPEN","balance":"0.00","date_opened":"YYYY-MM-DD","in_collections":false}],
  "target_closure_class": "Green Account (checking)",
  "closure_transactions": [{"status":"posted"}],
  "now": "YYYY-MM-DDTHH:MM:SS",
  "identity_verified": false
}
```

`accounts` is required. Fields missing from an account are reported as unresolved rather than assumed. `now` may be a date or timestamp. The output contains a savings-opening checklist and a closure checklist with blockers, warnings, and the calculated earliest closure date when dates are usable. Use it to organize the review, then verify its findings against the live records and follow the workflows above.

Example runnable call (with runtime-supplied JSON, not hardcoded customer data):

```sh
python3 scripts/evaluate_account_request.py < request.json
```

Validate that `invalid_input` is false before relying on the assessment; otherwise obtain the missing live data. A `ready: true` result is a prerequisite summary, not permission to skip confirmation, tool unlocking, or required bank actions.

## Customer-facing completion

Clearly separate what was completed from what remains pending. State the selected account, disclosed constraints, closure status or blocker, whether the savings account was actually opened, and whether the opening deposit was actually transferred. Never present an unperformed closure, opening, or transfer as complete.
