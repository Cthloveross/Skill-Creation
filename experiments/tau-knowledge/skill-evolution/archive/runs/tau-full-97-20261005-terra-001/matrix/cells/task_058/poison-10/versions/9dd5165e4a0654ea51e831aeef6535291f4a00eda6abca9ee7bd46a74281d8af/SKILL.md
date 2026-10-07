---
name: savings-card-yield-planning-and-opening
description: Evaluate a customer's savings-account and credit-card combinations by projected one-year net yield, then safely open a selected personal savings account and arrange its funding. Use for requests to maximize savings interest net of card annual fees, including optional immediate funding from an existing checking account.
---

# Savings and Card Yield Planning and Opening

Use this skill when a customer wants a savings-account recommendation, potentially alongside a credit card, based on projected earnings and annual fees, and may want to open the selected savings account.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and assumptions

- Treat APY as the annual yield on a stable balance. The comparison is a projection, not a guarantee: it changes if balances, tier eligibility, product terms, or card eligibility change.
- Include only applicable bonuses. Credit-card APY bonuses do **not** stack: use only the highest applicable card bonus. Linked checking boosts likewise do **not** stack: use only the highest applicable qualifying checking boost. These two categories may stack with each other and with documented relationship or tier bonuses.
- Annual fees reduce the projected net result. Do not treat unearned signup bonuses, credits, promotions, cash back, or uncertain fee waivers as part of a one-year yield comparison unless all qualification conditions, dates, and expected value are explicitly established.
- An account/card combination is not actionable merely because it has the highest projected yield. Verify its opening requirements, ongoing balance requirements, customer eligibility, and any required linked-product conditions.
- Never invent a rate, boost percentage, account status, required deposit, application approval, available balance, or promotion eligibility from a product name.

## 1. Gather and verify required facts

Before making an account-opening or transfer action:

1. Identify the authenticated customer and verify identity using the normal verification process. When the runtime requires it, obtain customer confirmation of two identity fields, compare them with the system record, obtain the current timestamp, and create the verification audit record.
2. Verify the customer's authority and ownership of every account involved.
3. For opening personal savings, verify all of the following:
   - the customer is verified;
   - at least one Rho-Bank checking account is active;
   - the checking relationship is at least 14 days old;
   - the customer has fewer than five personal savings accounts;
   - no account is in collections or has a negative balance.
4. Gather the intended stable savings balance and expected holding period. Confirm whether the customer intends to open a new card and whether any existing cards are active under the same customer profile.
5. For each candidate, gather authoritative product facts: base APY and tier threshold, opening and ongoing minimums, annual card fee, card APY bonus, and linked-checking/relationship bonus rules. Confirm that all bonus conditions are met.
6. For a transfer, additionally verify source and destination status is `ACTIVE` or `OPEN`, the source has sufficient **available** funds, IDs are distinct, the amount is positive USD, and the customer explicitly authorized the amount and source account.

If any required control cannot be verified, do not open an account or move funds. Explain the missing item and obtain it through an authorized workflow.

## 2. Compare combinations

Use `scripts/project_net_yield.py` to make an auditable ranking from facts collected at runtime. The script is calculation-only; it neither retrieves data nor performs banking actions.

### Script interface

Run with JSON on standard input and read JSON from standard output.

Input schema:

```json
{
  "balance": 20000,
  "months_held": 12,
  "options": [
    {
      "label": "descriptive combination name",
      "savings_account": "Official Savings Account Name",
      "base_apy": 0,
      "minimum_opening_deposit": 0,
      "minimum_ongoing_balance": 0,
      "annual_fees": [{"product": "card or account", "amount": 0}],
      "card_apy_bonuses": [0],
      "checking_apy_boosts": [0],
      "other_stackable_apy_bonuses": [0],
      "eligibility_confirmed": true
    }
  ]
}
```

All APY fields are percentage points (for example, `0.5` means +0.5 percentage points). Include only card and checking bonuses that have already been verified as applicable. `annual_fees` must include every annual fee the customer will incur for that option. `months_held` is from 0 through 12.

Output contains `ranked_eligible_options`, ordered by projected net earnings, plus `ineligible_or_invalid_options` with actionable reasons. For each eligible option it reports effective APY, the selected highest card and checking boosts, gross projected interest, annual fees, and projected net earnings.

Example runnable call:

```sh
python3 scripts/project_net_yield.py <<'JSON'
{"balance":20000,"months_held":12,"options":[{"label":"candidate","savings_account":"Example Account","base_apy":4.0,"minimum_opening_deposit":500,"minimum_ongoing_balance":1000,"annual_fees":[{"product":"Example Card","amount":50}],"card_apy_bonuses":[0.5],"checking_apy_boosts":[],"other_stackable_apy_bonuses":[],"eligibility_confirmed":true}]}
JSON
```

Validate that `valid` is true before relying on the result. An option is excluded if its account name is not a full official name ending in `Account`, the projected balance is below an opening or ongoing minimum, eligibility is unconfirmed, or a numeric field is malformed.

### Explain the recommendation

Present the highest eligible projected net result and state:

- the assumed balance and holding period;
- base APY, each verified selected bonus, and effective APY;
- gross projected interest, annual fees, and net projection;
- material product requirements, such as funding minimum and ongoing balance;
- limitations: rate/eligibility can change and daily balances affect actual interest.

If there is no eligible option, do not recommend opening one. State which requirement blocks each candidate and what information or condition is needed.

## 3. Obtain the customer's decision

Before opening anything, obtain clear confirmation of:

- the exact selected savings account class, using its full official name ending in `Account`;
- the customer's decision to open that savings account;
- whether they also want to apply for a card, acknowledging that card approval is separate and subject to the documented application requirements;
- the opening-deposit plan.

Where no agent card-application tool is documented, do not claim to submit a credit-card application. Provide the documented application channel and requirements, and explain that approval, credit line, and any promotional terms are determined separately. Never represent an unverified promotion as available.

## 4. Open the selected personal savings account

Only after all eligibility checks and explicit selection confirmation succeed:

1. Unlock the internal `open_bank_account_4821` tool.
2. Call it with:
   - `user_id`: authenticated customer ID;
   - `account_type`: `savings`;
   - `account_class`: exact, full official selected account name ending in `Account`.
3. Record the new account ID and verify that the account was created as expected.

Do not substitute abbreviations, product nicknames, or a checking account class for `account_class`. If the open request fails, report the failure without asserting that an account exists, then resolve the reported validation issue before considering another attempt.

## 5. Arrange the opening deposit

After a successful opening, ask whether the customer wants to transfer the required opening deposit from their checking account now.

### Customer authorizes immediate internal transfer

1. Confirm the exact source checking account, destination (the newly opened savings account), amount, ownership, statuses, available balance, applicable fees/limits/cutoffs, and authorization.
2. Unlock `transfer_funds_between_bank_accounts_7291`.
3. Call it with `source_account_id`, `destination_account_id`, and a positive USD `amount` equal to the confirmed required deposit.
4. Verify the transfer posted once. Do not initiate a duplicate transfer.
5. If insufficient funds or an invalid account status is returned, do not claim completion. Offer a revised amount or eligible source only after re-validation and fresh authorization.

### Customer declines immediate transfer

Do not call the transfer tool. Clearly state that the customer has **30 days** to fund the new account through an internal transfer or external deposit, or the account will be closed. State the account's documented minimum opening deposit and document the customer's decision where interaction notes are supported.

## 6. Completion response

Confirm only completed actions. Include the new savings account details available from the opening result and either:

- successful funding status, amount, and source account description; or
- that funding was deferred, the required deposit amount, the 30-day deadline, and closure consequence.

Separately summarize any card application guidance. Do not imply the card was opened, approved, linked, or its APY bonus applied unless a supported process actually confirms it.
