---
name: banking-account-transition-and-apy-plan
description: Safely recommend and, after authentication and explicit confirmations, carry out a personal checking-account replacement, savings-account opening, and related APY optimization. Use for requests involving closing/opening bank accounts, funding a new savings account, or comparing linked checking and credit-card APY benefits.
---

# Banking Account Transition and APY Plan

Use this Skill to determine the highest **currently eligible** savings APY, explain the qualifying product combination accurately, and safely complete only the account actions the customer explicitly confirms.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and authorization rules

1. Treat an account recommendation, a statement of interest in “something better,” and a request to compare products as **not** authorization to open, close, apply for, link, or transfer anything.
2. Before any account action, authenticate the customer by obtaining and matching at least two of the four identity fields (date of birth, email, phone number, address) against the identified profile. Obtain the current timestamp and create the required verification log only after the fields match.
3. Verify the customer owns and has authority over every source account and proposed destination account. Do not rely on a name alone as authentication.
4. Never assume account status, opening date, balances, pending activity, collections status, account counts, card status, subscription status, credit score, credit approval, or product eligibility. Query supported systems or ask the customer when an item cannot be verified.
5. A product application remains subject to its stated approval requirements. Do not present a conditional card bonus as already active, and do not claim an APY is guaranteed until all qualification conditions are met.
6. Use only declared normal banking tools. A script in this package produces a recommendation only; it never performs a bank action.
7. Do not repeat an operation whose tool result is `UNKNOWN`. Preserve the result, explain that completion cannot be confirmed, and use the institution’s supported resolution path.

## APY analysis method

APY components should be evaluated separately:

- Start with the savings account’s applicable base APY for the customer’s balance tier.
- Exclude a savings product if its opening amount, ongoing minimum, balance-tier condition, or another required condition is not met by the proposed plan.
- For linked checking accounts, include a boost only where the exact checking/savings pairing is documented and both accounts are eligible and active. If multiple checking boosts could apply, select only the highest eligible checking boost.
- For credit cards, select only the highest eligible credit-card APY bonus; do **not** sum card bonuses.
- Add eligible checking and credit-card components to the base APY because these are separate bonus types. Add other bonuses only when the specific product terms explicitly state they are additive and the required conditions have been verified.
- Distinguish an available product from a merely possible application. If approval, a subscription, a score threshold, or a balance increase is needed, label the plan conditional or unavailable rather than ranking it as an active result.

Use `scripts/select_apy_plan.py` after collecting the current product terms and eligibility facts. It evaluates supplied candidate plans deterministically and returns the best eligible plan plus an auditable APY breakdown.

### Script interface

The script reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "balance": "decimal amount",
  "plans": [
    {
      "id": "stable non-customer-specific label",
      "eligible": true,
      "base_apy": "percentage points",
      "minimum_opening_deposit": "decimal amount",
      "minimum_ongoing_balance": "decimal amount",
      "other_additive_bonus_apy": "percentage points",
      "assumptions": ["verified condition or clearly labeled condition"],
      "checking_options": [
        {"name": "checking product", "boost_apy": "percentage points", "eligible": true}
      ],
      "card_options": [
        {"name": "card product", "bonus_apy": "percentage points", "eligible": true}
      ]
    }
  ]
}
```

`eligible` must be false for a plan or option that is unavailable, unverified, requires an unmet balance requirement, or is only an unapproved application. Omit optional arrays or use empty arrays when no bonus applies. All rates are percentage points (for example, `0.55`, not `0.0055`). The result includes every eligible candidate and the selected maximum checking and card bonus for each, so it can be checked before it is communicated.

Runnable call pattern:

```sh
python3 scripts/select_apy_plan.py <<'JSON'
{"balance":"CURRENT_BALANCE","plans":[...]}
JSON
```

Validate the result before use: `ok` must be true, `best_plan` must be non-null, its stated minimums must not exceed `balance`, and its `total_apy` must equal the sum of `base_apy`, `checking_boost_apy`, `card_bonus_apy`, and `other_additive_bonus_apy`. If no plan is eligible, explain which facts or requirements prevent a recommendation; do not invent a result.

## Required conversational workflow

### 1. Establish identity and scope

- Identify the customer profile using a supplied identifier or supported lookup.
- Ask for and match two identity fields, then obtain a current timestamp and log verification.
- Confirm the requested scope separately: recommendation only, closure, checking opening, savings opening, immediate funding, credit-card application, and/or account linking.
- For a request to close an account, obtain explicit confirmation identifying the exact account after disclosing any applicable closure fee or notice period.

### 2. Gather decision-critical facts

Use supported read-only account and product information to establish:

- all active checking, savings, and credit-card accounts under the verified profile;
- account ownership, status, opening dates, balances, pending transactions, account-count limits, collections/negative-balance status, and closure-for-cause history where relevant;
- the customer’s available funds and funding source for any opening deposit;
- the balance tier and minimum-balance conditions for each savings candidate;
- documented eligible checking/savings pairings and their boost amounts;
- active linked card status and card-specific APY bonuses;
- all additional prerequisites, including age, subscription, credit score, application approval, and direct-deposit or relationship conditions when applicable.

If a required fact cannot be retrieved or verified, state that it is unresolved and do not perform the dependent banking action.

### 3. Give a decision-ready recommendation

Provide a concise comparison that includes:

- the highest currently eligible total APY and its arithmetic breakdown;
- the checking, savings, and card components required to receive it;
- required balance, opening-deposit, linking, active/good-standing, application, and approval conditions;
- the best alternative if a higher plan is unavailable; and
- any benefits or limitations relevant to the customer’s stated goal.

Explicitly say that multiple credit-card bonuses do not stack and that only the highest applicable card bonus is used. Likewise, only the highest applicable checking boost is used when more than one checking account could provide a boost.

If a card is needed for the highest result but the customer has not been approved, give both the currently active rate without that card and the conditional rate if approved. Ask whether the customer wants to proceed with the specific selected products; obtain separate consent for account opening, closure, any card application, linking, and funding.

### 4. Close an existing checking account only after verification

For a checking-account closure, verify all of the following immediately before the close action:

- ownership and explicit customer authorization for the exact account;
- account status is `OPEN`;
- no pending transactions;
- tier-specific early-closure fee and notice period;
- if an early fee applies, the balance can cover it; otherwise the current holdings are zero; and
- the customer understands the fee and notice consequence.

Do not close an account if any prerequisite fails. If a closure notice period applies, explain it and do not imply instant closure. Use the declared `close_bank_account_7392` workflow only after its prerequisites are met. Record the tool result and do not retry an unknown result.

### 5. Open a replacement checking account

Before opening personal checking, verify the customer is authenticated and eligible: verified identity, age at least 18, no more than four personal checking accounts, and no checking account closed for cause during the prior six months. Confirm the exact full official `account_class` name ending in `Account`.

Use the declared `open_bank_account_4821` workflow with `account_type` set to `checking` and the confirmed account class. Re-check the result before treating the new checking account as active. If closing the old checking account would leave no active checking account while a savings opening depends on one, sequence the actions so the active-checking requirement remains satisfied.

### 6. Open a savings account and arrange funding

Before opening personal savings, verify: authenticated/verified customer; at least one active Rho-Bank checking account held for at least 14 days; fewer than five personal savings accounts; and no accounts in collections or with negative balances. Confirm the exact full official savings `account_class` ending in `Account`, and confirm the customer accepts its minimum opening deposit and ongoing balance requirements.

Use the declared `open_bank_account_4821` workflow with `account_type` set to `savings`. Do not assume opening succeeds; retain the returned destination account ID only after a successful result.

Then ask separately whether the customer authorizes an immediate transfer, naming the source checking account, destination savings account, and exact amount. Before a transfer, verify ownership, available balance, minimums, fees, limits, cutoffs, recipient/destination details, and confirmation requirements. If authorized and supported, use `transfer_funds_between_bank_accounts_7291`. If funding is deferred, communicate the documented funding deadline and closure consequence for an unfunded account.

### 7. Finish and verify

Summarize completed actions, account identifiers only as appropriate for the authenticated customer, funding status, any fees or pending dates, and the APY that is active now versus conditional. Explain that future account closure, unlinking, falling below requirements, card closure, or loss of good standing can change eligibility. Never state that a requested card application, account link, transfer, or closure succeeded without its successful tool result.

## Tool availability handling

The account-opening, transfer, and closure tools may be exposed as discoverable agent tools in a runtime. If so, unlock only the exact documented tool name and call it with verified, confirmed parameters. If a required lookup or action tool is unavailable, do not guess its parameters or simulate a result. Tell the customer what remains unverified and use an available supported handoff path only when necessary.
