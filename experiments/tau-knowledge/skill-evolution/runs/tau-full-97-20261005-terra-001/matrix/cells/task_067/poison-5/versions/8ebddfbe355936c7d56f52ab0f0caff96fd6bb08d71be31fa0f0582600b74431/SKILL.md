---
name: safe-personal-account-replacement-and-apy-planning
description: Safely advise on and execute personal checking replacement, personal savings opening, linked APY planning, funding, and old-account closure. Use when a customer wants to replace checking, open savings, compare documented yields, or maximize a savings APY through eligible linked products.
---

# Safe Personal Account Replacement and APY Planning

## Purpose and boundaries

Use this workflow to separate three concerns that must not be conflated:

1. **Product advice** may be provided from current documented terms without performing an account action.
2. **Account openings and closures** require verified identity, authority, product selection, and every applicable eligibility condition.
3. **Transfers** require separate, explicit authorization and source-account balance validation.

The executor performs banking actions only through the normal banking tools. Packaged scripts calculate plans only; they never open, close, or fund accounts.

Do not apply for a credit card merely to improve an APY. A credit-card application requires a separate customer request, authorization, and satisfaction of the card's documented application requirements.

## Mandatory controls before every banking action

Before each opening, closure, or transfer, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

1. Retrieve the customer record using an available identifier.
2. Verify identity by matching two of the record's identity fields (date of birth, email, phone number, or address) with the customer. A lookup or an email address alone is not two-factor identity verification.
3. Obtain the current time and create the verification audit record with `log_verification` using the complete retrieved customer record.
4. Confirm the verified customer is requesting or authorizing the relevant action.
5. Unlock and use `get_all_user_accounts_by_user_id_3847` for the verified user. Retain each account ID, type, official class, status, balance, and opening date.
6. Retrieve active credit-card accounts when current card bonuses are relevant.
7. Obtain facts that account retrieval does not establish—such as pending transactions and checking accounts closed for cause—from a supported record source or direct customer confirmation. Never infer those facts from a zero balance, an OPEN status, tenure, or an absence of returned account records.

If a required fact is unavailable, explain the precise blocker and defer only the affected banking action. If no available tool can establish it, offer an appropriate human-agent transfer rather than representing it as confirmed.

## APY comparison and recommendation

Use the current product documentation. Do not claim that terms are unavailable merely because the customer has no current credit card.

For each documented savings candidate:

1. Confirm the customer can meet both its required opening deposit and its sustainable ongoing balance.
2. Start with the documented base APY.
3. Add at most one qualifying linked-checking boost: the highest applicable checking boost only.
4. Add at most one applicable credit-card bonus: the highest bonus from cards the customer already holds and is eligible to use only.
5. A checking boost and one card bonus may stack with the base APY; multiple checking boosts and multiple card bonuses do not stack within their respective categories.
6. Present currently available APY separately from conditional APY that would require a card application, approval, invitation, score verification, or other unmet condition.

A customer who delegates selection to the bank (for example, asks for the highest documented combination) may thereby select the uniquely supported checking and savings combination, provided the customer has not deferred that part of the request. State the exact official classes, requirements, and APY calculation before opening accounts. Delegation does not authorize a transfer or a credit-card application.

### Current documented comparison facts

When the supplied product documentation is applicable:

- **Platinum Plus Account** has a 7.0% base APY, a $50,000 opening-deposit requirement, and a $100,000 ongoing minimum balance.
- **Purple Account** paired with Platinum Plus Account is a documented qualifying pair and provides a +0.3% linked-checking boost. Thus the combination yields **7.3% APY** before a card bonus.
- **Diamond Elite Account** has a $250,000 ongoing minimum, so it is not sustainable for a customer who intends to maintain only $100,000, despite its higher stated base APY.
- A **Platinum Rewards Card** can add +0.4% to Platinum Plus Account. This would make a potential 7.7% with the Purple boost, but only if the customer separately applies, is approved, and meets the documented 750 minimum credit-score requirement. Unknown score or absence of that card is not approval and does not remove the available 7.3% checking/savings recommendation.

Use `scripts/evaluate_bank_plan.py` for reproducible arithmetic and non-stacking selection. Its output is planning support, not proof of account eligibility or authorization.

## Checking-account opening gate

Before opening a personal checking account, confirm all of the following:

- Identity is verified and the customer is at least 18.
- The customer will not exceed four personal checking accounts.
- The customer has no checking account closed for cause in the previous six months.
- The exact official account class ending in `Account` has been selected or validly delegated.

After every item passes, unlock `open_bank_account_4821` and call it through the normal agent-tool mechanism with the verified `user_id`, `account_type` set to `checking`, and the exact official `account_class`. Report success only after a successful tool result.

If closure-for-cause history is unknown, do not open checking. A customer saying they do not know is not a confirmation that no closure occurred.

## Savings-account opening and funding gate

Before opening personal savings, confirm all of the following:

- Identity is verified.
- The customer currently has at least one ACTIVE or OPEN Rho-Bank checking account that has been held at least 14 days.
- The customer will hold fewer than five personal savings accounts after the opening.
- No customer account is in collections or has a negative balance.
- The exact official savings class ending in `Account` has been selected or validly delegated.
- The customer understands the documented opening-deposit and ongoing-balance requirements.

After every item passes, unlock `open_bank_account_4821` and call it with `account_type` set to `savings` and the exact official account class.

After a successful savings opening, ask whether the customer authorizes an immediate opening-deposit transfer from a specified checking account. Do not treat a stated savings goal or balance as transfer authorization. For a transfer, verify both account IDs are customer-owned, distinct, and ACTIVE or OPEN; verify sufficient available balance, positive USD amount, relevant limits and fees, and explicit transfer authorization. Then unlock and call `transfer_funds_between_bank_accounts_7291`.

If the customer declines or does not authorize immediate funding, state that the savings account must be funded within 30 days through an internal transfer or external deposit or it will be closed. For Platinum Plus Account, the documented opening deposit is $50,000.

## Checking-account closure gate

Before closing a checking account, verify:

- The account belongs to the verified customer and is OPEN.
- There are no pending transactions.
- The relevant account tier, early-closure window, fee, and notice period are known.
- If an early closure fee applies, the balance is at least the fee; otherwise, the balance is exactly $0. The fee is deducted directly from the account, with no alternate payment method.
- Any notice period has elapsed and the customer has authorized closure after its consequences were explained.

Documented closure terms:

- Light Blue Account, Light Green Account, and Green Fee-Free Account: $15 within 30 days; no notice period.
- Blue Account and Green Account (checking): $25 within 60 days; three-day notice.
- Evergreen Account: $50 within 90 days; seven-day notice.
- Bluest Account: $100 within 180 days; 14-day notice.

When all conditions pass, unlock `close_bank_account_7392`, call it using its runtime-required parameters, and report closure only after a successful result. A zero balance does not establish that there are no pending transactions.

## Required sequence for replacement plus savings

Do not close the only mature checking account before completing any savings opening that relies on its active status and 14-day tenure. A newly opened replacement checking account does not immediately satisfy the savings-tenure requirement.

For a customer requesting a checking replacement and savings account in the same active scope:

1. Verify identity and retrieve all accounts.
2. Give the documented APY recommendation, including available and conditional card paths.
3. Confirm checking-opening eligibility and open the selected replacement checking account.
4. Keep the existing mature checking account OPEN while confirming savings eligibility and opening the selected savings account.
5. Handle savings funding only after separate transfer authorization, or give the 30-day funding disclosure.
6. Recheck the old checking account's closure prerequisites, especially pending transactions, then obtain closure authorization and close it.

If opening eligibility is unknown, defer the opening. If closure eligibility is unknown, defer the closure. If the customer later defers savings, do not open savings or discuss funding as though it remains requested; preserve the mature checking account where possible so the customer can satisfy savings eligibility when they resume the request.

## Calculator interface

Run `scripts/evaluate_bank_plan.py` with one JSON object on stdin. It emits one JSON object on stdout and performs no banking action.

Input schema:

```json
{
  "target_balance": 100000,
  "savings_candidates": [
    {
      "savings_class": "Official Savings Account Name",
      "base_apy": 7.0,
      "opening_deposit_minimum": 50000,
      "ongoing_balance_minimum": 100000,
      "eligible": true,
      "checking_options": [
        {"checking_class": "Official Checking Account Name", "boost_apy": 0.3, "eligible": true}
      ],
      "card_options": [
        {"card_name": "Card Name", "boost_apy": 0.4, "eligible": null}
      ]
    }
  ]
}
```

`eligible` is `true`, `false`, or `null` where `null` means unknown or contingent. Include checking options only for documented qualifying pairs. The script returns viable plans, conditional plans, and rejections. Before presenting a result, validate its product terms against current documentation. Before acting on it, independently apply every gate in this Skill.
