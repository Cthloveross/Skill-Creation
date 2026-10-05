---
name: bank-account-transition-and-yield-planning
description: Safely advise on and execute a transition from a personal checking account to replacement checking and savings accounts, including eligibility checks, closure prerequisites, opening deposits, and comparison of linked APY boosts. Use for customer requests to open, close, replace, or optimize personal checking/savings accounts.
---

# Bank Account Transition and Yield Planning

Use this Skill for personal checking/savings account openings, closures, and yield comparisons where linked checking accounts and credit cards can affect savings APY.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A read-only lookup is not identity verification. Before any account opening, closure, transfer, or profile-changing action:

1. Ask the customer to confirm two of four identity fields without disclosing the values first: date of birth, email, phone number, or address.
2. Retrieve the authoritative customer profile, compare the two supplied factors, and obtain the current timestamp.
3. Call `log_verification` with the complete retrieved profile and timestamp only after two factors match.
4. Confirm the customer is the account owner and has authorized the specific action.

Do not take an account action when verification, authority, ownership, confirmation, or an applicable prerequisite is absent.

## Tools and safe discovery

The supplied banking tools may be discoverable rather than directly callable. When a documented internal banking tool is needed, unlock that exact tool first and then call it with the documented arguments. Never invent a tool name or parameters.

Relevant documented internal tools:

- `get_all_user_accounts_by_user_id_3847(user_id)`: retrieve account ID, type, class, status, balance, and opening date. Use for both eligibility and closure review.
- `get_bank_account_transactions_9173(account_id)`: retrieve transactions, including `pending` status. Use to establish whether a closure candidate has pending transactions.
- `open_bank_account_4821(user_id, account_type, account_class)`: open a selected account only after all opening prerequisites and explicit selection are confirmed.
- `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`: use only after the customer authorizes an immediate transfer and the source ownership, available balance, amount, destination, fees, limits, and confirmation are validated.
- `close_bank_account_7392`: close an eligible account after closure prerequisites and customer confirmation are complete.

Credit-card applications are customer dashboard actions according to the product materials. Explain the application requirements; do not open a credit card through an account-opening tool or imply that an application is approved.

## End-to-end workflow

### 1. Establish the objective and collect explicit selections

Determine whether the customer wants advice only, a checking opening, a savings opening, a closure, or a sequence of these actions. Clarify:

- desired checking and savings account classes;
- savings amount and whether the opening funds are external or should be transferred internally;
- whether the customer wants to pursue any credit card and understands its separate eligibility/application process;
- whether the customer authorizes each requested banking action.

A preference such as “best perks” or “highest APY” is not consent to open a particular account. Provide a conditional recommendation, disclose material requirements and fees, then obtain the exact official account-class selections. All account-class strings supplied to the opening tool must be full official names ending in `Account`.

### 2. Verify the customer and retrieve current accounts

Complete identity verification and log it as described above. Then retrieve all accounts. Normalize the results and run:

```sh
python3 scripts/validate_account_workflow.py <<'JSON'
{
  "now": "<current ISO timestamp>",
  "identity_verified": true,
  "accounts": [],
  "savings_opening": {"requested": true},
  "checking_opening": {"requested": true},
  "closure": {"requested": false}
}
JSON
```

The script only evaluates supplied facts; it does not verify identity, retrieve records, or execute bank actions. Treat every item reported in `missing` or `failed` as a blocker until resolved.

For savings openings, verify all of the following from authoritative data:

- the customer is verified;
- at least one active Rho-Bank checking account exists;
- an active checking account has been open for at least 14 days;
- fewer than five personal savings accounts are currently held;
- no account is in collections and no account has a negative balance.

For checking openings, verify the customer is at least 18, has fewer than four personal checking accounts, and has no checking account closed for cause in the last six months. If a required field is unavailable from the account response, obtain it from the applicable authoritative source; do not infer it.

### 3. Preserve ordering when replacing checking

Do not close the customer’s only seasoned checking account before confirming savings-opening eligibility. A newly opened checking account has no 14-day tenure. If the current checking account is the account that satisfies the tenure requirement, normally:

1. verify the current checking is active and seasoned;
2. open any selected replacement checking, subject to checking eligibility;
3. open the selected savings while the seasoned checking remains active, subject to savings eligibility;
4. complete any authorized funding; and
5. close the old checking only after the closure checks pass.

If no active checking has at least 14 days of tenure, do not open savings yet. Explain the tenure requirement and defer the savings opening until it is satisfied.

### 4. Evaluate yield without overstating certainty

Use `scripts/compare_savings_apy.py` to calculate candidate scenarios from documented figures:

```sh
python3 scripts/compare_savings_apy.py <<'JSON'
{
  "deposit_amount": "6000",
  "candidates": [
    {
      "name": "<scenario label>",
      "base_apy": "0",
      "minimum_balance": "0",
      "checking_boosts": [{"source": "<checking class>", "apy": "0"}],
      "credit_card_bonuses": [{"source": "<card>", "apy": "0"}],
      "other_additive_bonuses": []
    }
  ]
}
JSON
```

The script selects only the highest checking boost and the highest credit-card bonus. It adds those selected values to base APY and any independently documented additive bonuses. It returns ineligible scenarios when the supplied deposit is below the supplied minimum balance.

When explaining results:

- Checking boosts do not stack with each other; use only the highest applicable linked-checking boost.
- Credit-card APY bonuses do not stack with each other; use only the highest applicable credit-card bonus.
- The selected checking boost may stack with the selected credit-card bonus and independently documented relationship bonuses.
- A conditional card benefit cannot be described as current APY until the customer holds the qualifying active card under the same profile.
- A high advertised APY is not available to the stated deposit if the opening/ongoing minimum is unmet.
- Do not silently treat a document’s illustrative arithmetic as controlling. Add percentage-point boosts according to the explicit stacking policy.

For the documented product facts relevant to this workflow, see `references/product_facts.md`. If product eligibility, a required balance override, or a rate is not documented, state that it is unverified rather than calculating an “absolute” result.

### 5. Open accounts only after all gates pass

Before each opening, reconfirm the selected official account class, product requirements, funding plan, and customer authorization.

- For a personal checking account, call `open_bank_account_4821` with `account_type: "checking"` and the confirmed full class name.
- For a personal savings account, call it with `account_type: "savings"` and the confirmed full class name.
- Record the newly returned account ID and details.

For a savings opening, ask whether the customer authorizes an immediate internal transfer for the required opening deposit.

- If yes, verify source ownership, available balance, required amount, account details, limits, fees, and final confirmation; then transfer from the selected checking account to the new savings account.
- If funds are external or the customer declines the internal transfer, do not initiate a transfer. Explain that the account must be funded within 30 days by internal transfer or external deposit or it will be closed. Also disclose any product-specific opening-deposit amount and enrollment requirements.

### 6. Close the former checking account last

Use the account lookup and transaction history to validate closure prerequisites. The account must be `OPEN` and have no pending transactions.

Determine the closure tier and fee by account class and elapsed time since opening:

| Tier | Account classes | Early closure fee | Fee window | Notice |
|---|---|---:|---:|---:|
| Entry | Light Blue Account, Light Green Account, Green Fee-Free Account | $15 | within 30 days | 0 days |
| Mid | Blue Account, Green Account (checking) | $25 | within 60 days | 3 days |
| Premium | Evergreen Account | $50 | within 90 days | 7 days |
| Elite | Bluest Account | $100 | within 180 days | 14 days |

If an early closure fee applies, the balance must be at least the fee because it is deducted from that account and cannot be paid another way. If no fee applies, the balance must be exactly $0. Do not close an account with pending transactions. Confirm the applicable fee/notice and final closure authorization immediately before calling `close_bank_account_7392`.

### 7. Final response and notes

State what was completed, account details returned by the system, funding status or the 30-day deadline, any closure fee/notice outcome, and remaining customer actions. If a condition remains unmet, clearly state the blocker and the next non-action step. Never claim a card rate, account opening, transfer, or closure occurred unless the relevant tool returned success.

## Current-conversation decision aid

For a customer with $6,000 who asks for the highest documented potential savings APY, distinguish the following from guaranteed eligibility:

- The documented highest conditional path at that balance is Gold Account savings paired with Green Account (checking), while holding both an active Gold Rewards Card and active EcoCard under the same profile. Gold Rewards Card status reduces Gold’s minimum balance from $10,000 to $5,000. Green checking supplies Gold’s +0.75% linked boost, and EcoCard supplies Gold’s highest documented card bonus of +0.60%. The resulting documented calculation is 5.50% + 0.75% + 0.60% = 6.85% APY.
- Do not also add the Gold Rewards Card’s +0.025% card/relationship APY amount when using EcoCard’s +0.60%, because only the highest credit-card APY bonus applies. The Gold Rewards Card may still be required for the $5,000 Gold minimum-balance override.
- This path remains conditional on Gold Rewards Card requirements (at least 720 credit score and active Rho-Bank+ subscription), EcoCard application/approval, same-profile linking, account-opening eligibility, and the customer’s explicit selection. EcoCard has a $50 annual fee; Gold Rewards Card has a $0 annual fee.
- If the customer lacks the cards or does not wish to apply, do not promise 6.85%. Compare eligible non-card and card-pending scenarios separately.

This decision aid does not override the verification, account-tenure, opening, funding, or closure requirements above.
