---
name: personal-account-migration-and-savings-selection
description: Safely handles a customer's request to close or replace a personal checking account, open checking and savings accounts, and compare eligible linked-checking APY options. Use for account migrations, personal checking/savings openings, closure screening, and opening-deposit arrangements.
---

# Personal Account Migration and Savings Selection

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

Use this workflow for personal checking and savings account changes. It produces assessments and action recommendations, but scripts never make banking changes. The executor alone performs approved actions using the normal banking tools.

Do not rely on a customer's recollection for account status, balance, pending transactions, opening date, account counts, collections, or identity-verification status. Retrieve and use authoritative system records. Do not infer an account class from a shortened name: use its full official name ending in `Account`.

## Required records before an action

1. Identify the customer from an unambiguous profile identifier.
2. Authenticate the customer by confirming two of the four profile fields: date of birth, email, phone number, and address. Retrieve the profile only to compare customer-supplied values; do not disclose values merely to solicit confirmation.
3. Obtain the current timestamp and log identity verification after two fields match.
4. Retrieve all bank accounts and, where relevant, credit-card accounts. For every affected account obtain its ID, type, class, status, ownership, opening date, actual current balance, pending-transaction state, and collection/negative-balance status.
5. Obtain explicit confirmation of each selected account class, each requested closure, applicable early-closure fee, opening deposit amount, source account, destination account, and whether an immediate transfer is authorized.

If a required system lookup, verification, confirmation, account ownership check, or prerequisite is unavailable, do not perform the affected action. Explain the precise missing item and request it or transfer only when the normal procedure requires escalation.

## Product decision method

When comparing choices, separate a savings APY from checking fees, checking APY, balance requirements, and perks. Do not promise an APY that requires an unmet balance, card, direct-deposit, relationship, or eligibility condition.

1. For each proposed savings class, identify its base APY tier at the customer's planned savings balance and all ongoing balance requirements.
2. Find only documented qualifying checking/savings pairings. A checking boost applies only when both eligible accounts are active under the same customer profile.
3. If more than one checking account qualifies for that savings class, use the single highest applicable checking boost; do not add checking boosts together.
4. Credit-card bonuses can add to a checking boost only when documented and actually eligible. If several cards qualify, use only the highest eligible card bonus.
5. Present a compact comparison that states assumptions, base APY, each eligible bonus, resulting stated APY, minimum/funding requirements, and important checking costs or benefits. Do not treat a bonus percentage as a monetary return.
6. Ask the customer to choose the exact checking and savings classes before opening either account.

For product facts supplied with an execution, use those facts as the current source of truth. `references/product-comparison-notes.md` records the known product-policy patterns and must not substitute for an account-specific lookup when a condition is uncertain.

## Opening personal checking

Before opening a personal checking account, verify all of the following from system records:

- identity is verified;
- customer is at least 18 years old;
- customer has fewer than four existing personal checking accounts;
- customer has no checking account closed for cause during the previous six months; and
- the exact desired official account class is confirmed.

If eligible and authorized, unlock and call `open_bank_account_4821` with the authenticated `user_id`, `account_type` of `savings` or `checking` as appropriate, and the exact official `account_class`. Record the returned account identifier and review the response before using it in a later transfer.

## Opening personal savings

Before opening a personal savings account, verify all of the following from system records:

- identity is verified;
- customer has at least one active Rho-Bank checking account that has been held for at least 14 days;
- customer has fewer than five personal savings accounts;
- no customer account is in collections or has a negative balance; and
- the selected savings class and any product-specific opening requirement are confirmed.

Do not close the only checking account that satisfies the 14-day condition before a requested savings account has been opened. If a replacement checking account was just opened, it does not itself satisfy that condition for the next 14 days.

After the savings opening succeeds, ask whether the customer authorizes an immediate opening-deposit transfer. If yes, confirm the source account belongs to the customer, the available balance covers the amount and applicable fees, and then use `transfer_funds_between_bank_accounts_7291` from the confirmed checking account to the newly returned savings-account ID. If no, state that the account must be funded within 30 days by internal transfer or external deposit or it will be closed.

## Closing a personal checking account

Retrieve the actual targeted account record. Before closure, confirm account ownership, that its status is `OPEN`, and that it has no pending transactions. Determine its applicable tier and closure age from its actual opening date:

| Tier / account classes | Early fee and period | Notice period |
| --- | --- | --- |
| Entry: Light Blue Account, Light Green Account, Green Fee-Free Account | $15 if closed within 30 days | 0 days |
| Mid: Blue Account, Green Account (checking) | $25 if closed within 60 days | 3 days |
| Premium: Evergreen Account | $50 if closed within 90 days | 7 days |
| Elite: Bluest Account | $100 if closed within 180 days | 14 days |

If an early fee applies, balance must be at least the fee because it is deducted directly from the account and cannot be paid another way. If no early fee applies, current holdings must be exactly $0. Do not presume that an account described as “empty” has a zero balance. Do not close if the opening date, balance, pending state, or tier cannot be confirmed.

After all conditions and any notice period are satisfied, unlock and call `close_bank_account_7392` using the tool's documented account identifier. Report the completed result only after the tool confirms it.

## Recommended order for a migration

1. Authenticate and log verification.
2. Read current account, eligibility, balance, and product-condition records.
3. Explain viable choices and obtain exact selections and confirmations.
4. If needed, open the replacement checking account after checking-opening eligibility passes.
5. While an existing qualifying checking account remains active, open the selected savings account after savings eligibility passes.
6. If expressly authorized, transfer the opening deposit only after the destination ID is returned; otherwise state the 30-day funding deadline.
7. Screen the old checking account for closure and close it only if all closure conditions hold. Honor any tier notice period.
8. Summarize account IDs/details appropriate for the customer, funding status, relevant fees/deadlines, and any unresolved prerequisite.

## Optional deterministic screening helper

Use `scripts/assess_account_changes.py` after authoritative observations are normalized into its JSON schema. It returns blocking conditions and non-executing next-action recommendations for checking opening, savings opening, and a requested closure. It does not replace profile authentication, product research, explicit customer authorization, tool-response review, or normal banking tools.

Example:

```json
{
  "as_of": "2025-01-15T12:00:00-05:00",
  "identity_verified": true,
  "customer": {"age": 30, "checking_closed_for_cause_within_6mo": false},
  "accounts": [
    {"id": "existing-checking", "type": "checking", "account_class": "Light Blue Account", "personal": true, "status": "OPEN", "opened_at": "2024-01-01", "balance": "0.00", "pending_transactions": false, "in_collections": false}
  ],
  "request": {
    "open_checking": {"account_class": "Blue Account", "confirmed": true},
    "open_savings": {"account_class": "Silver Plus Account", "confirmed": true},
    "close_account_id": "existing-checking"
  }
}
```

Run it by sending that JSON object to the script on standard input. It emits one JSON object on standard output with `checking_opening`, `savings_opening`, `closure`, and `global_blocks`. `eligible: true` means only that the supplied structured facts passed the deterministic policy checks; the executor still must complete all required banking controls and obtain authorization before an action.
