---
name: checking-replacement-and-savings-apy-plan
description: Safely authenticate a Rho-Bank customer, evaluate a checking-account replacement and personal-savings opening, calculate a documented highest-APY recommendation, and sequence any account closure, opening, and funding actions. Use for customers who want to close or replace checking while opening savings or maximizing savings APY.
---

# Checking replacement and savings APY plan

Use this Skill when a customer wants to replace/close a checking account, open personal savings, or asks which documented checking/savings/card combination produces the best savings APY. It separates (1) factual recommendation, (2) eligibility, and (3) irreversible banking actions. Never treat a recommendation or script output as an authorization to act.

## Required runtime facts

Obtain and use live facts rather than customer estimates whenever a normal banking tool is available:

- authenticated user ID and a logged identity verification;
- all bank accounts, including ID, type, class, status, balance, and opening date;
- transaction history for each account proposed for closure, to detect pending items;
- active credit cards, if calculating a currently applicable card bonus;
- the customer's intended savings funding amount, source, and explicit authorization if an internal transfer is requested.

The account lookup and transaction-history tools are discoverable internal tools. Unlock them before use:

- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_bank_account_transactions_9173(account_id)`

The action tools are also discoverable internal tools:

- `open_bank_account_4821(user_id, account_type, account_class)`
- `close_bank_account_7392(account_id)`
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`

Use the exact full official class name ending in `Account` for every opening. Do not expose tool names or parameters to the customer.

## 1. Authenticate before revealing or changing account information

1. Locate the profile using a supplied name or email if needed.
2. Have the customer confirm at least two profile fields among date of birth, email, phone number, and address. A lookup result alone is not customer confirmation.
3. Retrieve the complete profile needed for the audit record, call `get_current_time`, then call `log_verification` with all required profile fields, user ID, and that timestamp.
4. Only after successful logging should you retrieve or discuss nonpublic account details or perform account actions.

If two fields cannot be confirmed, do not perform the account actions. Request the missing verification information without disclosing it.

## 2. Retrieve and validate live account state

After verification, retrieve all accounts. For a closure candidate, retrieve its transaction history too. Treat a transaction with `status: pending` as a pending transaction even when the customer believes none exists.

For a proposed **personal checking** opening, verify:

- customer is verified;
- customer is at least 18;
- customer will not exceed four personal checking accounts;
- no checking account was closed for cause in the past six months.

For a proposed **personal savings** opening, verify:

- customer is verified;
- at least one active Rho-Bank checking account exists and has been held for at least 14 days;
- customer has fewer than five personal savings accounts;
- no account is in collections and no account has a negative balance.

Do not infer tenure, balances, account status, collections, or the account count from the customer's recollection. If an eligibility fact is not available from records or a supported process, explain that the opening cannot yet proceed.

## 3. Sequence a replacement safely

When the existing checking account is needed to satisfy the savings account's active-checking/14-day requirement, do **not** close it first. Subject to all eligibility requirements, use this order:

1. confirm the exact recommended checking and savings classes with the customer;
2. open the replacement checking account;
3. open the savings account while the qualifying existing checking account remains active;
4. arrange savings funding only with an authorized valid source;
5. close the old checking account only after all closure requirements are met.

This order avoids making the customer ineligible for the savings account. It is still necessary to recheck applicable account-count limits before every opening.

## 4. Recommend APY accurately

Build the recommendation from applicable product documentation and the customer’s actual amount, not from an advertised headline alone.

For each feasible savings option:

1. Check its opening deposit and ongoing balance requirements against the amount the customer expects to maintain. A card-related reduced minimum applies only while the qualifying active card is actually held and linked.
2. Start with the applicable base rate or balance tier.
3. Identify eligible linked checking boosts for that specific savings class. If several active checking accounts qualify, add **only the highest** applicable checking boost.
4. Identify bonuses from the customer’s active credit cards. Add **only the highest** applicable credit-card bonus; credit-card bonuses never stack with one another.
5. Add a separately documented relationship, tier, or direct-deposit bonus only when its precise conditions are met. A checking boost and the one highest credit-card bonus may stack with such separate bonuses.
6. State material tradeoffs, such as required balances, opening deposits, account fees, and conditions for the advertised benefit.

Do not count a proposed or hypothetical credit card as active. If the customer asks for the best possible combination including a card but there is no supported card-application action, distinguish clearly between:

- the best **currently attainable** rate using the customer’s active products; and
- a **projected** rate contingent on approval, activation, linkage, and any balance requirement of a separate card product.

Do not claim to open a credit card, apply a projected card benefit, or report an exact maximum if relevant product terms or eligibility conditions are unavailable. A customer delegation to choose a combination does not eliminate the requirement to state the selected exact account classes before opening them.

## 5. Documented product reasoning relevant to these requests

Use the original product documents as the authority. The following points are useful cross-checks, not substitutes for checking all conditions:

- Gold Account has a 5.5% base APY and a normal $10,000 minimum balance. An active linked Gold Rewards Card reduces that balance requirement to $5,000 and carries the stated 0.025% relationship benefit. Green Account (checking) has a documented +0.75% boost for Gold savings, but also has a $22.50 monthly maintenance fee unless its $1,350 minimum daily balance waiver condition is met.
- Green Account (savings) has a 4.0% base APY, a $100 opening deposit, and a $500 ongoing minimum. Evergreen Account (checking) has a documented +0.55% boost for Green savings. The eligible-card documentation must be used to identify the single highest active card bonus.
- Silver Plus uses a 3.0% Tier 1 rate below its $15,000 Tier 2 threshold, has a $1,000 opening deposit and $2,500 ongoing minimum, and has separately documented direct-deposit and relationship features that must be conditionally verified.
- Gold Plus, Platinum, Platinum Plus, and Diamond Elite have stated opening and/or ongoing balance requirements. Do not recommend them as attainable with a smaller stated amount merely because their headline APY is higher.

If documentation conflicts internally, do not silently select the more favorable reading. Explain the uncertainty and use a supported clarification or escalate only when necessary.

## 6. Savings funding

After a savings account opens, ask whether the customer authorizes an immediate opening-deposit transfer from a specified checking account.

Before calling the transfer tool, verify that:

- source and destination are distinct accounts belonging to the customer;
- both statuses are `ACTIVE` or `OPEN`;
- the source has sufficient available funds;
- the amount is positive USD and meets the relevant required opening deposit; and
- the customer authorized the exact source and amount.

Then call `transfer_funds_between_bank_accounts_7291`. Do not invent an internal source merely because the customer says they have savings elsewhere. If no authorized internal transfer is requested or possible, explain that the account must be funded within 30 days by internal transfer or external deposit or it will close.

## 7. Close the former checking account only when allowed

For closure, live records must show:

- status `OPEN`;
- no pending transactions; and
- either a zero balance or enough balance to pay an applicable early-closure fee.

For a Light Blue Account (an entry-tier account), a $15 early-closure fee applies when closed within 30 days. If that fee applies and the balance is below $15, closure cannot proceed because there is no alternate payment method. If it does not apply, the balance must be exactly $0. Call `close_bank_account_7392` only after these checks pass.

If a pending item, status issue, early-closure balance issue, or missing tenure prevents closure, do not call the closure tool. Tell the customer the specific blocker and the next safe step.

## 8. Completion response

After successful actions, state only the relevant confirmation: opened account class(es), funding status or 30-day funding deadline, transfer status if one was made, and closure completion if applicable. Do not claim that a pending or unsupported card benefit is active.

## Optional deterministic validator

`scripts/evaluate_account_plan.py` evaluates supplied account facts for opening, Light Blue closure, and internal-transfer prerequisites. It performs no banking actions and cannot verify information that was omitted from its JSON input.

### JSON input schema

```json
{
  "today": "YYYY-MM-DD",
  "identity_verified": true,
  "customer_age": 18,
  "checking_closed_for_cause_last_6_months": false,
  "has_collections": false,
  "has_negative_balance": false,
  "accounts": [
    {
      "account_id": "runtime account id",
      "account_type": "checking or savings",
      "account_class": "official full class name",
      "status": "OPEN",
      "balance": "0.00",
      "date_opened": "YYYY-MM-DD",
      "has_pending_transactions": false
    }
  ],
  "proposed": {
    "open_checking": false,
    "open_savings": false,
    "close_account_id": null,
    "savings_opening_deposit": "0.00",
    "transfer": null
  }
}
```

`transfer`, when supplied, is an object with `source_account_id`, `destination_account_id`, `amount`, and `customer_authorized`. The script writes a JSON object with `checking_opening`, `savings_opening`, `closure`, `transfer`, and ordered `safe_sequence` fields. Each validation contains `allowed`, `blockers`, and `warnings`.

Run it against a JSON file assembled from live records:

```sh
python3 scripts/evaluate_account_plan.py < plan.json
```

Treat `allowed: false` as a hard stop for that action. Recheck live records immediately before using any action tool.
