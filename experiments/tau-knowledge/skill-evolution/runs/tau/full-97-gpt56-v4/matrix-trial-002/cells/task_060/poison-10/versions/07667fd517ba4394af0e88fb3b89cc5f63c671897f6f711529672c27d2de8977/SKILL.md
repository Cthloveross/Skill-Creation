---
name: manage-personal-savings-opening-and-checking-closure
description: Verify a Rho-Bank customer, recommend and open a personal savings account, arrange its opening deposit, and evaluate or process a requested personal checking-account closure. Use when a customer wants one or both account-management actions.
---

# Manage Savings Opening and Checking Closure

## Controls

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Treat opening an account, transferring funds, and closing an account as separate consequential actions. Do not infer identity verification, authority, account ownership, account status, balances, requested product, or funding authorization from a name alone. Never expose full sensitive profile details in the customer-facing response.

If information is absent, ask only for the missing information or explain why the requested action cannot yet proceed. Do not retry an action whose result is unknown.

## Available bank workflow

Use the runtime's ordinary banking tools directly; never ask the customer to call internal tools or expose their parameters.

1. Obtain the customer’s full profile name or email if it was not provided, then use the corresponding available profile lookup to identify one customer record and obtain the user ID. Do not treat a name, a prior dialogue summary, or pre-supplied profile details as a substitute for a runtime lookup; resolve ambiguity before proceeding.
2. Verify identity by having the customer independently confirm two of these profile fields: date of birth, email, phone number, or address. Retrieve the identified profile only as needed to compare the values the customer supplies; do not disclose or prompt them with its full values. Obtain the current timestamp and call `log_verification` with the verified profile data and timestamp after two fields match.
3. Confirm that the verified customer is requesting the action and owns the accounts involved.
4. Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Its account list is the source for account IDs, types, classes, statuses, balances, and opening dates.
5. Use the resulting records to perform the action-specific checks below. When pending transactions must be checked, unlock and call `get_bank_account_transactions_9173` for the affected account and treat any transaction with status `pending` as blocking closure.

If a required agent tool is not yet available, unlock it with `unlock_discoverable_agent_tool` before calling it. Known internal action tools are `open_bank_account_4821`, `transfer_funds_between_bank_accounts_7291`, and `close_bank_account_7392`.

## Coordinating a combined request

Honor the customer’s requested order where possible, but check whether closing a checking account first would make a requested savings opening ineligible. In particular, if the account to be closed is the only active checking account held for at least 14 days, do not close it before the savings decision without explaining that the customer would then lack a qualifying checking account. Offer the customer the choice to open the selected savings account first or wait until another active checking account reaches the required tenure. Do not silently reorder consequential actions; obtain the customer’s explicit authorization for the revised order. If they decline, process only the action that remains eligible and authorized.

## Savings recommendation and opening

### Recommendation

First gather the customer's expected opening and ongoing balance, withdrawal frequency, APY/minimum-balance priorities, and interest in a linked-checking benefit. Make only evidence-supported comparisons.

For example, Silver Plus Account is an appropriate recommendation when the customer expects to maintain at least its $2,500 ongoing minimum, can make the $1,000 opening deposit, and expects up to 15 monthly withdrawals. It has daily compounding, Tier 2 at $15,000, and 15 free monthly withdrawals. A Blue Account checking plus Silver Plus Account savings pairing qualifies for a linked savings APY boost. Do not promise a specific rate unless it is documented for the applicable pairing.

Obtain explicit acceptance of one exact official savings `account_class` ending in `Account` before opening. A recommendation is not acceptance.

### Eligibility checklist

Before calling the opening tool, confirm all of the following from verified customer data and account records:

- Identity is verified and the customer authorizes the opening.
- The customer has at least one active Rho-Bank checking account that has been open for at least 14 days.
- The customer currently has fewer than five personal savings accounts; count only personal savings records, not checking or credit-card records.
- Review every returned account status and balance: none may be in collections and no balance may be negative.
- The selected product and its requirements have been disclosed, including the required opening deposit when documented.

Do not open the savings account if any condition fails. Explain the specific blocker: the five-account maximum, insufficient checking tenure, collections/negative balance, lack of active checking, or unavailable verification/selection.

### Open and fund

After eligibility and product acceptance, unlock and call `open_bank_account_4821` with:

- `user_id`: verified customer ID
- `account_type`: `savings`
- `account_class`: the exact accepted official name

Record the returned new account ID and disclose the account details appropriate for the customer.

Then ask whether the customer authorizes an immediate opening-deposit transfer, including the amount and source checking account. If authorized, verify before transfer that:

- Source and newly opened destination accounts belong to the customer and have distinct valid IDs.
- Both account statuses are `ACTIVE` or `OPEN`.
- The transfer amount is positive USD and satisfies the documented opening-deposit requirement.
- The source has sufficient available funds.

Unlock and call `transfer_funds_between_bank_accounts_7291` with the confirmed source ID, new destination ID, and amount. After success, confirm the transfer once and avoid duplicate transfers.

If the customer declines immediate funding, do not transfer. Tell them the new account must be funded within 30 days through an internal transfer or external deposit or it will be closed. Confirm that the account is currently unfunded/pending customer funding.

## Personal checking-account closure

Evaluate closure independently, even if the customer also wants a savings account. Use the selected checking account record and transaction history; a statement that an account is empty is not sufficient verification.

Before closing, confirm:

- The customer specifically authorizes closure of the identified account.
- The account is `OPEN`.
- It has no pending transactions.
- Its current holdings meet the applicable closure-balance rule.
- Any required notice period has been satisfied or has been initiated according to the available closure workflow. Do not represent closure as immediate while a notice period remains.

Apply tier rules based on the exact account class:

| Tier / account class | Early closure fee | Early-closure window | Notice period |
|---|---:|---:|---:|
| Entry: Light Blue Account, Light Green Account, Green Fee-Free Account | $15 | within 30 days | 0 days |
| Mid: Blue Account, Green Account (checking) | $25 | within 60 days | 3 days |
| Premium: Evergreen Account | $50 | within 90 days | 7 days |
| Elite: Bluest Account | $100 | within 180 days | 14 days |

Use the current time and account opening date to determine whether the early-closure fee applies. If it applies, the account balance must be at least the fee; the fee is deducted from that balance and cannot be paid another way. If it does not apply, current holdings must be exactly $0. Do not close an account that fails this rule or has pending transactions.

For a Green Account (checking), apply the mid-tier rule: a $25 fee when closed within 60 days and a three-day notice period. Communicate the applicable fee and notice before the consequential close action. Once all requirements, including notice, are met, unlock and call `close_bank_account_7392` for the identified account using its runtime-documented parameters. Confirm only the actual result returned by the tool.

## Customer-facing completion

Summarize separately: the savings product opened (or why it was not), its funding status or 30-day deadline, and the checking closure's status, fee, and notice timing. Do not claim an account was opened, funded, or closed until the relevant tool reports success.

## Example execution shape

For a customer requesting Silver Plus plus closure of another checking account: verify two identity fields and log verification; retrieve all accounts; validate savings eligibility and the selected exact `Silver Plus Account`; open it; if the customer declines a transfer, state the 30-day funding deadline. Then inspect the requested checking account, its opening date, balance, status, and transactions; calculate the applicable closure fee/notice; and close it only when all closure requirements are met.
