---
name: savings-and-checking-account-change-advisor
description: Advise a verified banking customer on savings-account yield and ATM-rebate tradeoffs, and safely handle the related checking-account replacement, account opening, funding, or closure workflow. Use for product comparisons and for requests to close, open, or transfer between personal checking and savings accounts.
---

# Savings and Checking Account Change Advisor

Use this Skill to separate an informational product recommendation from a banking action. A recommendation may be given from stated facts and documented product terms. Do not open, close, transfer, link overdraft protection, or change profile data until the required identity, authority, ownership, eligibility, balance, fee, limit, and confirmation checks are complete.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and assumptions

- Treat an APY as an annual percentage yield, not a guaranteed dollar-interest quote. Compare the APY that applies to the customer's stated balance tier, including only bonuses whose eligibility is actually verified.
- Treat an ATM rebate cap as a monetary monthly cap when the product documentation states a dollar amount. It offsets eligible ATM operator surcharges and is distinct from withdrawal-count limits and excess-withdrawal fees.
- Never infer that a customer has an eligible card, linked checking account, direct deposit, relationship qualification, active account, sufficient funds, no pending transactions, or manager approval. Verify each relevant fact.
- Only the highest applicable credit-card APY bonus applies if a customer holds multiple qualifying cards. Only the highest applicable checking-account APY boost applies if multiple checking accounts qualify. A selected card bonus and selected checking boost can stack with other independently eligible bonuses when product documentation permits.
- If account terms conflict or a requested feature is undocumented, state that it cannot be confirmed and do not promise it.

## Product-comparison method

1. Gather the planned opening deposit, intended ongoing balance, whether the customer needs ATM fee rebates, and any requested qualifying benefits (cards, direct deposit, linked checking).
2. Build candidates from the current product documentation. For each, record opening minimum, ongoing minimum, APY applicable at the stated balance, tier threshold if any, and ATM-rebate amount/cap.
3. Exclude candidates that the planned opening deposit cannot fund or whose required ongoing balance the customer does not intend to maintain. Do not call an account with a higher advertised APY eligible when its applicable balance requirement is not met.
4. When ATM reimbursement is required, retain only candidates with a documented ATM fee rebate and explain the cap. Rank remaining eligible products by applicable APY; use the rebate cap and other requested features as clear tie-breakers.
5. State the recommended product, the facts supporting it, material limits, and why higher-yield alternatives were excluded. Do not add unverified bonuses.
6. Use `scripts/rank_savings_options.py` for deterministic filtering and ranking when candidate data is supplied in JSON. The script does not call banking tools or make bank changes.

### Example currently documented comparison pattern

For a customer planning a $10,000 savings balance and needing ATM-fee rebates, check the Gold Account's documented $5,000 opening minimum, $10,000 ongoing minimum, 5.5% APY, and up-to-$30 monthly ATM rebate. Compare this with products whose higher advertised yield requires an opening deposit or ongoing balance above $10,000, and with tiered products whose stated balance earns their lower tier. Confirm any card, checking-link, direct-deposit, or relationship bonus separately before including it.

## Banking-action workflow

### 1. Authenticate and establish authority

For an action affecting an account, obtain confirmation of two of the four identity fields (date of birth, email, phone number, address) against the customer record. Retrieve the record using the appropriate user-information tool and, after matching two fields, call `log_verification` with all required record fields and the current timestamp. Confirm the requester is the authenticated account owner or otherwise authorized.

If identity or authority is not established, provide only general information and request the missing verification information; do not retrieve account details or perform an account action.

### 2. Inspect the current state

After verification, unlock and use `get_all_user_accounts_by_user_id_3847` to retrieve all checking and savings accounts. Use it to identify account IDs, type, class, status, balance, and opening date. For an account proposed for closure, unlock and use `get_bank_account_transactions_9173` and verify there are no pending transactions.

For a savings opening, verify all of the following before proceeding:

- Customer identity is verified in our systems.
- Customer has at least one active Rho-Bank checking account.
- Customer currently holds fewer than 5 personal savings accounts.
- Customer has no accounts in collections and no negative balances.
- The customer’s checking account tenure is at least 14 days.

For a personal checking opening, verify that the customer is verified, at least 18 years old, holds no more than four personal checking accounts, and has had no checking account closed for cause in the preceding six months.

### 3. Obtain explicit, action-specific confirmation

Before each action, confirm the exact account class, action sequence, source and destination accounts, amount, applicable opening deposit, known fees, and the customer's authorization. A preference or a request for a recommendation is not authorization to open, close, transfer, or enroll in overdraft protection.

If a customer wants checking overdraft protection, explain the documented product-specific fee and require confirmation of the eligible linked funding account before enrollment. For example, the documented Blue Account overdraft-protection transfer charge is $12.50 per triggered transfer. Do not imply that the checking-account opening itself completes enrollment.

### 4. Open accounts only when eligible and confirmed

Unlock `open_bank_account_4821`. For checking, call it with the authenticated `user_id`, `account_type` of `checking`, and the exact full official `account_class` ending in `Account`. For savings, use `account_type` of `savings` and the exact full official account class ending in `Account`.

After a savings account is opened, ask whether the customer authorizes an immediate opening-deposit transfer from a specified checking account. If yes, verify ownership, distinct valid account IDs, both statuses are ACTIVE or OPEN, positive USD amount, available funds, opening-minimum amount, fees, and confirmation. Then unlock and call `transfer_funds_between_bank_accounts_7291`. If the customer declines immediate funding, state the documented 30-day funding deadline and that the account will be closed if unfunded.

### 5. Close accounts only after closure checks

Do not close an account merely because the customer says they moved money. Verify the account is OPEN, has no pending transactions, and meets the relevant balance rule. Determine the tier, early-closure window, fee, and notice period from current documentation.

For a Light Blue Account, the entry-tier closure rules are: a $15 early-closure fee if closure occurs within 30 days and no notice period. If the fee applies, the account balance must be at least the fee; otherwise `current_holdings` must be $0. The fee is deducted from the account and has no alternative payment method. Once all conditions and explicit closure confirmation are present, unlock and use `close_bank_account_7392`.

### 6. Verify and communicate outcomes

After a transfer, verify it posted as expected and that no duplicate was initiated. After an opening, report the new account and its funding status or deadline. After a closure, report completion and any applied fee. Never retry an operation whose result is unknown; instead explain the status and investigate with permitted read-only tools.

## Response guidance for an informational request

Answer the exact comparison first in plain language. Include the applicable APY, balance conditions, and ATM-rebate cap; distinguish ATM-fee rebates from free-withdrawal limits. Then say that account opening, funding, and checking changes require verified eligibility and explicit authorization. Ask only for the next decision or facts needed for the requested next action.

## Script interface

Run from the package directory:

```sh
python3 scripts/rank_savings_options.py <<'JSON'
{"balance":10000,"opening_deposit":10000,"require_atm_rebate":true,"products":[{"name":"Example Account","opening_minimum":1000,"ongoing_minimum":2500,"tiers":[{"minimum_balance":0,"apy":3.0},{"minimum_balance":15000,"apy":4.5}],"atm_rebate_cap":25}]}
JSON
```

Input is a JSON object with nonnegative numeric `balance` and `opening_deposit`, optional boolean `require_atm_rebate`, and a `products` list. Each product requires `name`, `opening_minimum`, `ongoing_minimum`, and either `apy` or nonempty `tiers` (`minimum_balance`, `apy`). `atm_rebate_cap` is optional. Output JSON contains `eligible`, `excluded`, and `recommendation`; it is an analytical aid only.

Validate that each recommendation is eligible for both planned funding and ongoing balance, that tier selection uses the greatest threshold not exceeding the balance, and that a rebate-required recommendation has a positive documented rebate cap. Validate all live eligibility and account facts using banking tools before an action.
