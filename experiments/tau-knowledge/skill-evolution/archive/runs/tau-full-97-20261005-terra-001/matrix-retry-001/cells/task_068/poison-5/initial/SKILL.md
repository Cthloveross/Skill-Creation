---
name: rho-account-replacement-and-yield-planning
description: Safely handle a Rho-Bank request to replace a personal checking account, open and fund a personal savings account, and recommend the highest documented APY combination subject to the customer's stated product constraints (including documented travel-insurance needs). Use when account opening, closure, internal funding, and APY-product comparison are all in scope.
---

# Rho Account Replacement and Yield Planning

## Purpose and boundaries

Use this workflow for a customer who wants to close or replace a personal checking account and/or open a savings account, especially where the customer asks for the best yield. It coordinates recommendations with operational eligibility, but it does not invent products, rates, account-opening requirements, credit decisions, or tools.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do not treat a lookup by name, email, or user ID as identity verification. Authenticate by having the customer confirm at least two independent profile fields, then retrieve the profile, obtain the current time, and create the required verification audit record. Do not repeat profile data to the customer merely to solicit confirmation.

## Applicable tools

Unlock an agent-discoverable tool before calling it. Use only the documented signatures:

- `get_all_user_accounts_by_user_id_3847(user_id)`: retrieve account ID, type, class, status, balance, and opening date.
- `get_bank_account_transactions_9173(account_id)`: retrieve posted and pending transactions for a particular account.
- `open_bank_account_4821(user_id, account_type, account_class)`: open the confirmed checking or savings product.
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`: transfer internally only after all transfer preconditions are met.
- `close_bank_account_7392(...)`: close an account only after the applicable closure checks pass. Inspect the tool documentation after unlocking and use its required arguments exactly.

There is no documented agent tool here for applying for a credit card. Do not imply that a card was applied for, approved, opened, linked, or activated unless an available, documented tool actually performs that action. If the customer wants a card, explain the documented application conditions and direct them to the documented application channel.

## Information to obtain before acting

1. Authenticate the customer and log verification using the current timestamp.
2. Retrieve all bank accounts for the authenticated `user_id`.
3. Identify the exact account the customer wants closed. Confirm its account ID and obtain a final confirmation immediately before the irreversible closure.
4. Retrieve transactions for that account. Treat any `pending` transaction as a closure blocker.
5. Obtain or verify any fact that account retrieval cannot establish, including:
   - checking accounts closed for cause in the prior six months (for a new checking account);
   - collections status, if it cannot be determined from account status;
   - the customer's selected checking and savings account classes;
   - the transfer source, amount, and explicit transfer authorization;
   - any credit-card eligibility or approval facts.
6. State relevant fees, opening/ongoing balance requirements, and the funding consequence before seeking confirmation.

If a prerequisite is absent, unknown, or fails, do not execute the affected banking action. Explain the precise missing condition and, where appropriate, continue only with independent portions of the request.

## Eligibility checks

### New personal checking account

Before `open_bank_account_4821` for checking, confirm all of the following:

- identity is verified;
- customer is at least 18;
- customer will not exceed four personal checking accounts;
- customer has no checking account closed for cause during the last six months;
- the exact full official `account_class` has been confirmed and ends in `Account` (for example, `Green Account (checking)`).

Call the opening tool with `account_type: "checking"`. Do not close the existing checking account first merely to make the count work unless the customer has explicitly confirmed closure and all closure conditions pass.

### New personal savings account

Before `open_bank_account_4821` for savings, confirm all of the following:

- identity is verified;
- customer has at least one active Rho-Bank checking account;
- a checking relationship has been open for at least 14 days;
- customer has fewer than five personal savings accounts;
- no account is in collections and no account has a negative balance;
- the exact full official savings `account_class` is confirmed and ends in `Account`.

Call the opening tool with `account_type: "savings"`.

For a replacement request, preserve a qualifying existing checking account until savings eligibility has been evaluated and the savings opening is complete. A newly opened checking account does not satisfy the 14-day tenure condition on its opening day.

## Closing a Light Blue checking account

The Light Blue Account is an entry-tier account. Before closing it, verify all of the following:

- account status is `OPEN`;
- there are no pending transactions;
- determine whether closure occurs within 30 days of opening;
- if it is within 30 days, the $15 early-closure fee must be covered by the account balance because it is deducted from that balance and has no alternative payment method;
- if it is not within 30 days, the balance/current holdings must be $0.

A customer statement that money was moved out is not a substitute for an account and transaction check. If a fee applies and the account balance is below $15, do not close it. If there is no applicable fee and the balance is nonzero, do not close it until the balance is resolved. Confirm the requested account immediately before calling the closure tool.

## Funding a new savings account

After a savings account has been opened, ask whether the customer authorizes an immediate opening deposit from a specified checking account. Before an internal transfer, confirm:

- source and destination accounts both belong to the authenticated customer;
- source and destination IDs are valid and distinct;
- both accounts are `ACTIVE` or `OPEN`;
- source available balance covers the positive USD amount while preserving any disclosed requirements the customer must maintain;
- the amount, source, destination, fees if any, and authorization are confirmed.

Then call `transfer_funds_between_bank_accounts_7291`. Verify the posted result and avoid duplicate transfers.

If the customer declines immediate funding, clearly tell them the account must be funded within 30 days by internal transfer or external deposit or it will be closed. Do not infer authorization from a stated savings goal or from an amount the customer says they have saved.

## APY recommendation method

Use documented figures only. Evaluate the savings balance against each product's requirements, then add bonuses only where the documents expressly allow them.

1. Exclude savings products whose documented balance requirement exceeds the customer’s intended balance.
2. For every remaining savings product, start with its base APY.
3. Add at most one linked-checking boost: identify all qualifying active checking/savings pairings and use only the highest applicable boost. Checking boosts do not stack.
4. Add at most one credit-card APY bonus: identify all active, qualifying same-profile cards and use only the highest applicable card bonus. Card bonuses do not stack.
5. Relationship or other bonuses may be included only when their independent eligibility is documented; do not relabel them as a card bonus.
6. Confirm that every linked product is held under the same customer profile and in any required good standing.
7. Explain conditions rather than guaranteeing a future rate, approval, or coverage.

Use `scripts/rate_selector.py` to calculate and rank an explicitly supplied set of documented candidate combinations. It performs arithmetic and eligibility filtering only; the executor must build the candidate list from current product documents and customer facts.

### Documented travel-insurance constrained recommendation

For a $25,000 savings balance, where a credit card with documented travel insurance is mandatory, the highest fully documented combination in the supplied product material is:

- `Gold Account` savings: 5.5% base APY, with its $10,000 balance requirement met by $25,000;
- `Green Account (checking)`: +0.75% for a linked Gold Account;
- `Silver Rewards Card`: +0.20% documented Gold Account card bonus.

This produces a documented conditional total of **6.45% APY** (5.5% + 0.75% + 0.20%), provided the accounts and card are active, eligible, and linked under the same profile. The Silver Rewards Card is the documented card in this material with travel-insurance coverage. Its coverage is conditional: the covered fare must be charged in full to the card, the incident must be covered, and policy terms, exclusions, documentation requirements, and the $15,000 per-trip cap apply. The card’s documented application terms include a 680 minimum credit score, a $0 annual fee, and an 18.99% standard APR after any promotional period; approval is not guaranteed.

Do not substitute an EcoCard solely because its Gold Account bonus is higher: the supplied material does not document travel insurance for that card. Do not recommend a high-balance savings tier merely from its headline APY when $25,000 does not meet its documented ongoing balance requirement.

If the customer accepts this recommendation, separately confirm the exact checking and savings choices before opening either. The card application must use the documented customer application process; no banking-account opening or funding action implies card approval.

## Recommended execution order

1. Authenticate and log verification.
2. Retrieve accounts and assess all checking, savings, transfer, and closure prerequisites.
3. Present the recommendation, conditional effective APY, relevant balance requirements, card-coverage conditions, and any remaining unknowns.
4. Obtain confirmation of the exact checking class, savings class, and whether to proceed with each requested banking action.
5. Open the replacement checking account if its eligibility is satisfied.
6. Open the savings account while a qualifying 14-day checking relationship remains active.
7. If authorized, fund savings through the validated internal transfer; otherwise provide the 30-day funding deadline.
8. Re-check the identified Light Blue account’s closure status, balance/fee condition, and pending transactions; obtain final closure confirmation; then close it.
9. Report created account details, funding result or deadline, closure result, conditional APY configuration, and any action the customer must take for card application or linkage.

If the checking-account limit would be exceeded before closure, do not bypass the limit. Complete a permitted closure first only after its conditions and final confirmation are satisfied, then re-evaluate checking eligibility.

## Helper scripts

### `scripts/account_eligibility.py`

Reads JSON from stdin and writes JSON to stdout. Input schema:

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

`checking_closed_for_cause_last_6_months` may be `null` when unknown. The output provides separate checking and savings eligibility results, blockers, review items, counts, and qualifying checking account IDs. It never authorizes a banking action.

Run it through the packaged-script runtime as `scripts/account_eligibility.py`, supplying runtime-retrieved account facts. Validate that `savings.eligible` and/or `checking.eligible` is `true` only after all listed blockers and review items have been resolved.

### `scripts/rate_selector.py`

Reads JSON from stdin and writes JSON to stdout. Supply an intended amount, whether documented travel insurance is mandatory, and already-documented candidate combinations. Each candidate must include `name`, `base_apy`, `minimum_balance`, `checking_boost`, `card_bonus`, and `card_has_travel_insurance`. The script returns eligible combinations sorted by computed APY and identifies the best one. Review the `excluded` entries and independently validate linkage, card approval, and product terms before presenting a result.
