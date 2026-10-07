---
name: checking-and-savings-account-transition
version: 1.0.0
description: Safely handles a customer request to replace a personal checking account, recommend a checking account for early direct deposit and benefits, open a qualifying personal savings account, arrange funding, and close the old checking account. Use for banking workflows requiring identity verification, account/product eligibility checks, account-opening or closure tools, and account-specific recommendations.
---

# Checking and Savings Account Transition

## Scope

Use this workflow when a customer wants to close or replace a personal checking account and/or open personal savings. It supports recommendations but never treats a recommendation as authorization to open, close, transfer, or change an account.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and action rules

1. **Authenticate before any banking action.** Confirm two independent identity fields out of date of birth, email, phone number, and address. Do not reveal profile values to obtain confirmation. Retrieve the customer record using the supplied identifier, compare the customer-provided fields, obtain the current time, and call `log_verification` with the complete returned profile and time.
2. **Verify authority and ownership.** Identify the account from live account data, ensure the authenticated customer owns it, and verify that it is the intended account before viewing transactions, transferring funds, or closing it.
3. **Use current system facts, not assertions alone.** Customer statements can guide inquiry, but live data must establish account status, age/open date, balances, pending transactions, account counts, verification status where available, and relevant card holdings.
4. **Obtain explicit confirmation immediately before each irreversible action.** A request to “swap” does not authorize closing a named account. A request for the “best” product does not authorize a product selection. Require the exact official `account_class` string and a clear confirmation to open it; separately require clear confirmation to close the identified existing account.
5. **Do not invent product terms or funding outcomes.** Only state rates, fee waivers, account requirements, and bonus eligibility supplied by current product documentation. Never state an APY bonus is active without verifying the necessary linked products and cards.
6. **Use agent banking tools directly.** Never ask the customer to call internal tools or expose tool parameters. Tools listed below are invoked only after their prerequisites are satisfied.

## Required live review

After authentication, obtain live account records and inspect the existing checking account. Collect at least:

- account ID, owner, type/class, status, open date, current/available balance, and whether it is a personal checking account;
- all checking and savings accounts for the customer, including count and status;
- account transaction history using `get_bank_account_transactions_9173(account_id)` to detect pending transactions;
- any collections indicators and negative balances across the customer’s accounts;
- credit-card accounts, if a savings-rate calculation may include card bonuses;
- official identity-verification status, if the system exposes it.

If a required fact cannot be validated with the available normal banking tools, do not take the affected action. Explain what is missing and request the needed verification or route to the appropriate supported channel.

## Eligibility rules

### Opening personal checking

Before `open_bank_account_4821`, confirm all of the following:

- customer is verified;
- customer is at least 18;
- customer has fewer than 4 personal checking accounts;
- no personal checking account was closed for cause in the preceding 6 months;
- customer selected an exact, full official checking `account_class` ending in `Account`.

Call `open_bank_account_4821(user_id, "checking", account_class)` only after these checks and the customer’s explicit approval.

### Opening personal savings

Before `open_bank_account_4821`, confirm all of the following:

- customer is verified;
- customer has an active Rho-Bank checking account;
- the qualifying checking account has been held for at least 14 days;
- customer has fewer than 5 personal savings accounts;
- no account is in collections and no account has a negative balance;
- customer selected an exact, full official savings `account_class` ending in `Account`.

Call `open_bank_account_4821(user_id, "savings", account_class)` only after these checks and explicit approval.

**Sequencing:** Do not close the only eligible checking account before opening the savings account that relies on its active status and tenure. If the existing checking account is the qualifying account, retain it through savings eligibility and savings-opening completion. Opening a new checking account does not inherit the old account’s tenure.

### Closing personal checking

Before `close_bank_account_7392`, verify live data confirms:

- account status is `OPEN`;
- no pending transactions exist;
- the applicable tier, early-closure period, fee, and notice period;
- if an early closure fee applies, balance is at least that fee; otherwise balance/current holdings is exactly $0;
- any required notice period has been met.

For an entry-tier Light Blue Account, the early-closure fee is $15 only when closing within 30 days; the notice period is 0 days. Do not infer account age or transaction status solely from the customer’s statement. Then obtain a final explicit confirmation naming the account to close and call `close_bank_account_7392`.

## Recommendation method

1. Identify hard requirements first. For early direct deposit, compare only products whose documented early-deposit timing satisfies the customer’s requested timing. Disclose timing is dependent on payer transmission and eligibility.
2. Compare meaningful tradeoffs: early-deposit days, recurring fee and waiver threshold, balance requirements, ATM/wire fees, travel benefits, service benefits, age eligibility, and relevant limits. “Best overall perks” is preference-dependent; explain the rationale rather than claiming an objectively universal best.
3. For savings, remove products whose opening deposit or ongoing balance requirements exceed the customer’s confirmed available funds or intended maintained balance. Compare eligible base APY, then apply only documented bonuses.
4. Credit-card bonuses do not stack: apply only the highest applicable active-card bonus. Checking boosts do not stack: apply only the highest applicable eligible checking boost. A qualifying checking boost and the single highest applicable card bonus may both be additive to the savings rate when documentation permits.
5. State all assumptions and product requirements, then ask the customer to select exact named checking and savings account classes. A calculation can be assisted with `scripts/rank_account_options.py`.

### Example decision pattern for a two-day early-deposit request

Where current product documentation shows that a Purple Account provides eligible direct deposit up to two days early and substantial travel-oriented benefits, it can be a strong recommendation for a customer prioritizing early pay plus broad perks. Disclose its documented $15 monthly fee and $3,750 minimum daily balance waiver threshold. Do not select it automatically.

For a customer with $25,000 to deposit and maintain, Gold Plus can be the highest documented base-rate option among products whose stated opening and ongoing balance requirements fit that amount: 6.0% APY, $10,000 opening deposit, and $25,000 ongoing balance. Higher-rate tiers with higher required opening or ongoing balances are not suitable merely because the customer currently has $25,000. Recalculate if linked-card or checking-boost eligibility is confirmed.

## Funding the new savings account

After a savings account is opened, ask whether the customer authorizes an immediate opening-deposit transfer from a confirmed eligible checking account.

- If yes, re-check the source account’s available balance, the required deposit amount, source and destination ownership, transfer fee/limits/cutoffs, and the customer’s exact amount authorization. Then use `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`.
- If no, or if no internal checking balance is available, explain the external-funding route and the applicable product opening-deposit requirement. The general savings process provides a 30-day funding window for an unfunded account; do not use that statement to override a selected product’s stricter stated opening-deposit minimum.
- Never claim that a transfer, external deposit, or funding condition has completed unless the relevant system result confirms it.

## End-to-end execution order

1. Acknowledge the goals and ask for two identity fields if authentication is incomplete.
2. Verify identity, retrieve the customer’s live profile and accounts, and log verification.
3. Validate current checking ownership/status, balances, pending transactions, tenure, account counts, closure-for-cause history, collections/negative balances, and card holdings.
4. Provide a concise checking recommendation and a savings-rate/eligibility comparison based on documented terms and confirmed facts.
5. Obtain explicit selections for the exact new checking and savings account classes, plus separate authorization to open each.
6. Open the new checking after checking eligibility passes.
7. While the existing qualifying checking account remains open, open the selected savings after savings eligibility passes.
8. Obtain and execute funding authorization if possible; otherwise provide the accurate funding requirement and deadline information.
9. Revalidate all closure prerequisites for the old checking account, disclose any fee, obtain final closure confirmation, and close it.
10. Confirm only completed actions, account identifiers/details returned by the tools, funding status, relevant fee/waiver conditions, and any remaining customer action.

## Failure handling

- **Identity not verified:** stop before account actions; request another independent field or use the supported authentication path.
- **Ineligible account opening:** name the failed requirement without exposing sensitive information and do not call the opening tool.
- **Insufficient source balance or no transfer authorization:** do not transfer; explain funding alternatives and timing.
- **Pending transaction, nonzero closure balance, notice requirement, or fee shortfall:** do not close; explain the live blocker and the necessary next step.
- **Ambiguous product choice or closure request:** provide the comparison and ask for exact selections/confirmation.
- **Tool failure or uncertain outcome:** do not retry an operation reported as unknown. Preserve the known result, inspect account state through safe read-only tools if available, and escalate through the supported process when necessary.

## Helper script

`scripts/rank_account_options.py` accepts JSON on stdin and emits JSON on stdout. It is advisory only; it neither accesses systems nor takes banking actions.

Input schema:

```json
{
  "available_deposit": 25000,
  "minimum_early_deposit_days": 1,
  "checking_options": [
    {"account_class": "Example Checking Account", "early_direct_deposit_days": 2, "perk_score": 0}
  ],
  "savings_options": [
    {
      "account_class": "Example Savings Account",
      "base_apy_percent": 5.0,
      "opening_deposit_min": 1000,
      "ongoing_balance_min": 1000,
      "checking_boosts_percent": [0.0],
      "card_bonuses_percent": [0.0]
    }
  ]
}
```

`perk_score` is optional and must be supplied only from an explicit, documented comparison rubric; absent scores are not treated as objective quality. The output identifies eligible options, computes the maximum (not sum) of each bonus category, and returns assumptions/validation errors. Review its output against live eligibility and product documents before discussing or acting on it.
