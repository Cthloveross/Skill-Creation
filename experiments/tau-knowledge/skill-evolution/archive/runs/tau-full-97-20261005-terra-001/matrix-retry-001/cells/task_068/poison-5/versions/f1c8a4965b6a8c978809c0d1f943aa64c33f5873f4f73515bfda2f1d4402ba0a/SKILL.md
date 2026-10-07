---
name: rho-account-replacement-and-yield-planning
description: Safely handle a Rho-Bank request to replace or close a personal checking account, open and fund a personal savings account, and recommend a documented APY configuration subject to stated requirements such as travel-insurance coverage. Use for banking requests that combine account servicing, product comparison, and account-opening or closure decisions.
---

# Rho Account Replacement and Yield Planning

## Purpose and safety boundary

Use this workflow when a customer wants to replace or close a checking account, open a savings account, fund it internally, and/or select products for the highest documented APY. Make recommendations from the current product terms and customer facts, but do not invent product features, rates, eligibility, approvals, coverage, or available tools.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

A lookup by name, email, or user ID is not identity verification. Authenticate by having the customer confirm at least two independent profile fields, retrieve the matching profile, obtain the current time, and log the verification record. Do not repeat profile data merely to solicit confirmation.

## Product-information questions

Treat a question about a product feature as a documentation lookup question, not as a reason to guess or escalate. Before saying a feature is unavailable or undocumented:

1. Locate the current terms for the exact product type and class. Distinguish similarly named checking and savings products.
2. Find the requested feature in the terms and answer with its documented value and qualifiers.
3. State conditional availability exactly. In particular, do not convert an "up to" early-direct-deposit timeframe into a guarantee, and explain any documented payer-submission dependency.
4. If multiple product documents conflict, report the conflict rather than selecting a favorable value without explanation.
5. Say the feature is undocumented only after reviewing the relevant available terms and finding no answer.

For example, an early-direct-deposit question must be answered from the exact checking account's terms before discussing account closure, asking for further authorization, or transferring to a human. A customer-requested human handoff may still be completed after the accurate answer. Its summary must accurately describe the answer already provided and must not characterize documented terms as unavailable.

## Available banking tools

Unlock an agent-discoverable tool before calling it. Use only the documented signature and required arguments exposed after unlocking:

- `get_all_user_accounts_by_user_id_3847(user_id)` retrieves account ID, type, class, status, balance, and opening date.
- `get_bank_account_transactions_9173(account_id)` retrieves posted and pending transactions for an account.
- `open_bank_account_4821(user_id, account_type, account_class)` opens a confirmed checking or savings product.
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` transfers funds internally only after transfer preconditions pass.
- `close_bank_account_7392(...)` closes an account only after all closure checks pass. Inspect its documentation after unlocking and use its required arguments exactly.

There is no documented agent tool here for credit-card application. Do not claim that a card was applied for, approved, opened, linked, or activated unless an available documented tool performed that action. If applicable, explain the current documented application channel and conditions without guaranteeing approval.

## Obtain and validate facts before an action

1. Authenticate the customer and log verification with the current timestamp.
2. Retrieve all bank accounts for the authenticated customer.
3. Identify the exact account requested for closure and retrieve its transactions. A pending transaction blocks closure.
4. Obtain facts that account retrieval does not establish, including collections status, checking accounts closed for cause in the preceding six months, the selected product classes, and credit-card eligibility or approval.
5. State relevant fees, balance requirements, funding requirements, and restrictions before requesting authorization.
6. Obtain explicit, final authorization for each irreversible action immediately before that action.

If a prerequisite is missing, unknown, or fails, do not execute the affected action. Explain the specific blocker and continue only with independent informational portions of the request.

## Eligibility checks

### Personal checking opening

Before opening a personal checking account, confirm all of the following:

- identity is verified;
- customer is at least 18 years old;
- the opening will not cause the customer to exceed four personal checking accounts;
- no checking account was closed for cause in the previous six months;
- the customer has explicitly selected the exact full official checking `account_class`, ending in `Account`.

Use `account_type: "checking"`. Do not close an existing account merely to create space unless the customer gave final closure authorization and the closure prerequisites pass.

### Personal savings opening

Before opening a personal savings account, confirm all of the following:

- identity is verified;
- customer has at least one active Rho-Bank checking account;
- a checking relationship has been open for at least 14 days;
- customer has fewer than five personal savings accounts;
- no account is in collections and no account has a negative balance;
- the customer explicitly selected the exact full official savings `account_class`, ending in `Account`.

Use `account_type: "savings"`. Preserve an existing qualifying checking relationship until savings eligibility has been assessed and the savings account is open. A checking account opened today does not meet the 14-day tenure requirement.

## Closing an entry-tier checking account

For an entry-tier account such as Light Blue, verify before closure:

- status is `OPEN`;
- no transactions are pending;
- whether closure is within 30 days of opening;
- if within 30 days, the balance covers the $15 early-closure fee, which is deducted from the account and has no alternative payment method;
- if no early fee applies, current holdings are $0.

The customer saying they moved money out is not a substitute for account and transaction checks. If a fee applies but the balance is less than the fee, do not close. If no fee applies but a balance remains, do not close until it is resolved. Reconfirm the exact account and final closure authorization immediately before calling the closure tool.

## Savings funding

After savings opening, ask whether the customer authorizes an immediate opening deposit from a specified checking account. Before an internal transfer, verify:

- source and destination belong to the authenticated customer;
- IDs are valid and different;
- both accounts are `ACTIVE` or `OPEN`;
- the source has sufficient available funds for a positive USD amount while preserving disclosed requirements;
- source, destination, amount, applicable fees, and explicit authorization are all confirmed.

Call the transfer tool only after these checks. Verify the result and avoid duplicate transfers. A stated savings goal or saved amount is not transfer authorization.

If the customer declines immediate funding, tell them that the savings account must be funded within 30 days by internal transfer or external deposit or it will be closed.

## APY recommendation method

Use only current documented figures. Do not treat an advertised rate as achievable unless the customer meets all of its stated conditions.

1. Build candidate combinations from current savings, checking, and card terms plus customer constraints.
2. Exclude savings products whose applicable opening or ongoing balance requirement exceeds the intended balance.
3. Start each candidate with the savings base APY.
4. Add at most one documented linked-checking boost: only a qualifying listed same-profile pairing is eligible, and only the highest applicable checking boost applies.
5. Add at most one documented card bonus: only an active, qualifying same-profile card can be counted, and only the highest card bonus applies.
6. Include relationship or other bonuses only when their separate eligibility is documented.
7. If travel insurance is required, include only cards whose supplied terms document that coverage and clearly state activation, card-payment, covered-event, documentation, limit, and exclusion conditions.
8. Explain that card approval, linkage, account status, and good standing remain conditions rather than guarantees.

Use `scripts/rate_selector.py` to rank an explicitly supplied, documented candidate list. It performs arithmetic and basic filtering only; the executor must obtain product facts from current terms and must independently validate all linkage, approval, and account-status assumptions.

## Recommended execution order

1. Authenticate and log verification.
2. Retrieve accounts and transactions; assess closure, opening, and transfer prerequisites.
3. Answer any product-feature questions from the exact current terms.
4. Present the documented recommendation, assumptions, balance requirements, and any credit-card coverage conditions or unknown facts.
5. Obtain explicit selection of each checking and savings class and explicit authorization for each requested banking action.
6. Open checking only if eligible and authorized.
7. Open savings while a qualifying seasoned checking relationship remains active, only if eligible and authorized.
8. Fund savings only if separately authorized; otherwise state the 30-day funding deadline.
9. Recheck closure conditions, obtain final closure authorization, and then close the specified account.
10. Report actual completed actions, funding result or deadline, and any remaining customer actions.

If the checking-account limit prevents opening before closure, do not bypass the limit. Close an account first only after all closure conditions and final authorization are satisfied, then reassess checking eligibility.

## Helper scripts

### `scripts/account_eligibility.py`

Reads one JSON object from stdin and emits one JSON object to stdout. Input:

```json
{
  "identity_verified": true,
  "as_of": "YYYY-MM-DD",
  "age_years": 18,
  "checking_closed_for_cause_last_6_months": false,
  "accounts": [
    {
      "account_id": "string",
      "account_type": "checking|savings",
      "account_class": "string",
      "status": "OPEN|ACTIVE|...",
      "balance": "decimal",
      "date_opened": "YYYY-MM-DD",
      "in_collections": false
    }
  ]
}
```

`checking_closed_for_cause_last_6_months` and `in_collections` may be `null` or absent when unknown. The result contains separate checking and savings eligibility, blockers, review items, counts, and qualifying checking IDs. Unknown required facts are review items, never passing conditions. The script is advisory and does not authorize action.

### `scripts/rate_selector.py`

Reads one JSON object from stdin and emits one JSON object to stdout. Input:

```json
{
  "amount": "decimal",
  "require_travel_insurance": true,
  "candidates": [
    {
      "name": "documented configuration name",
      "base_apy": "decimal percentage points",
      "minimum_balance": "decimal",
      "checking_boost": "decimal percentage points",
      "card_bonus": "decimal percentage points",
      "card_has_travel_insurance": true
    }
  ]
}
```

The output provides eligible candidates sorted by calculated APY, excluded candidates with reasons, and the best candidate or `null`. Validate that supplied boosts are the single highest applicable boosts and that all non-arithmetic conditions are satisfied before communicating a recommendation.
