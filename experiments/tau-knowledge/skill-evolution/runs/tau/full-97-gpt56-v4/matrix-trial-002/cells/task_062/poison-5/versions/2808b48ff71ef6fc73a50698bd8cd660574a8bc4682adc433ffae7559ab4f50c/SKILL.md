---
name: coordinated-bank-account-changes
description: Safely handles a customer request involving personal savings or checking closures, a business-checking opening, and a personal-savings opening. Use when recommendations, eligibility checks, sequencing, verification, and bank-tool actions must be coordinated in one interaction.
---

# Coordinated Bank Account Changes

Use this workflow for a combined request to close accounts and open business checking and/or personal savings. Do not treat an expressed desire to open an account as a selected product or as authority to transfer funds.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Tool and verification procedure

1. Identify the customer using supplied name or email with the relevant customer lookup tool.
2. Authenticate before any state-changing action. Ask the customer to provide or confirm at least two identity fields from date of birth, email, phone number, and address. Compare those fields against the customer record; do not reveal unprompted record values to make authentication easier.
3. Obtain the current timestamp and call `log_verification` only after two fields match. Its required fields must be copied from the verified customer record, and `time_verified` must be the current-tool timestamp.
4. Establish authority and ownership:
   - For existing-account actions, retrieve the customer’s accounts and confirm each target belongs to the authenticated customer.
   - For a business account, confirm the customer is an authorized signer/representative for the business and gather any required business application facts before opening. Do not imply that personal-account verification alone proves LLC authority.
5. Unlock and call `get_all_user_accounts_by_user_id_3847` to obtain all account IDs, types, classes, statuses, balances, and opening dates. Retrieve records again immediately before every state-changing action if earlier actions could have changed eligibility.
6. Use `scripts/account_workflow.py` to make transparent, deterministic assessments from the retrieved records. The script never performs a bank action and its output is a checklist, not a substitute for missing data.

Never expose internal tool names or tool parameters to the customer. Never use a customer-facing discoverable tool for these bank actions.

## Recommended sequencing

Plan the full request before performing the first irreversible action. A business-checking opening requires that the customer have **no accounts with status CLOSED**. Therefore, when business checking is requested alongside closures, complete all verification, authority, selection, and business-opening eligibility checks first, and open the business checking account before closing any account. If business eligibility fails, do not close an account merely to continue; explain the blocker and offer appropriate next steps.

A personal-savings opening requires an active Rho-Bank checking account held at least 14 days. Before closing a checking account, ensure that another qualifying checking account will remain if it is needed for the savings opening or deposit transfer.

A usual safe order, after all required confirmations, is:

1. Verify identity and business authority; retrieve accounts.
2. Compare products and obtain the exact business-checking `account_class` selection.
3. Verify business-checking eligibility and open it.
4. Re-retrieve accounts, compare personal savings products, and obtain the exact personal-savings `account_class` selection and funding decision.
5. Verify personal-savings eligibility and open it.
6. If the customer authorizes immediate funding, validate the source checking account, opening-deposit amount, status, ownership, available balance, and destination account, then transfer the deposit.
7. Re-check and close requested accounts only when their respective closure requirements are met. Honor applicable notice periods and never represent a closure as complete until the closure tool succeeds.

If a requested account is a required qualifying checking account, explain the sequencing dependency before closing it.

## Product comparisons and selection

Use only documented product facts and distinguish a recommendation from a customer’s exact selection.

### Personal savings considerations

- **Bronze Account:** $0 opening deposit and ongoing minimum balance, 2.0% APY, six free withdrawals per month; excess withdrawals and paper statements can have fees.
- **Green Account (savings):** $100 opening deposit, $500 ongoing balance, 4.0% APY, paperless statements required, and eight free withdrawals per month. EcoCard benefits can raise the free withdrawal total to 15 only when that separate eligibility applies.
- **Silver Account:** $500 opening deposit, $1,000 ongoing balance, 10 free withdrawals per statement cycle, with higher APY tier at $10,000.
- **Silver Plus Account:** $1,000 opening deposit, $2,500 ongoing balance, 15 free withdrawals per month, and a possible $8 monthly maintenance fee below the ongoing balance requirement.
- **Gold Account:** $10,000 stated minimum balance and 20 monthly withdrawals; it is generally unsuitable where the customer cannot support that balance.

For a customer expecting 10–15 monthly savings withdrawals and approximately $2,500–$3,000 savings, explain that Silver Plus has the documented 15-free-withdrawal allowance but sits at the $2,500 ongoing requirement and has a potential fee below it. Discuss whether the customer can maintain that balance. Do not promise that a feature, waiver, card benefit, or APY bonus applies without confirming its separate eligibility.

### Business checking considerations

- **Navy Blue** has a $0 monthly maintenance fee, no minimum balance requirement, a $25,000 daily digital-transfer limit, and standard ACH availability. Same-day ACH may be profile-dependent and has a stated $5 fee.
- **Cobalt Blue** has a $20 monthly fee waived by maintaining a daily balance of at least $2,500, includes 175 monthly transactions, supports ACH, and charges $20 for outgoing domestic wires.
- **True Blue** has a $25,000 maintenance minimum and a $75 monthly fee unless the balance is at least $50,000 during the statement period.

For a basic new LLC seeking low fees and roughly 50–100 transactions monthly, Navy Blue is often the documented fit, subject to confirming payment rails, expected balance, business eligibility, and the customer’s explicit selection. Do not invent card-acceptance, international-payment, or account-opening features that are not documented.

Ask one consolidated follow-up if facts are missing: exact selected account classes, business legal name and authorized-signer confirmation, expected business balance and client payment method, personal-savings funding amount, and whether the customer authorizes an immediate internal transfer. `account_class` must be the full official name ending in `Account` (for example, `Navy Blue Account` or `Silver Plus Account`).

## Business checking opening

After verification, authority confirmation, selection, and fresh account retrieval, require all of the following:

- customer is verified;
- at least one existing **personal** checking account has status `OPEN`;
- the customer currently holds fewer than six business checking accounts (opening another must not exceed the six-account maximum);
- no account has status `CLOSED`;
- an existing checking account has a balance of at least $500.

If every condition is met and the customer has selected an account class, unlock `open_bank_account_4821` and call it with the authenticated user ID, `account_type` set to `checking`, and the exact selected business account class. Record the returned account ID and result. If tool output is ambiguous or reports `UNKNOWN`, do not repeat the operation; retrieve accounts and resolve the state first.

## Personal savings opening and funding

Before opening, require all of the following:

- verified customer identity;
- at least one active Rho-Bank checking account;
- fewer than five existing personal savings accounts;
- no accounts in collections and no negative balances;
- qualifying checking-account tenure of at least 14 days;
- customer-selected full official savings account class.

If eligible, unlock `open_bank_account_4821` and call it with `account_type` set to `savings` and the exact selected account class. Confirm the returned account ID before considering a funding transfer.

Ask whether the customer wants an immediate opening-deposit transfer. If yes, obtain explicit transfer authorization and validate: source and destination are distinct accounts owned by the customer, both are `ACTIVE` or `OPEN`, the source has sufficient available funds, the amount is positive USD, and the amount meets the selected product’s documented opening-deposit minimum. Unlock and call `transfer_funds_between_bank_accounts_7291` once. Verify its posting before confirming completion. If the customer declines immediate funding, clearly state that the account must be funded within 30 days through internal transfer or external deposit or it will be closed.

## Closures

For each closure, use fresh records and establish: the account is `OPEN`, it belongs to the customer, it has no pending transactions, its balance is acceptable, any applicable early fee and notice period have been handled, and the customer’s request/confirmation covers the closure.

- **Bronze Account (savings):** $20 early-closure fee if closed within 60 days; one-day notice period.
- **Evergreen Account (checking):** $50 early-closure fee if closed within 90 days; seven-day notice period.

If an early closure fee applies, the account balance must be at least the fee because the fee is deducted from that balance. If no early fee applies, the account balance must be $0. Do not transfer funds merely to make a closure possible unless separately authorized and all transfer preconditions are satisfied. Do not claim a notice-period closure is immediately complete.

When all closure requirements, including the applicable notice process, are satisfied, unlock `close_bank_account_7392` and call it once for the target account. Re-retrieve accounts to verify the resulting status. Never retry an operation reported as `UNKNOWN`.

## Handling missing data or failures

- If identity or authority cannot be verified, stop before any banking action.
- If account retrieval lacks a required field, treat that condition as unverified; do not infer it from a product name or balance.
- If eligibility is not met, name the specific documented blocker and do not open the account.
- If a closure’s pending-transaction state is unavailable, do not close it; obtain that state through the available bank workflow or explain that it must clear.
- If a selected account has no documented opening-deposit amount, do not guess. Confirm the amount through the relevant product workflow before offering or executing funding.
- For tool errors, report only confirmed results. Do not duplicate an action after a timeout, ambiguous response, or `UNKNOWN`; inspect current account state first.

## Script usage

Run the included script through the Skill runtime, supplying current account records rather than hardcoded customer data:

```json
{
  "operation": "business_opening",
  "now": "2025-01-01T12:00:00-05:00",
  "accounts": [{"account_id": "...", "account_type": "checking", "account_class": "...", "status": "OPEN", "balance": 500, "date_opened": "2024-01-01", "is_business": false}],
  "identity_verified": true
}
```

Supported `operation` values are `business_opening`, `personal_savings_opening`, and `closure`. For `closure`, include `target_account_id` and `pending_transactions` when known. The script emits JSON with `eligible`, `blockers`, `checks`, and, where applicable, fee and notice information. Treat `unknown` checks as blockers. Validate that the output has no blockers before acting, then still apply confirmation, authority, and fresh-record requirements above.

Finish by summarizing only confirmed completed actions, the new account details actually returned, funding status or deadline, any pending notice period, and any unresolved blockers.
