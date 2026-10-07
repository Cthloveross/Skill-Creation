---
name: rho-personal-account-transition
version: 1.0.0
description: Safely handle a verified Rho-Bank customer's request to replace or close a personal checking account and open personal checking and/or savings accounts, including eligibility, linked-savings APY comparisons, funding, and checking closure sequencing.
---

# Rho Personal Account Transition

Use this Skill when a customer wants to close or replace a personal checking account, open personal checking or savings, compare checking/savings combinations, or fund a newly opened savings account.

## Safety and authorization boundary

- Treat an account opening, closure, and transfer as separate consequential actions. Do not perform any of them merely because the customer asked generally to "swap" accounts or expressed an interest in a rate.
- Obtain identity verification before retrieving sensitive account details or taking action. Verify two of the four required identity fields (date of birth, email, phone number, address) against the customer record, then call `log_verification` with the complete retrieved record and a current timestamp. A name and a profile lookup alone are not two verified fields.
- A customer must select the exact checking and/or savings account class and explicitly authorize each opening. Obtain a separate authorization for an immediate internal funding transfer and for account closure.
- Respect `###STOP###` and other explicit stop/end signals: make no banking-tool calls or other actions. State that nothing was opened, transferred, or closed and that a fresh confirmation is required to resume.
- Never expose internal tool names or parameters to the customer. Banking actions are performed by the agent through its normal agent-discoverable tools.

## Required runtime data

After verification, unlock and use `get_all_user_accounts_by_user_id_3847` to retrieve current accounts. For a requested checking closure, also unlock and use `get_bank_account_transactions_9173` for the selected account to establish whether transactions are pending. Use the current account records, not the customer's description, for account IDs, status, balance, dates, and account counts.

The account retrieval data does not by itself establish every opening criterion. In particular, do not assume that a customer has no checking account closed for cause in the last six months, or that no account is in collections, when that information is absent. Obtain an authorized system confirmation; if that cannot be obtained with available tools, do not open the account and route through the appropriate authorized support path rather than guessing.

## Workflow

1. **Authenticate and identify the request.** Locate the customer record only from customer-provided identifying information. Ask for enough additional identity fields to complete two-field verification. Retrieve the current time and log verification only after exact comparisons succeed.
2. **Collect account state.** Retrieve all accounts. Record each account's type, class, status, balance, and opening date. For the proposed closure, inspect transactions for `pending` status. Check any available internal status information for collections, negative balances, and closure-for-cause history.
3. **Evaluate eligibility before offering execution.** Run `scripts/evaluate_account_workflow.py` with current facts to make the documented checks explicit. Its output is an advisory checklist, not an authorization or a banking action.
   - New personal checking: verified; age at least 18; existing personal checking count does not exceed 4 under the stated criterion; no checking closure for cause in the past six months.
   - New personal savings: verified; at least one active/open Rho-Bank checking account with at least 14 days' tenure; fewer than 5 personal savings accounts; no collections and no negative balance on any account.
   - Do not close the customer's existing qualifying checking account before the savings eligibility has been established and the savings opening is completed. A newly opened checking account will not satisfy the 14-day savings-tenure requirement immediately.
4. **Compare options accurately.** Use only documented account terms. Confirm the customer understands opening deposits, ongoing balance requirements, fees, and any paperless requirement. For linked APY, only listed checking/savings pairings qualify, and multiple checking boosts do not stack: only the highest applicable checking boost applies. Credit-card bonuses likewise use only the highest applicable card bonus and only when an eligible active card is actually held.
   - Do not claim an APY boost percentage where the documentation names a pairing but does not provide its percentage.
   - For a customer with no eligible credit card seeking the highest documented rate on a $6,000 savings balance, a supported comparison is Green Account (checking) plus Gold Account (savings): Gold's documented 5.5% base rate plus Green checking's documented +0.75% Gold boost, subject to the Gold account's $5,000 opening deposit and $10,000 ongoing minimum balance. Clearly flag that $6,000 does not meet that ongoing $10,000 requirement.
   - A lower-balance alternative supported by the documents is Evergreen Account (checking) plus Green Account (savings): Green's 4.0% base plus Evergreen's +0.55% linked boost. Green savings has a $100 opening deposit, $500 ongoing minimum, and requires paperless statements. Discuss the checking account's own fees and waiver conditions separately.
   - These are comparisons, not selections. Ask the customer to choose the exact official class strings. Preserve labels exactly, including parenthetical qualifiers such as `Green Account (checking)`. Do not fabricate or normalize a class name.
5. **Open only after confirmation.** Unlock `open_bank_account_4821` and call it only after the applicable eligibility checks are confirmed and the customer has selected and authorized an exact class. Set account type to `checking` or `savings` as appropriate. Confirm each successful result before proceeding.
6. **Arrange savings funding.** Ask whether the customer authorizes an immediate internal transfer and identify the source account and amount. If authorized, validate that source and destination are distinct accounts of the same customer, both are `ACTIVE` or `OPEN`, the amount is positive USD, and the source has sufficient funds. Unlock and call `transfer_funds_between_bank_accounts_7291` only then. If funding is deferred or cannot be transferred internally, explain the 30-day funding window and closure consequence; do not imply that an external deposit was made.
7. **Close the old checking account last, if separately authorized.** Verify that it is `OPEN`, has no pending transactions, and satisfies the balance/early-fee rule. Entry-tier checking classes (Light Blue Account, Light Green Account, Green Fee-Free Account) have a $15 early-closure fee within 30 days and no notice period. If that fee applies, its balance must be at least $15 because it is deducted from that account; otherwise its balance must be exactly $0. Unlock and call `close_bank_account_7392` only when all requirements and authorization are present.
8. **Confirm accurately.** Report only completed actions and their returned details. State whether savings was funded, pending funding, or subject to the 30-day deadline. If a prerequisite failed, explain the specific blocker and do not execute a workaround that was not authorized.

## Script interface

Run:

```json
{"as_of":"2025-11-14","identity_verified":true,"age":34,"checking_closed_for_cause_last_6_months":false,"accounts":[{"account_id":"...","account_type":"checking","account_class":"Light Blue Account","status":"OPEN","balance":"0.00","date_opened":"2025-01-01","pending_transactions":false,"in_collections":false}],"requested":{"checking_class":"Green Account (checking)","savings_class":"Gold Account","close_account_id":"..."}}
```

The script emits JSON with `checking_opening`, `savings_opening`, and `closure` check lists. Each check has `pass` set to `true`, `false`, or `null` for unknown. A `ready` value is true only when all required checks are known and true. Supply facts obtained at runtime; do not place customer IDs, expected results, or a claimed authorization into the script as a substitute for tool-based verification.

See `references/rho_account_policy.md` for the product and policy facts used by this workflow.
