---
name: safe-bank-account-transition
summary: Safely handles a verified customer's request to close a personal checking account, select and open replacement checking/savings products, arrange an authorized opening deposit, and explain documented product tradeoffs.
description: Use for Rho-Bank account-transition requests involving checking-account closure, personal checking or savings opening, funding, debit cards, overdraft protection, and savings APY comparisons. It enforces identity, ownership, eligibility, balance, transaction, fee, and explicit-confirmation checks before any bank action. It does not invent product benefits or apply for products when no documented agent tool exists.
---

# Safe Bank Account Transition

## Scope and safety boundary

Use this workflow when a customer wants to replace or close a checking account and/or open and fund personal checking or savings accounts. It supports documented product comparisons, but product information is not authorization to make a change.

**Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.**

Treat each state-changing tool call as a banking action. Do not proceed merely because the customer says they have moved money or because an account lookup returned profile data. Never disclose full sensitive data unnecessarily. Do not claim a benefit (for example, travel insurance) that is absent from the available product documentation.

## Inputs and expected result

At runtime, obtain the authenticated customer's request, verified identity evidence, customer/account/card records, current time, available product documentation, and the normal banking tools named by the documentation. Do not hardcode a customer ID, account ID, balance, date, product outcome, or a recommendation from a prior interaction.

The completed interaction should either:

1. make only the specifically authorized, fully eligible account actions and clearly summarize resulting account/funding status; or
2. stop safely, explain the concrete missing prerequisite, missing documentation, or missing authorization, and ask the focused follow-up needed.

## 1. Verify identity and authority first

1. Identify the customer using a supplied identifier (for example, email) and retrieve the profile with the normal lookup tool.
2. Ask the customer to confirm at least two independent profile fields. A lookup result alone is not confirmation.
3. Retrieve the current time and call `log_verification` only after the customer has confirmed two of the profile fields. Supply the full returned profile fields and time in the tool's required schema.
4. Confirm the customer is the owner/authorized actor for every account and debit card involved.
5. If verification or authority is incomplete, do not perform an account, card, or transfer action. Request the missing verification or transfer to a human only when appropriate.

## 2. Gather the facts before proposing or executing changes

Retrieve the customer's bank accounts and, where relevant, their transactions, debit cards, and credit-card accounts using documented normal banking tools. Inspect tool results; do not infer account state from the customer's description.

For a requested checking closure, determine:

- target account ID, ownership, class, status, opening date, current/available balance, and pending transactions;
- the relevant tier's early-closure window, fee, and notice period;
- whether all debit cards linked to that checking account are already closed; retrieve cards by checking account ID when necessary;
- whether any required funds are available to pay an early-closure fee from the account itself.

For requested openings, determine the exact full official `account_class` string, account type, current account counts, customer age where required, prior closures where required, account standing, checking tenure, and documented opening-deposit requirement. For an immediate transfer, identify the owned source/destination accounts, available funds, amount, and fee/limit implications.

Use `scripts/check_transition.py` to normalize an evidence snapshot into blockers and required confirmations if helpful. The script only evaluates supplied facts; it cannot verify facts or perform bank actions.

## 3. Evaluate closure without closing prematurely

Personal checking closure requires all of the following:

- account status is `OPEN`;
- no pending transactions;
- any associated debit cards are closed first;
- if an early closure fee applies, the account balance is at least that fee; otherwise the balance must be exactly $0; and
- the account-specific notice period and any other documented prerequisites are satisfied.

For the documented tiers, use these early closure rules:

| Tier/classes | Fee window and fee | Notice |
|---|---:|---:|
| Light Blue, Light Green, Green Fee-Free | $15 if closed within 30 days | 0 days |
| Blue, Green (checking) | $25 if closed within 60 days | 3 days |
| Evergreen | $50 if closed within 90 days | 7 days |
| Bluest | $100 if closed within 180 days | 14 days |

If a linked debit card must be closed, use the debit-card procedure first: confirm ownership, ACTIVE/PENDING status, no pending transactions/refunds, card-age rule (with the documented lost/stolen/fraud exception), and an explicit permitted reason. Use `close_debit_card_4721(card_id, reason)` only after those checks. Do not use debit-card closure merely to bypass the checking-account closure conditions.

Only after all closure prerequisites and the customer's explicit closure authorization are present, unlock and call `close_bank_account_7392` with the tool's documented runtime schema. Record the result. A closure failure means stop and explain the result; do not retry or assume closure.

## 4. Evaluate and open replacement accounts

### Personal checking

Before opening personal checking, verify: customer is verified, age is at least 18, the customer has no more than four existing personal checking accounts, there was no checking account closed for cause in the prior six months, and the customer selected the exact official class name ending in `Account`.

### Personal savings

Before opening personal savings, verify: customer is verified, has at least one active Rho-Bank checking account held at least 14 days, has fewer than five personal savings accounts, has no accounts in collections and no negative balances, and selected the exact official class name ending in `Account`.

If all applicable requirements pass and the customer has explicitly authorized that product, unlock and use `open_bank_account_4821` with `account_type` set to `checking` or `savings` and the exact official `account_class`. Read the result and retain the returned account ID before attempting funding.

Do not open either account if a required fact is unavailable, a condition fails, or the customer has only asked for a recommendation.

## 5. Funding and overdraft protection

For a savings account with a required opening deposit, ask whether the customer authorizes an immediate internal transfer after the account is successfully created. Confirm source-account ownership, destination ID, available balance, exact amount, all relevant limits/fees, and the customer's explicit transfer confirmation. Then unlock and call `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`.

If the customer declines immediate funding, state the documented 30-day funding window and closure consequence for the savings-opening workflow. Do not claim funding is complete.

A product feature such as automatic overdraft transfers is not itself enrollment authorization. Explain the documented feature and per-transfer charge, then obtain the customer’s explicit authorization and use only a documented enrollment/configuration tool if one is actually available. If no such tool is documented or available, do not simulate enrollment; explain that the feature cannot be configured in the current workflow.

## 6. Give accurate product comparisons

Use only the supplied documentation. Separate a documented rate from an estimate and state its conditions. For APY comparisons:

- credit-card APY bonuses do not stack; use only the highest applicable active-card bonus;
- the highest applicable linked-checking boost applies when multiple qualifying checking accounts exist; those checking boosts do not stack;
- eligible checking and credit-card bonuses can stack with other documented bonus categories;
- honor balance tiers, minimums, opening-deposit requirements, account linkage, same-profile requirements, and product eligibility.

For example, a documented automatic overdraft-transfer feature on a checking account should be distinguished from out-of-network ATM reimbursements on a savings account. Do not call a fixed dollar cap a guarantee that every ATM charge will be reimbursed. Do not represent a credit-card application as an agent action where documentation only specifies an online customer application. If travel insurance or any other requested card benefit is undocumented, say that it cannot be confirmed from the available materials and seek the customer’s direction rather than asserting it exists or does not exist universally.

When customer requirements conflict (such as the highest rate versus a required undocumented travel benefit), present the supported tradeoff and request a revised explicit selection. A prior authorization for a different product combination does not authorize a newly changed combination.

## 7. Confirm completion or a safe stop

After every successful action, report only verified results: account class/ID as appropriate, closure/opening status, funded or unfunded status, transfer amount/status, applicable deadlines, and disclosed fees. If no action was safe to take, state the exact blocker and the next customer action or fact needed.

If the customer asks for a human, the task needs unavailable specialized handling, or a verified action cannot be completed due to a technical error, use `transfer_to_human_agents` with the most accurate available reason and a concise factual summary. Never transfer merely to avoid gathering available prerequisite information.

## Script interface

`scripts/check_transition.py` reads one JSON object from standard input and writes one JSON object to standard output. It has no external dependencies and performs no banking action.

Input schema:

```json
{
  "checking_open": true,
  "checking_age_days": 14,
  "savings_count": 0,
  "checking_count": 0,
  "verified": true,
  "age_years": 18,
  "has_collections": false,
  "has_negative_balance": false,
  "recent_checking_closed_for_cause": false,
  "closure": {
    "account_class": "Light Blue Account",
    "status": "OPEN",
    "age_days": 30,
    "balance": "0.00",
    "pending_transactions": false,
    "debit_cards_closed": true
  }
}
```

All fields are optional. Missing facts are reported as `unknown` rather than treated as approval. Output contains `checking_opening`, `savings_opening`, and `closure` objects, each with `eligible`, `blockers`, and `unknown` fields. `eligible: true` means only that all facts supplied for that checklist pass; the executor must still verify ownership, exact product selection, authorization, and applicable tool results before acting.

Example runtime use:

```sh
python3 scripts/check_transition.py <<'JSON'
{"verified":true,"checking_open":true,"checking_age_days":20,"savings_count":1,"has_collections":false,"has_negative_balance":false}
JSON
```

Validate that every `blockers` and `unknown` entry has been resolved with live tool evidence before treating a checklist as passed, and independently verify current tool results immediately before every state-changing call.
