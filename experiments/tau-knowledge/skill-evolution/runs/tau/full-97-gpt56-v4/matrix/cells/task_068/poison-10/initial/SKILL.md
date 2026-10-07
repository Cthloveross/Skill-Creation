---
name: checking-and-savings-transition
version: 1.0.0
description: Handle a request to close or replace a personal checking account, compare checking and savings options, and (only after verification and eligibility checks) open, fund, or close accounts using the documented banking tools. Use when a customer wants a checking upgrade, early direct deposit, or the best eligible savings APY.
---

# Checking and Savings Transition

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety

Use this workflow for account-product advice, checking-account closure, and opening/funding personal checking or savings accounts. Product advice may be provided from documented facts before identity verification, but do **not** retrieve protected account details, log verification, open or close an account, or transfer funds until the required checks pass.

Never infer an account ID, status, balance, tenure, pending activity, verification status, ownership, a customer selection, or a required confirmation from a product recommendation. If a required fact is unavailable, explain what is needed and pause the affected action.

## Inputs to gather

1. The customer’s stated objective and requested actions (for example: close an old checking account, open a replacement, open savings later).
2. Customer identity: have the customer provide and confirm at least two of the four profile fields—date of birth, email, phone number, and address. Do not reveal profile fields merely to solicit confirmation.
3. Exact desired new account class, unless the customer is only seeking advice.
4. For a savings-opening request, the intended funding amount and whether an immediate transfer is authorized.
5. After identity verification, the customer’s accounts, statuses, dates opened, balances, pending transactions, and any eligibility-relevant account condition.

## Identity and authority procedure

1. Locate the customer record using an identifier the customer supplied, such as name or email. Use `get_user_information_by_name`, `get_user_information_by_email`, or `get_user_information_by_id` as appropriate.
2. Ask the customer to supply two profile fields. Compare the supplied values with the retrieved record.
3. Obtain the current timestamp using `get_current_time`, then call `log_verification` with the complete retrieved profile and timestamp only after two fields match.
4. Confirm the caller is the account holder and has authorized the requested account action.
5. If the customer cannot complete verification, provide general product information only and do not take account action.

## Account discovery and eligibility

After identity is verified, unlock and call `get_all_user_accounts_by_user_id_3847` with the authenticated user ID. Use the returned account ID, type, class, status, balance, and opening date; do not rely on customer recollection.

For a proposed **personal checking** account, verify all of the following before opening:

- customer is verified;
- customer is at least 18;
- customer would not exceed four personal checking accounts;
- customer has no checking account closed for cause within the preceding six months;
- the exact `account_class` is selected and is the full official name ending in `Account`.

For a proposed **personal savings** account, verify all of the following before opening:

- customer is verified;
- the customer has at least one active Rho-Bank checking account held for at least 14 days;
- the customer has fewer than five personal savings accounts;
- no account is in collections or has a negative balance;
- the exact savings `account_class` is selected and is the full official name ending in `Account`.

If closure of the only eligible checking account would prevent a planned savings opening, explain the sequencing issue. Do not claim a replacement account immediately satisfies a 14-day savings-tenure requirement unless its actual opening date shows it does.

## Product comparison method

Use only current documented product facts. Match each checking account to a savings account only when that exact pairing is documented as eligible. Do not stack checking boosts: if multiple eligible checking accounts exist, only the highest applicable checking boost applies. Credit-card bonuses similarly use only the highest applicable card bonus, but a valid checking boost and the applicable highest card bonus may be additive if documented.

For each savings candidate:

1. Reject it when the proposed savings amount cannot satisfy its required opening deposit or ongoing-balance requirement for the benefits being compared.
2. Start with the documented base APY.
3. Add the highest documented applicable checking boost, if its pairing and ownership conditions are met.
4. Add the highest documented applicable credit-card bonus only if an eligible active card under the same profile has been confirmed.
5. State assumptions, qualifying balances, and direct-deposit timing separately. A checking account’s early-direct-deposit feature is contingent on the payer sending funds early.

For repeatable comparisons, prepare documented candidate data and run:

```sh
python3 scripts/select_account_combination.py <<'JSON'
{
  "savings_amount": "25000",
  "savings_products": [],
  "checking_options": [],
  "credit_card_bonuses": []
}
JSON
```

The script reads JSON from standard input and emits JSON to standard output. It never performs banking actions. Populate the arrays from the current account documentation and verified product holdings; do not hardcode a customer’s account IDs, balances, selections, or an expected recommendation into the package.

When an unverified customer asks for the best documented combination, clearly label the result as a product comparison, not an account-opening decision. Present the recommended eligible combination, its effective APY calculation, the balance conditions, and its early-direct-deposit timing. Ask for selection only if they want to proceed.

## Closing a personal checking account

Before closing, confirm all of the following from verified account data:

- the exact account belongs to the authenticated customer;
- account status is `OPEN`;
- there are no pending transactions (unlock and use `get_bank_account_transactions_9173(account_id)` when needed);
- current holdings are $0, except that if an applicable early-closure fee applies, the balance must at least cover that fee because it is deducted from the account;
- the account tier, applicable early-closure window and fee, and notice period have been determined and disclosed;
- the customer still wants closure after the applicable fee and notice information is provided.

For entry-tier checking accounts, including Light Blue Account, the documented early-closure fee is $15 if closed within 30 days and the notice period is 0 days. Do not assume the fee applies without checking the actual opening date against the current date. If the balance is nonzero and no fee applies, do not close it until the balance is resolved. If a closure prerequisite fails, explain the blocking condition and do not call the closure tool.

After all checks and confirmation, unlock `close_bank_account_7392` and call it with the verified account ID. Report the returned outcome; do not retry an ambiguous or unknown result.

## Opening and funding accounts

Only after the relevant eligibility checklist passes and the customer has selected the exact official account class:

1. Unlock `open_bank_account_4821`.
2. Call it with the authenticated user ID, `account_type` of `checking` or `savings`, and the selected full official `account_class`.
3. For a new savings account, ask whether the customer authorizes an immediate opening-deposit transfer. If they decline, explain the documented 30-day funding deadline and possible closure if it remains unfunded.
4. If an immediate transfer is authorized, unlock `transfer_funds_between_bank_accounts_7291` and verify both account statuses are `ACTIVE` or `OPEN`, ownership is the same customer, source and destination differ, the USD amount is positive, and available funds cover the amount. Call it only after these checks.
5. Confirm the result and funding status. Never represent a transfer recommendation as a completed transfer.

## Completion response

Separate completed actions from recommendations and blocked actions. Include the selected product, material rate/fee/limit conditions, transaction or account result returned by a tool, and any next required customer decision. If no banking action can safely proceed, state the missing prerequisite and offer the next verification or selection step.
