---
name: bank-account-transition-and-savings-yield-planning
description: Safely handle a request to close or replace a personal checking account and open/fund a personal savings account, including eligibility checks, product comparison, linked-account APY analysis, and normal banking-tool execution. Use when a customer asks to change checking accounts, open savings, optimize savings APY, or combine these requests.
---

# Bank Account Transition and Savings Yield Planning

Use this workflow for account closures, opening personal checking or savings accounts, transfers used to fund savings, and recommendations about linked checking/savings APY. Do not treat a recommendation, product comparison, or a customer's stated preference as authorization to perform a banking action.

## Safety and authentication gate

Before **any** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

1. Identify the customer through the available user lookup tool.
2. Authenticate by having the customer confirm at least two of the four profile fields: date of birth, email, phone number, and address. Do not expose profile fields as proof or ask leading questions that disclose them.
3. After two fields are independently confirmed, retrieve the current timestamp and call `log_verification` with the complete profile record and timestamp.
4. If authentication is incomplete, do not close, open, or transfer funds. Explain what two verification fields are needed and continue only with general, non-account-specific information.
5. A supplied name, a prior lookup result, or a statement that the customer owns an account is not identity verification.

## Gather authoritative account facts

After authentication, retrieve all bank accounts using the documented agent tool `get_all_user_accounts_by_user_id_3847` when it is available in the runtime (unlock it first if the runtime requires unlocking a discoverable agent tool). Collect account ID, type, class, status, balance, and opening date.

Retrieve transaction history with `get_bank_account_transactions_9173` when necessary to establish whether an account has pending transactions. If a documented lookup tool cannot be accessed in the current runtime, state that the required fact cannot be verified and do not perform the dependent banking action. Never infer account status, tenure, balance, account count, closure history, collections status, or pending transactions from the customer's recollection alone.

For a request that combines several actions, evaluate each action independently and only execute an action whose prerequisites are satisfied. A blocked closure does not automatically block an otherwise eligible opening, but all prerequisites for the opening still apply.

## Evaluate a checking-account closure

For the account the customer wants closed:

1. Confirm it belongs to the authenticated customer and that the customer explicitly authorizes closure of that exact account.
2. Verify it is `OPEN` and has no pending transactions.
3. Determine the tier-specific early-closure fee from the account class and account age.
4. Verify that the balance is zero when no early-closure fee applies. When a fee applies, verify the account balance is at least that fee because the fee is deducted from the account; do not arrange an alternative payment method.
5. Clearly disclose any fee and obtain confirmation if required by the applicable normal workflow.
6. Unlock and call `close_bank_account_7392` only after all closure requirements are met.
7. If the balance must first be moved, use the normal transfer workflow only after the customer has authorized the source, destination, and positive USD amount and both accounts are active/open. Do not initiate a duplicate transfer. Recheck the account before attempting closure.

If a requirement is unverified or failed, do not close the account. Give the specific blocker without asserting that the account is eligible or ineligible based on missing evidence.

## Evaluate opening a personal checking account

Before calling `open_bank_account_4821` for a checking account, verify all of the following:

- verified customer identity;
- age at least 18;
- no more than four existing personal checking accounts;
- no checking account closed for cause in the preceding six months;
- explicit customer selection of an exact account class whose official name ends in `Account`.

Discuss relevant opening and ongoing-balance requirements, maintenance fees and waiver conditions, and requested perks before the customer selects a product. A product recommendation is not a product selection. Once eligibility and the exact selection are confirmed, call `open_bank_account_4821(user_id, "checking", account_class)` using the official full class string.

## Evaluate opening and funding a personal savings account

Before opening savings, verify all of the following:

- verified customer identity;
- at least one active Rho-Bank checking account;
- that qualifying checking relationship has been open at least 14 days;
- fewer than five existing personal savings accounts;
- no accounts in collections and no negative balances;
- explicit customer selection of an exact official savings account class ending in `Account`.

Also discuss the product's initial-deposit minimum, ongoing balance requirement, fees, and whether the proposed balance can actually satisfy the product's conditions. Do not describe a rate as attainable if the available balance fails an ongoing qualification threshold.

After eligibility and selection are established, use `open_bank_account_4821(user_id, "savings", account_class)`. Then ask whether the customer authorizes an immediate opening-deposit transfer from a specific checking account. If yes, validate that source and new destination are distinct customer-owned accounts in `ACTIVE` or `OPEN` status, validate sufficient available funds and a positive USD amount, then call `transfer_funds_between_bank_accounts_7291`. Confirm the result and check for duplicate transfers. If the customer declines immediate funding, tell them they have 30 days to fund the account by internal transfer or external deposit or it will be closed.

## APY comparison and recommendation method

1. Use only product terms supported by current documentation: base APY, opening and ongoing balance requirements, product fees, and qualifying linked-account or credit-card bonuses.
2. Eliminate products that the customer cannot fund or maintain under the stated scenario. Distinguish an opening-deposit minimum from a higher ongoing threshold.
3. For every feasible savings candidate, identify active qualifying checking pairings and applicable credit-card bonuses under the same customer profile.
4. Apply only documented pairings. Within checking-based boosts, use only the highest applicable boost; within credit-card bonuses, use only the highest applicable bonus. Do not stack multiple bonuses from the same category. Add the selected checking boost, selected card bonus, and separately documented additive bonuses to the base APY only where documentation permits it.
5. Consider maintenance fees and checking balance needed to obtain a fee waiver when comparing economically meaningful outcomes. Explain ties and tradeoffs rather than inventing a preference.
6. Use `scripts/rank_savings_yields.py` for deterministic ranking when the documented figures have been assembled. Its result is analysis only; it cannot authorize or execute banking actions.
7. Present the recommendation and obtain the customer's explicit selection of both account classes before opening anything.

## Tool and failure handling

- Unlock documented internal agent tools before calling them if the runtime requires it. Call banking tools directly; never ask the customer to invoke internal tool names or provide tool parameters.
- Treat a tool error as a failed action. Do not claim completion, do not retry an action whose result is `UNKNOWN`, and re-read the relevant state before any safe follow-up.
- If identity, authority, account ownership, eligibility, account information, or transaction state cannot be verified with available tools, stop before the affected action and explain the missing prerequisite.
- Preserve the customer's funds and existing account if a closure, opening, or funding prerequisite is not met.

## Required customer-facing completion

After successful actions, state the account(s) affected, selected product class(es), relevant fee/funding status, and any funding deadline. For an APY recommendation, state the assumptions and that rates, linked-product eligibility, and balances must remain qualifying; do not guarantee future earnings.

## Yield-ranking helper

Run the packaged helper by sending JSON on stdin and reading JSON from stdout:

```text
python3 scripts/rank_savings_yields.py < candidates.json
```

Input schema:

```json
{
  "balance": "positive USD decimal",
  "products": [
    {
      "id": "stable product label or ID",
      "base_apy": "annual percentage decimal",
      "minimum_opening_deposit": "USD decimal, optional",
      "minimum_ongoing_balance": "USD decimal, optional",
      "eligible": true,
      "checking_bonuses": [{"id": "source", "apy": "percentage"}],
      "credit_card_bonuses": [{"id": "source", "apy": "percentage"}],
      "other_additive_bonuses": [{"id": "source", "apy": "percentage"}],
      "notes": ["optional documented qualification note"]
    }
  ]
}
```

The helper emits feasible and ineligible candidates, selected highest bonus per non-stacking category, effective APY, a one-year APY-based estimate for the supplied stable balance, and all tied best candidates. Supply only verified product data and mark unknown eligibility as `false` rather than assuming it is true. Validate that the response has `valid: true`, review the `ineligible` reasons, and manually verify that every supplied pairing and bonus is documented before communicating or acting on the ranking.
