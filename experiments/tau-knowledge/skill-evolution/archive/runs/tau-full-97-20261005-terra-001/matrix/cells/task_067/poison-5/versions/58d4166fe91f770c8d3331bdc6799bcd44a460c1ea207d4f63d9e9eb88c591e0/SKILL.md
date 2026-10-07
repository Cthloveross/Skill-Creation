---
name: personal-bank-account-replacement-and-yield-optimization
description: Handle a verified customer's personal checking replacement, savings opening, and documented APY comparison. Use when the request requires account eligibility checks, linked checking/savings APY boosts, conditional card-bonus guidance, opening-deposit handling, or safe sequencing of an old checking-account closure.
---

# Personal Bank Account Replacement and Yield Optimization

## Scope

Use this Skill for personal checking and savings account openings, closure of an existing checking account, and documented APY planning. The executor performs banking actions through normal banking tools; packaged scripts only calculate and validate plans and never execute banking actions.

Do not apply for, open, or represent approval of a credit card unless the customer separately requests that action and the applicable application requirements are verified.

## Required pre-action controls

Before **every** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

1. Retrieve the customer record using an available identifier. Do not treat lookup alone as identity verification.
2. Confirm two of the available identity fields (date of birth, email, phone number, address) against the record. Obtain the current timestamp and call `log_verification` with the complete record fields and timestamp.
3. Confirm that the verified customer is authorized to request the intended account actions.
4. Unlock and call `get_all_user_accounts_by_user_id_3847` for the verified user. Retain account IDs, types, official classes, statuses, balances, and opening dates.
5. Obtain any facts not returned by account retrieval, including pending transactions, accounts closed for cause, collections, and negative balances, from supported records or direct customer confirmation. Do not infer unavailable facts.
6. For APY planning, retrieve current credit-card accounts. No current card means no current card bonus; it does not mean product documentation is unavailable.

If required verification or eligibility information is missing, explain the specific blocker and defer only the affected action.

## APY recommendation method

Use documented product terms, not guesses. Evaluate each plausible savings product against the customer's intended opening deposit and sustainable ongoing balance. Exclude products whose ongoing requirement cannot be met, even if their advertised base APY is higher.

For each eligible savings option:

1. Start with its documented base APY.
2. Add the highest documented boost from an active or planned qualifying checking/savings pairing. Checking boosts do not stack with other checking boosts.
3. Add only the highest bonus from active, approved, eligible credit cards held under the same customer profile. Card bonuses do not stack with one another.
4. A selected checking boost and the selected card bonus may each stack with the base APY.
5. Clearly separate an available APY from a conditional APY that requires a new-card application, approval, score verification, invitation, or another unmet condition.

Use `scripts/evaluate_bank_plan.py` for repeatable arithmetic and non-stacking selection. Independently validate product eligibility, official product names, and customer authority before acting.

### Documented Platinum Plus planning rule

When a customer intends to maintain $100,000 and delegates product comparison, the documented usable recommendation is:

- **Purple Account** checking plus **Platinum Plus Account** savings.
- Platinum Plus Account has a 7.0% base APY, requires a $50,000 initial deposit, and has a $100,000 ongoing minimum balance.
- Purple Account supplies a +0.3% boost when paired with Platinum Plus Account.
- The available projected savings APY is therefore **7.3%** (7.0% + 0.3%), before any eligible credit-card bonus.

Do not recommend Diamond Elite Account solely for its 7.5% base APY when the customer intends to maintain only $100,000: its documented ongoing minimum is $250,000.

A Platinum Rewards Card can add +0.4% to Platinum Plus, making a potential 7.7% (7.0% + 0.3% + 0.4%). State this only as conditional unless the customer already holds the eligible approved card. A prospective Platinum Rewards Card requires application and approval and has a documented minimum credit score of 750. Unknown score is not approval and must not prevent the documented 7.3% checking/savings recommendation.

When the customer explicitly delegates selection (for example, asks the bank to determine the highest documented eligible combination), their delegation can serve as selection of the uniquely supported recommended checking and savings classes. State the recommended official classes and basis before executing. Obtain separate express authorization for an immediate money transfer and any credit-card application.

## Checking-opening gate

Before opening personal checking, confirm all of the following:

- The customer is verified and is at least 18 years old.
- The customer will hold no more than four personal checking accounts after opening.
- The customer has no checking account closed for cause in the previous six months.
- The exact official `account_class` has been selected or validly delegated.

Once all conditions pass, unlock `open_bank_account_4821` and call it with the verified `user_id`, `account_type` of `checking`, and the exact official class. Do not abbreviate account classes.

## Savings-opening gate and funding

Before opening personal savings, confirm all of the following:

- The customer is verified.
- At least one of the customer's Rho-Bank checking accounts is currently active or OPEN and has been held for at least 14 days.
- The customer will hold fewer than five personal savings accounts after opening.
- No customer account is in collections or has a negative balance.
- The exact official savings `account_class` is selected or validly delegated.
- The customer understands the product's opening-deposit and ongoing-balance requirements.

Only after these checks pass, unlock `open_bank_account_4821` and call it with `account_type` of `savings` and the exact official class.

After a successful savings opening, ask whether the customer authorizes an immediate transfer of the required opening deposit from a specified checking account. For Platinum Plus Account, the documented required opening deposit is $50,000.

- If authorized, verify both account IDs are distinct, customer-owned, and ACTIVE or OPEN; confirm sufficient available funds, positive USD amount, fees, limits, cutoffs, and transfer authorization. Unlock and call `transfer_funds_between_bank_accounts_7291`, then verify posting and avoid duplicates.
- If the customer declines or does not authorize an immediate transfer, state that the savings account must be funded within 30 days by internal transfer or external deposit or it will be closed.

Never use the stated savings total as authorization to move funds.

## Checking-closure gate

Before closing checking, use the retrieved account record and verify:

- The account belongs to the verified customer and is OPEN.
- There are no pending transactions.
- The applicable tier, early-closure window, fee, and notice period are known.
- If an early fee applies, the current balance is at least the fee; otherwise, it is exactly $0. The fee is deducted from that account with no alternate payment method.
- Any required notice period has elapsed and the customer has authorized closure after the consequences were explained.

For Light Blue Account, Light Green Account, and Green Fee-Free Account, the fee is $15 for closure within 30 days and the notice period is zero days. For Blue Account and Green Account (checking), the fee is $25 within 60 days and notice is three days. For Evergreen Account, the fee is $50 within 90 days and notice is seven days. For Bluest Account, the fee is $100 within 180 days and notice is 14 days.

When all conditions pass, unlock and call `close_bank_account_7392` with the documented tool parameters. Report closure only after a successful tool result.

## Required sequence for replacement plus savings

Preserve any mature active checking account needed for savings eligibility. A newly opened checking account does not itself satisfy a 14-day checking-tenure requirement.

For a verified customer replacing their only mature checking account while also opening savings:

1. Retrieve accounts and determine whether the existing checking account is OPEN and at least 14 days old.
2. Confirm checking-opening eligibility and open the selected replacement checking account.
3. While the mature existing checking remains OPEN, confirm savings eligibility and open the selected savings account.
4. Ask about the authorized opening-deposit transfer and either perform it after all transfer checks or disclose the 30-day funding consequence.
5. Recheck closure prerequisites for the old checking account, disclose the fee/notice result, obtain closure authorization, and close it only after the savings opening succeeds.

If the old checking account has already been closed and no remaining active checking account has 14 days of tenure, do not open savings; explain that savings must wait until the tenure condition is met.

## Calculator interface and validation

Run `scripts/evaluate_bank_plan.py` with JSON on stdin. It emits JSON on stdout and makes no network or banking calls.

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

`eligible` must be `true`, `false`, or `null` (unknown). Include a checking option only for a documented qualifying pairing. The result separates verified plans, conditional plans, and rejected candidates.

Before presenting or acting on a result, validate that official classes exactly match the applicable product documentation, base APY plus selected boosts equals projected APY, no ineligible candidate was recommended, and all action gates above have independently passed.
