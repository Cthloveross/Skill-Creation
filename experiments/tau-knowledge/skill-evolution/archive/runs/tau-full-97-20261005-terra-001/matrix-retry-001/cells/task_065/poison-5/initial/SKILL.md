---
name: checking-replacement-and-savings-apy-planner
description: Safely handles a request to replace/close a personal checking account while opening personal checking and savings accounts, including a documented highest-APY comparison for a stated savings deposit. Use when the request requires identity verification, account/card closure checks, account-opening eligibility, exact product selection, or linked APY analysis.
---

# Checking Replacement and Savings APY Planner

Use this workflow for account changes only after the customer has requested them. Treat product terms, APY rates, balances, account status, and pending activity as time-sensitive facts: retrieve or confirm them during execution rather than relying on an earlier statement.

## Safety and authorization gates

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

1. Authenticate the customer by having them confirm at least two of date of birth, email, phone number, and address against the customer record. Do not count a name alone as one of these two factors.
2. Obtain the current timestamp with `get_current_time` and create the audit record with `log_verification` only after the two-factor comparison succeeds.
3. Confirm that the authenticated customer owns each account and debit card involved.
4. Before any irreversible action, state the exact account class(es), funding approach, APY assumptions, known fees, and closure consequences, then obtain explicit confirmation. A request to "find the best option" authorizes research and a recommendation, not account opening or closure without confirmation of the resulting exact selection.
5. If an eligibility fact, pending-activity fact, card-refund fact, or required account balance cannot be verified from the available tools and customer confirmation, do not perform the affected action. Explain the missing prerequisite and continue only with safe informational work.

## Required account and card discovery

After verification, unlock and use the relevant agent tools documented for this workflow:

- `get_all_user_accounts_by_user_id_3847(user_id)` for account IDs, account type/class, open status, balance, and opening date.
- `get_debit_cards_by_account_id_7823(account_id)` for cards attached to each checking account that may be closed.
- `open_bank_account_4821(user_id, account_type, account_class)` only after the applicable opening checks and product selection confirmation.
- `close_debit_card_4721(card_id, reason)` only after the card-closure checks below.
- `close_bank_account_7392(...)` only after all closure conditions and any required notice period are met. Use the runtime-disclosed tool contract rather than guessing parameters.
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)` only when the customer explicitly authorizes an immediate internal opening-deposit transfer and all source/destination, available-balance, amount, fee, and confirmation checks pass.

Account lookup is required to establish account counts, statuses, balances, dates, and relevant ownership. Do not infer that an account has no debit cards merely because the customer did not mention one.

## Determine whether the requested sequence is possible

### Personal checking opening

Before opening a replacement checking account, confirm all of the following:

- the customer is verified and authorized;
- the customer is at least 18;
- opening the account will not cause the customer to exceed four personal checking accounts;
- the customer has no checking account closed for cause in the preceding six months; and
- the exact, official checking `account_class` has been selected and confirmed.

Use `account_type: "checking"`. Preserve the official account class exactly as provided in product information; do not shorten or normalize names such as names containing parenthetical qualifiers.

### Personal savings opening

Before opening savings, confirm all of the following:

- the customer is verified and authorized;
- at least one active Rho-Bank checking account exists;
- a qualifying checking relationship has been held for at least 14 days;
- the customer has fewer than five personal savings accounts;
- no account is in collections and no account has a negative balance; and
- the exact, official savings `account_class` has been selected and confirmed.

Use `account_type: "savings"`. Also apply the selected product's disclosed opening deposit, ongoing-balance, and enrollment requirements. For example, do not claim a rate is achievable at the proposed deposit if that deposit misses a stated balance threshold or ongoing requirement.

If the user plans to close the only qualifying checking account, do **not** close it before the savings opening is completed. A newly opened replacement checking account normally will not itself satisfy the 14-day checking-tenure condition. If the existing checking account is not old enough, explain that savings opening must wait until a qualifying checking account reaches 14 days.

## Highest-APY comparison

Use `scripts/select_savings_plan.py` after collecting the applicable product facts from the supplied knowledge and the customer's stated amount/preferences. The script ranks only plans represented in its runtime input; it does not discover products or replace eligibility checks.

For every candidate savings product, record:

- exact savings class;
- the APY tier applicable to the proposed deposit;
- opening and ongoing balance requirements;
- enrollment requirements;
- each eligible linked-checking boost;
- any direct-deposit bonus and its stated condition; and
- any applicable card bonus.

Apply these rules when preparing the script input and explaining its result:

1. Exclude a product from an "achievable" recommendation when the proposed deposit does not meet a disclosed required opening minimum, ongoing minimum, or APY-tier threshold.
2. Include only a checking-savings pair explicitly documented as eligible. Do not assume that similarly named products pair.
3. When multiple qualifying checking accounts could boost the same savings account, include only the highest applicable checking boost; do not add them together.
4. When multiple eligible credit cards could boost the same savings account, include only the highest applicable card bonus; do not add them together.
5. A highest checking boost and a highest credit-card bonus may be combined with base APY and separately documented bonuses when the applicable product terms allow it.
6. Award a direct-deposit bonus only if the product documents that bonus and the customer has confirmed the required setup. Do not substitute direct deposit to a different product for the documented condition.
7. Report both the computed APY and the conditions needed to retain it. If rates are incomplete, conflicting, or no candidate meets the stated deposit constraints, do not call any option the absolute highest; state the limitation.

### Script interface

Run:

```text
python scripts/select_savings_plan.py < input.json
```

The script reads one JSON object from standard input and emits one JSON object on standard output.

Input schema:

```json
{
  "deposit": 0,
  "savings_products": [
    {
      "account_class": "Official Savings Account",
      "base_apy": 0,
      "opening_minimum": 0,
      "ongoing_minimum": 0,
      "tiers": [{"minimum_balance": 0, "apy": 0}],
      "direct_deposit_bonus": 0,
      "requires_direct_deposit": false,
      "requirements": ["optional condition"]
    }
  ],
  "new_checking_options": [
    {"account_class": "Official Checking Account", "opening_minimum": 0, "boosts": {"Official Savings Account": 0}}
  ],
  "existing_checking_options": [
    {"account_class": "Official Checking Account", "boosts": {"Official Savings Account": 0}}
  ],
  "checking_opening_funds": 0,
  "credit_card_bonuses": {"Card name": 0},
  "direct_deposit_confirmed": false
}
```

APY values are percentage points (for example, `4.0` means 4.0%). `tiers` is optional; when supplied, the highest tier whose `minimum_balance` does not exceed the deposit is used. `ongoing_minimum` is treated as an eligibility constraint. Omit an unknown product minimum rather than inventing one. Include only active/eligible existing checking accounts and only credit cards that the customer currently holds in good standing.

The result contains `eligible_plans`, sorted highest to lowest, with base, checking, card, and direct-deposit components plus unmet-condition exclusions. Validate that the selected plan's `total_apy` equals the displayed components, its selected checking source appears in the input, and all stated conditions are communicated to the customer.

## Closing the outgoing checking account

Keep the outgoing checking account open until the replacement/savings sequence can safely proceed. Then evaluate closure using fresh account data.

For a Light Blue, Light Green, or Green Fee-Free checking account:

- the early-closure fee is $15 if closure occurs within 30 days of opening;
- no advance notice is required;
- status must be OPEN;
- there must be no pending account transactions; and
- if the early fee applies, the account balance must be at least the fee; otherwise its balance must be exactly $0.

For a Light Blue account specifically, calculate whether the 30-day window has elapsed from its retrieved opening date; do not rely on an approximate customer recollection. If the fee applies and the balance is insufficient, do not close the account. Explain that the fee is deducted from the account balance and no alternate payment method is available.

Before closing any checking account, retrieve its debit cards. All associated debit cards must be closed first. For each card, confirm ownership, that status is ACTIVE or PENDING, no pending/processing transactions, no pending refunds (or the documented written acknowledgement for linked-account credit), and at least 14 days since `date_issued`. The age requirement is bypassed only for `lost`, `stolen`, and `fraud_suspected`; it is not bypassed merely because the checking account is closing. Use reason `account_closing` only when that is the confirmed reason. If a card cannot yet be closed, the linked checking account cannot be closed.

After every closure prerequisite is met, call the closure tool and confirm the outcome. Do not promise a closure until the tool succeeds.

## Savings funding and completion

After a savings account is successfully opened:

- If an immediate internal transfer was explicitly authorized, transfer only the confirmed required amount after rechecking the source's available balance and the destination account ID.
- If funding will be external or is deferred, state the product's minimum opening deposit and tell the customer that the new savings account must be funded within 30 days or it will be closed.
- Clearly distinguish an externally planned deposit from a completed deposit.
- Summarize newly opened account details, computed APY conditions, whether funding is pending, the outgoing account/card status, and any action still required.

## Observable stop conditions

Do not perform the blocked action if identity verification fails, ownership is unclear, a selected class is unconfirmed, an account-count limit would be exceeded, savings tenure is under 14 days, collections/negative balance exists, a mandatory opening requirement cannot be met, card closure prerequisites fail, account closure balance/status/pending conditions fail, or tool results are unsuccessful. State the specific condition and the next safe resolution step.
