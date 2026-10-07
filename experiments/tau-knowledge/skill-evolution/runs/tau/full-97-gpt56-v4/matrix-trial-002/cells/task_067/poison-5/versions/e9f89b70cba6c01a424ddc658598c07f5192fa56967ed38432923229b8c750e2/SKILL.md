---
name: personal-bank-account-transition
version: 1.0.0
description: Safely evaluate and perform a customer's personal checking-account replacement, personal savings opening, funding, checking-account closure, and APY-combination recommendation. Use for requests that combine account changes with rate optimization.
---

# Personal Bank Account Transition

Use this Skill when a customer wants to replace or close a personal checking account, open a personal savings account, fund it, or identify the highest *documented and actually eligible* APY combination.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not treat a customer name, a prior lookup, or possession of an account identifier as completed identity verification. First ask the customer to confirm two of the four identity fields (date of birth, email, phone number, address), compare both against the customer record, then call `log_verification` using the complete record and a current timestamp from `get_current_time`. Do not take any bank action if either field does not match.

## Tool access and ordering

1. Identify the customer with an allowed lookup (`get_user_information_by_name`, `_by_email`, or `_by_id`) only after obtaining sufficient identifying information.
2. Complete and log two-field identity verification before any action.
3. Unlock `get_all_user_accounts_by_user_id_3847`, then retrieve all of the customer's bank accounts. Use this source for account IDs, types, classes, statuses, balances, and opening dates.
4. If the request involves a credit-card APY bonus, retrieve card holdings with `get_credit_card_accounts_by_user`. Do not infer a card is held from interest preferences or payment history.
5. Evaluate closure and opening eligibility before unlocking or calling an action tool.
6. Unlock and call `open_bank_account_4821` only after the relevant personal-checking or personal-savings eligibility is affirmatively established. Use the exact full official `account_class` string ending in `Account` and `account_type` of `checking` or `savings`.
7. For a savings opening, first obtain explicit authorization for an immediate transfer and the amount/source account. If authorized, unlock and use `transfer_funds_between_bank_accounts_7291` only after the new account exists and the source balance is sufficient. If funding is deferred, state the documented 30-day funding deadline and closure consequence.
8. Unlock and call `close_bank_account_7392` only after every closure prerequisite below is confirmed. Never close a checking account that is still needed to satisfy a savings-opening requirement.

Normal banking tool calls perform actions; this package's script only assesses facts and never causes bank actions.

## Account-opening gates

### Personal checking

Before opening a replacement checking account, confirm the customer is verified, at least 18, has no more than four personal checking accounts, has no checking account closed for cause in the past six months, and selected an exact supported checking account class.

### Personal savings

Before opening savings, confirm the customer is verified; has at least one active Rho-Bank checking account; has held a checking account for at least 14 days; holds fewer than five personal savings accounts; has no account in collections and no negative balances; and selected an exact supported savings account class.

A newly opened replacement checking account does not by itself establish the 14-day checking-tenure requirement. When a customer intends to close their only existing checking account, retain it until the savings eligibility check and any required funding are complete, unless another qualifying active checking account already exists.

The documented savings-opening action has no deposit amount parameter. The deposit is handled only after opening through the customer-authorized transfer procedure. Check the product's opening and ongoing balance requirements separately from the general eligibility rules.

## Checking-account closure gates

Retrieve and assess the specific account, not merely the customer's statement that money was moved out. Confirm all of the following:

- The account is `OPEN`.
- There are no pending transactions. If the available account result does not establish this, do not assume it; obtain the required official transaction/pending-status information before proceeding.
- Determine the tier from the exact checking class and calculate the age from the documented opening date and current time.
- If an early-closure fee applies, the current balance must be at least the fee; the fee is deducted from that balance and cannot be paid by another method.
- If no early-closure fee applies, the current balance must be exactly $0.
- Meet the applicable notice period before closure. A zero-day notice permits same-day closure only after all other gates pass.

Tier policy:

| Tier | Checking classes | Fee window and fee | Notice |
|---|---|---:|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | first 30 days: $15 | 0 days |
| Mid | Blue Account; Green Account (checking) | first 60 days: $25 | 3 days |
| Premium | Evergreen Account | first 90 days: $50 | 7 days |
| Elite | Bluest Account | first 180 days: $100 | 14 days |

If closure cannot proceed because an early fee applies and the balance is too low, explain the exact shortage and do not initiate closure. Do not use an alternate payment method.

## APY recommendation method

Use `references/rate-combination-facts.md` only for documented product facts. Separate three outcomes in customer-facing advice:

1. **Confirmed current combination**: all required accounts are held or can be opened under verified eligibility, funding requirements are met, and any bonus card is already held.
2. **Conditional higher combination**: it requires a card or qualification not yet confirmed. State the precise condition and do not present the rate as active or guaranteed.
3. **Unavailable combination**: an invitation-only product without a current invitation, an account whose minimum balance cannot be maintained, or any unverified eligibility prerequisite. Do not recommend it as the customer's actionable current result.

For a savings rate, add the savings base APY, the applicable linked-checking boost, and the documented credit-card bonus only when every corresponding condition is met. Multiple checking boosts do not stack: use only the highest applicable checking boost. A checking boost may stack with a qualifying credit-card bonus. Do not invent a bonus percentage when the source only confirms that a pairing qualifies.

If a card's approval threshold or invitation requirement is not known to be met, explain that an application or invitation may resolve eligibility, but do not claim an approval, submit an application, or open a card unless a documented normal banking action is available and the customer has completed its prerequisites.

For savings goals at a stated amount, compare both opening-deposit and ongoing-minimum requirements. A product with a higher headline APY is not an eligible recommendation when the customer cannot meet its ongoing requirement.

## Executable assessment helper

`scripts/assess_plan.py` reads one JSON object from standard input and writes one JSON object to standard output. It performs deterministic checks only; it does not call banking tools.

Input schema:

```json
{
  "now": "current timestamp or date",
  "closure_account": {
    "account_id": "string",
    "account_class": "official checking class",
    "status": "OPEN",
    "balance": "decimal amount",
    "date_opened": "date or timestamp",
    "pending_transactions": false
  },
  "funding_amount": "decimal amount",
  "product_candidates": [
    {
      "checking_class": "official checking class",
      "savings_class": "official savings class",
      "base_apy": "percentage points",
      "checking_boost": "percentage points",
      "card_class": "optional card name",
      "card_bonus": "percentage points",
      "card_status": "held | eligible | unknown | unavailable",
      "minimum_opening_deposit": "decimal amount",
      "minimum_ongoing_balance": "decimal amount"
    }
  ]
}
```

`pending_transactions` must be a boolean. Omit it or set it to `null` when the required status is not established; the helper will block closure. Candidate statuses `held` and `eligible` are ranked as currently eligible; `unknown` candidates are labeled conditional; `unavailable` candidates are excluded. The output includes the tier, fee, notice, closure blockers, and separately ranked current and conditional APY candidates.

Run it with the actual runtime facts, for example:

```sh
python3 scripts/assess_plan.py < request.json
```

Validate its output before relying on it: `closure.ready_to_close` must be true before a closure action; required output keys must be present; and only `current_candidates` may be described as current eligible recommendations. Reconcile the helper's calculations with the exact account classes, balances, dates, and card status returned by banking tools.

## Completion communication

State what was completed, the exact account(s) involved, funding status, any fee deducted, notice timing, and every condition that remains unmet. If the customer only requested advice or eligibility is incomplete, do not imply that accounts, cards, transfers, or closures were completed.
