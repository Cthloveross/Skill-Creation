---
name: personal-account-replacement-and-savings-apy-planning
description: Safely recommend and, after verified authorization, execute a replacement personal checking account, personal savings opening and funding, and prior checking-account closure. Use when a customer wants linked-account overdraft protection, savings features, or a highest documented APY plan.
---

# Personal Account Replacement and Savings APY Planning

## Scope
Use this Skill for a customer who wants to replace or close a personal checking account, open a personal savings account, fund it, and/or compare documented APY combinations. It supports an advice-only stage as well as an authorized-action stage. A recommendation, including a credit-card recommendation, is **not** authorization to open accounts, transfer funds, or apply for a card.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime and tool boundaries

- Read-only customer lookup is not identity verification. Retrieve a profile only to compare details that the customer independently provides.
- To verify identity, ask the customer to confirm at least two of date of birth, email, phone number, and address. Compare them against the authorized profile lookup. Obtain the current timestamp with `get_current_time`, then call `log_verification` with the verified profile fields and timestamp.
- For specialized banking actions documented in the knowledge base, first use `unlock_discoverable_agent_tool`, then use `call_discoverable_agent_tool`. Never ask the customer to invoke agent tools or expose tool arguments to them.
- Use only tools currently available through the runtime. Do not invent an account-listing, closure, card-application, overdraft-enrollment, or balance-lookup capability. If a required fact cannot be obtained from an authorized system of record, explain what is missing and do not perform the affected action.
- The customer-facing overdraft-protection enrollment flow is performed in account settings and requires acceptance of the per-transfer disclosure. Opening a Blue Account does not by itself establish a linked funding source or authorize transfers.

## Required facts before changing accounts

### For every action
1. Verify identity and log it as above.
2. Confirm the customer is authorized for every account involved and that source and destination accounts belong to that customer.
3. Obtain and validate the specific account IDs, statuses, balances/available funds, pending activity, applicable fees, dates, product eligibility, and the customer’s confirmation for the exact action.
4. Reconfirm immediately before each consequential action: opening each account, closing the old account, and transferring a specified amount. A prior general request does not authorize an unspecified transfer or a credit-card application.

### Opening a personal checking account
Before opening, confirm the customer is verified, at least 18, holds no more than four personal checking accounts, and has no personal checking account closed for cause in the prior six months. Capture the exact official `account_class` ending in `Account` (for example, `Blue Account`).

### Opening a personal savings account
Before opening, confirm all of the following:

- The customer is verified.
- At least one active Rho-Bank checking account exists and has been held for at least 14 days.
- The customer holds fewer than five personal savings accounts.
- No account is in collections and no account has a negative balance.
- The selected `account_class` is the complete official name ending in `Account` (for example, `Gold Account`).

Do not substitute a newly opened checking account for the required qualifying checking relationship unless it independently meets the 14-day tenure. When the old checking account is the only qualifying checking account, preserve it until savings eligibility and the intended savings opening have been completed.

### Funding a new savings account
For an immediate internal funding transfer, confirm both accounts are ACTIVE or OPEN, IDs are distinct, the source has sufficient available funds, the amount is positive USD, ownership is the same, and the customer has authorized the amount and source. If the customer declines or cannot make an internal funding transfer, tell them that the savings account must be funded within 30 days by an internal transfer or external deposit or it will be closed. Do not characterize an unverified external balance as available funds.

### Closing an existing personal checking account
Before closing, verify the account is OPEN, there are no pending transactions, and the current holdings meet the applicable condition:

- If an early-closure fee applies, balance must be at least that fee because it is deducted from the account; there is no alternate payment method.
- If no early-closure fee applies, balance must be $0.

For a Light Blue Account, the early-closure fee is $15 if closure is within 30 days. Check the open date rather than relying on the customer’s statement that money was moved. Do not close an account needed to satisfy an unfinished savings-opening eligibility requirement.

## APY recommendation method

1. Convert each documented feasible combination into one candidate: savings product, qualifying checking product, qualifying card option, deposit amount, required benefits, and all conditions.
2. Exclude candidates that fail a requested feature, funding requirement, product eligibility, or balance requirement. Do not call an unknown product “highest.”
3. Calculate the APY as the documented savings base APY plus:
   - at most one credit-card APY bonus—the highest applicable active/same-profile card bonus only; and
   - an applicable checking-account boost or other explicitly eligible additive bonus.
4. Credit-card bonuses do not stack with one another. A qualifying credit-card bonus can stack with a documented qualifying checking boost or other additive bonus.
5. Separately report (a) APY currently available from active products and (b) a projected APY conditional on obtaining and activating a card under the same customer profile. Do not promise card approval or treat a potential card as active.
6. Use `scripts/rank_apy_plans.py` to consistently filter and rank evidence-derived candidates. Its result is decision support; validate every candidate against current product records and customer eligibility before presenting it as available.

### Known fit for the documented Blue/Gold requirements
When the requirements are automatic linked-savings overdraft protection on checking, savings ATM rebates, and a $10,000 savings balance, the documented fit is `Blue Account` plus `Gold Account`. Blue supports linked-account overdraft-protection transfers for $12.50 per transfer; Gold has a $5,000 opening deposit minimum, $10,000 ongoing minimum balance, and up to $30 monthly ATM fee rebates. Gold’s base APY is 5.5%.

For Gold, the highest documented card bonus is EcoCard at +0.6 percentage points. Thus, if an EcoCard is active and held under the same customer profile, the documented projected Gold APY is 6.10% (5.5% + 0.6%), subject to all product terms. A Blue Account has no documented Gold linked-checking APY boost. Do not add other Gold card bonuses to EcoCard’s +0.6%.

If the customer has no qualifying active EcoCard, disclose that the Gold account earns its base 5.5% until the card condition is met. EcoCard application requires standard identity and income information and is an application subject to approval; no agent card-opening tool is documented here. Give application guidance only and obtain a separate customer request before any supported application workflow.

## Authorized execution order

Use this order after the recommendation is accepted and every prerequisite above is satisfied:

1. **Preserve eligibility and inspect the old account.** Identify the existing qualifying checking account and verify its age, status, balance, opening date, and pending activity. If authorized and available, retrieve transaction history using `get_bank_account_transactions_9173` to review pending entries; transaction history alone does not establish all closure facts.
2. **Open replacement checking.** Confirm the chosen official class, then unlock and call `open_bank_account_4821` with the authenticated `user_id`, `account_type` set to `checking`, and that confirmed class. Record the returned new account ID and outcome. Do not claim overdraft protection is enabled; direct the customer to account settings to select the linked account and accept the disclosure.
3. **Open savings.** Recheck savings eligibility while the qualifying checking account remains open. Confirm the official savings class, then call `open_bank_account_4821` with `account_type` set to `savings` and the confirmed class. Record the new savings ID.
4. **Fund only with explicit authorization.** If the customer authorizes an immediate transfer and the transfer validations pass, unlock and call `transfer_funds_between_bank_accounts_7291` with the selected source, newly created savings destination, and positive authorized USD amount. Confirm posting and avoid duplicate transfers. Otherwise provide the 30-day funding deadline and closure consequence.
5. **Close the old checking account last.** Revalidate the closure conditions after any funding activity. Unlock `close_bank_account_7392` and use its currently exposed runtime schema; do not assume parameters absent from the exposed schema. Confirm the closure result.
6. **Give a concise completion record.** State opened/closed account details that may be safely shared, transfer/funding status or deadline, applicable fee disclosures, and any customer-performed next step such as overdraft-protection enrollment or a separate card application.

## Fail-safe handling

- Stop account opening when verification, age/count, tenure, good-standing, class, or consent requirements are missing or fail.
- Stop a transfer for insufficient funds, nonpositive amount, same account IDs, non-owned accounts, invalid statuses, or missing transfer authorization. Resolve the condition before a new attempt.
- Stop closure for non-OPEN status, pending transactions, insufficient early-closure-fee balance, or a nonzero balance when no fee applies.
- If a product feature, APY boost, balance rule, account status, or tool schema is absent or conflicting, describe the uncertainty without choosing in the customer’s favor. Obtain an authoritative record or offer a non-action alternative.

## Ranker interface and validation

`scripts/rank_apy_plans.py` reads one JSON object from stdin and emits one JSON object on stdout. It accepts evidence-derived candidates only; it does not retrieve account or product data.

Input schema:

```json
{
  "deposit_amount": "number in USD",
  "requirements": {
    "automatic_overdraft_protection": "boolean",
    "minimum_savings_atm_rebate": "number in USD"
  },
  "candidates": [
    {
      "name": "string",
      "supported": true,
      "savings": {
        "account_class": "official name",
        "base_apy": "percentage points",
        "opening_minimum": "USD",
        "ongoing_minimum": "USD",
        "monthly_atm_rebate": "USD"
      },
      "checking": {
        "account_class": "official name",
        "automatic_overdraft_protection": true,
        "apy_boost": "percentage points"
      },
      "credit_card_options": [
        {
          "account_class": "string",
          "bonus_apy": "percentage points",
          "active_same_profile": false,
          "eligible_if_obtained": true
        }
      ]
    }
  ]
}
```

Run it with current evidence saved by the executor, for example: `python3 scripts/rank_apy_plans.py < current-plan-input.json`.

Validate output before use: `ok` must be true; only entries in `eligible_plans` meet supplied constraints; `current_effective_apy` must include only `active_same_profile` cards; `projected_effective_apy` selects at most one qualifying card; and every plan returned must still be independently verified against current records before an action.
