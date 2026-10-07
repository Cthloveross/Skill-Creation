---
name: checking-replacement-and-savings-opening
version: 1.0.0
description: Safely handle a request to replace a personal checking account, open and fund a personal savings account, evaluate documented APY bonuses, set expectations for overdraft protection, and close the old checking account only after all prerequisites are verified. Use when account-opening, transfer, closure, and account-benefit requests are combined.
---

# Checking replacement and savings opening

## Scope

Use this Skill for a customer who wants to close or replace a checking account and open a savings account. It supports eligibility and closure checks, a documented Gold Account APY calculation, and an execution order that prevents closing an account before the replacement/funding plan is ready.

This Skill does not itself perform bank actions. The execution agent must use the normal banking tools named in the knowledge base and must not treat a script recommendation as an action.

## Required runtime inputs

Gather or retrieve, at runtime:

- authenticated customer identity and `user_id`;
- current timestamp;
- all bank accounts, including ID, type, class, status, balance/current holdings, date opened, and any available pending-transaction data;
- checking-opening facts: verified status, age, number of personal checking accounts, and checking accounts closed for cause in the last six months;
- savings-opening facts: verified status, active checking account(s), personal savings count, all account statuses/balances, and checking tenure;
- the exact full official account-class names selected by the customer;
- source account, amount, and authorization for any opening-deposit transfer;
- closure target, status, balance, opening date, and pending-transaction status;
- active credit cards if evaluating card APY bonuses.

Do not infer verification from possession of a name, email address, account lookup, or demographic record. Verify two of the four identity fields (date of birth, email, phone, address), obtain the current time, and call `log_verification` only after successful verification.

## Execution procedure

1. **Authenticate and retrieve facts.**
   - Identify the customer, confirm two identity fields, call `get_current_time`, then call `log_verification` with the complete profile fields and timestamp.
   - Unlock and use `get_all_user_accounts_by_user_id_3847` to retrieve all bank accounts. Do not rely only on the customer's statement that money was moved or an account is eligible for closure.
   - Retrieve credit-card accounts if the customer asks about card-linked APY. Absence of a card account means no card bonus is currently active.

2. **Confirm product choices and disclose supported features.**
   - A Blue Account supports linked-account overdraft-protection transfers at $12.50 per automatic transfer. Explain that this is distinct from Blue's $0.00 account overdraft fee.
   - The provided procedure says Blue overdraft protection is enabled in account settings by choosing a linked funding account and accepting the $12.50 per-transfer disclosure. Do not claim that the linkage is complete unless an available tool or account setting confirms it.
   - A Gold Account requires a $5,000 opening deposit, has a $10,000 ongoing minimum balance, a 5.5% base APY, 20 monthly withdrawals, and up to $30 in monthly ATM-fee rebates.
   - Capture exact official names including the `Account` suffix, e.g. `Blue Account` and `Gold Account`.

3. **Check opening eligibility before opening either account.**
   - For personal checking: customer must be verified, at least 18, have no more than four personal checking accounts, and have no checking account closed for cause in the prior six months.
   - For personal savings: customer must be verified; have at least one active Rho-Bank checking account; have fewer than five personal savings accounts; have no account in collections and no negative account balance; and have held a checking account for at least 14 days.
   - If any condition is unknown, stop and obtain it. If any condition fails, do not call an opening tool. Explain the precise failed condition and, when calculable, the date eligibility begins.
   - Run `scripts/assess_account_plan.py` with normalized retrieved facts to make a reproducible checklist. Its result is advisory; source tool records remain authoritative.

4. **Open accounts only after eligibility and customer confirmation.**
   - Unlock `open_bank_account_4821` and call it separately for each confirmed account, using the authenticated `user_id`, `account_type` (`checking` or `savings`), and exact selected `account_class`.
   - Record the newly returned account IDs and verify their status before any transfer.
   - Never fabricate an account ID, balance, deposit source, or opening result.

5. **Fund the savings account.**
   - Ask whether the customer wants an immediate internal transfer and identify the source checking account and amount. The customer must authorize this transfer.
   - For an internal transfer, confirm source/destination are distinct and ACTIVE or OPEN, belong to the customer, and that the source has sufficient available funds. Unlock and call `transfer_funds_between_bank_accounts_7291` only with a positive USD amount.
   - If funding is deferred, inform the customer that the new savings account has 30 days to be funded through an internal transfer or external deposit or it will be closed. Do not imply that an external deposit occurred.
   - If the customer says funds were moved out of the old account, do not select it as a source until the actual balance and authorization are confirmed.

6. **Address APY and credit-card questions accurately.**
   - For a Gold Account, use `scripts/assess_account_plan.py` with `gold_apy` input to calculate base APY plus the highest active documented credit-card bonus. Credit-card bonuses do not stack with each other.
   - A documented linked-checking boost can be additive to the base APY and the selected card bonus, but multiple checking boosts do not stack; use only the highest applicable, documented amount. Do not invent a boost percentage when the documentation lists a qualifying pairing but no amount.
   - The Gold Account card-bonus table supports these bonuses: Bronze Rewards +0.15%, Silver Rewards +0.20%, Gold Rewards +0.025%, Platinum Rewards +0.15%, Diamond Elite +0.30%, EcoCard +0.60%, Green Rewards +0.35%, Crypto-Cash Back +0%.
   - No supplied procedure supports opening a credit card or establishes which credit cards include travel insurance. State that limitation rather than recommending or opening a card based on unverified travel-insurance coverage. Do not promise the advertised APY until account/card eligibility and system application are confirmed.

7. **Close the old checking account last.**
   - Confirm the target account is OPEN and has no pending transactions.
   - For Light Blue Account, the early-closure fee is $15 if closure is within 30 days of opening, with no notice period. If the fee applies, current holdings must be at least $15 because the fee is deducted from the account; otherwise current holdings must be exactly $0.
   - If any closure condition is unmet or unknown, do not close it. Explain what must be resolved.
   - After all conditions are met, unlock and call `close_bank_account_7392` for the verified target account. Confirm the tool result. Do not close an account merely because the customer requested replacement.

8. **Complete the interaction.**
   - State only confirmed account openings, transfer/funding status, overdraft-link setup status, closure status, applicable fees, and any deferred-funding deadline.
   - If a required action has no available procedure/tool (for example, credit-card opening or travel-insurance verification), explain the limitation and offer an appropriate supported next step; do not make up an action.

## Script interface

`scripts/assess_account_plan.py` reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD",
  "verified": true,
  "age_years": 30,
  "accounts": [
    {
      "account_id": "string",
      "account_type": "checking|savings",
      "account_class": "string",
      "status": "OPEN|ACTIVE|...",
      "balance": "0.00",
      "date_opened": "YYYY-MM-DD",
      "personal": true,
      "closed_for_cause_date": "YYYY-MM-DD or null",
      "pending_transactions": false
    }
  ],
  "closure_account_id": "string or null",
  "gold_apy": {
    "active_card_classes": ["EcoCard"],
    "checking_boost_candidates": [
      {"source": "documented checking relationship", "percent": "0.10"}
    ]
  }
}
```

`accounts` may be empty, but the resulting `unknown_or_missing` list must then be resolved through normal tools. `gold_apy.checking_boost_candidates` must contain only boost values confirmed by documentation and the customer's actual active checking accounts.

The output contains `checking_opening`, `savings_opening`, `closure`, `gold_apy`, and `unknown_or_missing`. Each section identifies pass/fail/unknown conditions rather than authorizing an action. Validate that all required checks are `pass` before opening or closing. For a Gold Account APY result, ensure `unsupported_cards` is empty before presenting a calculated card-bonus result as complete.
