---
name: personal-bank-account-transition-and-yield-planning
description: Safely handles a verified customer's request to close or replace a personal checking account, open personal checking or savings accounts, arrange an authorized savings opening deposit, and compare documented APY combinations. Use when account eligibility, closure prerequisites, linked-account APY boosts, or card APY bonuses must be evaluated before banking actions.
---

# Personal Bank Account Transition and Yield Planning

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

Use this workflow for personal checking/savings openings, a checking-account closure, and APY planning. It does not itself apply for or open credit cards. Do not represent a projected APY combination as available until each product's documented eligibility is confirmed. Do not call a banking action tool merely because the customer asked for information or a recommendation.

An email lookup or a customer record lookup is not identity verification. Before any action, obtain and compare at least two of date of birth, email, phone number, and address against the customer record. Then obtain the current timestamp and call `log_verification` with all required record fields and that timestamp. Confirm the customer is authorized to act and that each affected account belongs to them.

## Runtime inputs and account discovery

1. Identify the customer without treating the initial identifier as proof of identity. Retrieve the customer record with the appropriate lookup tool.
2. Complete the two-field identity check, call `get_current_time`, and record it with `log_verification`.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` using the verified `user_id`. Retain its account IDs, types, classes, statuses, balances, and opening dates. Obtain any required pending-transaction, closure-history, collections, and negative-balance facts from supported records or the customer; do not infer missing facts.
4. If APY optimization is requested, retrieve credit-card accounts as needed and collect only the product terms and boost values documented for the candidate accounts. For a potential new card, separately verify its application criteria and availability. A missing invitation, unknown score, or unavailable application path is not approval.

## Planning the highest APY correctly

1. Restrict savings candidates to those whose opening-deposit and ongoing-balance requirements the customer can meet at the desired balance.
2. For each candidate savings account, include only documented qualifying checking/savings pairings and their matching boost. A checking boost is not transferable to a different savings class.
3. Include card bonuses only for active/approved eligible cards under the same profile, or label unverified proposed cards as conditional. Multiple checking boosts do **not** stack: select only the highest applicable checking boost. Multiple card bonuses do **not** stack: select only the highest applicable card bonus. The selected checking boost and selected card bonus may stack with the base savings APY.
4. Use `scripts/evaluate_bank_plan.py` to rank structured candidates. It is a calculation aid, not evidence that a product is eligible or a tool authorization.
5. State the base APY, selected checking boost, selected card bonus, resulting projected APY, material balance requirements, and every remaining condition. If the available product evidence is incomplete, say that an absolute highest APY cannot be established from the verified candidates.
6. Obtain the customer's confirmation of the exact checking and savings selections before opening either account. The `account_class` must be the full official product name exactly as confirmed by the customer; do not normalize or abbreviate it.

## Eligibility gates

### Opening personal checking

Before opening, verify identity, authority, product selection, and all of the following:

- Customer is verified and at least 18.
- Opening the account will not exceed the four-personal-checking-account limit.
- The customer has no checking account closed for cause within the prior six months.

If any condition is false or unavailable, explain the blocker and do not open the account. Once eligibility and exact selection are confirmed, unlock `open_bank_account_4821` and call it with the verified `user_id`, `account_type: "checking"`, and confirmed official `account_class`.

### Opening personal savings

Before opening, verify identity, authority, exact product selection, account-specific deposits/fees, and all of the following:

- The customer has at least one active Rho-Bank checking account held for at least 14 days.
- Opening the account will leave the customer below the five-personal-savings-account limit.
- No account is in collections and no account has a negative balance.

Do not open if any item is unverified or fails. After eligibility and the exact official `account_class` are confirmed, call unlocked `open_bank_account_4821` with `account_type: "savings"`.

After a successful savings opening, ask whether the customer authorizes an immediate opening-deposit transfer from a specified checking account. If yes, verify source/destination ownership, distinct IDs, both account statuses (ACTIVE or OPEN), sufficient available funds, positive USD amount, fees/limits/cutoffs, and the customer confirmation. Then unlock and call `transfer_funds_between_bank_accounts_7291`. Verify the posting and avoid a duplicate. If the customer declines, explain that the account must be funded within 30 days through an internal transfer or external deposit or it will be closed.

### Closing personal checking

For a checking-account closure, use the retrieved account record and verify all of the following before proceeding:

- The identified account is owned by the verified customer and has OPEN status.
- There are no pending transactions.
- The applicable tier, early-closure window, fee, and notice period have been determined.
- If an early fee applies, the account balance is at least that fee; otherwise the balance is exactly $0. The fee is deducted from the account and has no alternate payment method.
- Any required notice period has been honored and the customer confirms closure after being told the fee and consequences.

For Light Blue Account, Light Green Account, and Green Fee-Free Account, the early-closure fee is $15 when closure occurs within 30 days and notice is 0 days. For Blue Account and Green Account (checking), the fee is $25 within 60 days and notice is 3 days. For Evergreen Account, the fee is $50 within 90 days and notice is 7 days. For Bluest Account, the fee is $100 within 180 days and notice is 14 days.

If a pending-transaction fact, balance, date opened, or fee/notice condition is unknown, pause rather than close. Once all conditions are satisfied, unlock and call `close_bank_account_7392` for the selected account using the tool's documented parameters. Confirm the returned closure outcome only after the tool succeeds.

## Recommended execution order for replacement requests

A request to replace checking and add savings can be carried out in a safe sequence:

1. Verify identity and retrieve all accounts.
2. Evaluate eligibility and present a conditional APY recommendation.
3. Obtain confirmations for the exact products and, where applicable, a source account and opening-deposit amount.
4. Open any new checking account only after its eligibility gate passes.
5. Open savings only after its eligibility gate passes; arrange funding only with explicit authorization.
6. Re-check the old checking account's closure conditions after balances and pending activity are current. Explain the applicable fee and notice, obtain closure confirmation, and only then close it.

Never promise that a checking account can be closed or that an APY can be attained while required facts remain unknown.

## Calculator interface

Run `scripts/evaluate_bank_plan.py` with a JSON object on stdin. It writes one JSON object to stdout and makes no network or banking calls.

Input schema:

```json
{
  "target_balance": 100000,
  "savings_candidates": [
    {
      "savings_class": "Official Savings Account Name",
      "base_apy": 0.0,
      "opening_deposit_minimum": 0,
      "ongoing_balance_minimum": 0,
      "eligible": true,
      "checking_options": [
        {"checking_class": "Official Checking Account Name", "boost_apy": 0.0, "eligible": true}
      ],
      "card_options": [
        {"card_name": "Card Name", "boost_apy": 0.0, "eligible": true}
      ]
    }
  ]
}
```

`eligible` is `true`, `false`, or `null` (unknown). Provide checking options only when the documented pairing applies. The script returns `viable_plans`, `conditional_plans`, and `rejections`, with each plan's base and selected non-stacked boosts. Validate that the recommendation uses only `viable_plans`, that each selected class is an exact official class, and that all action prerequisites above have independently passed.
