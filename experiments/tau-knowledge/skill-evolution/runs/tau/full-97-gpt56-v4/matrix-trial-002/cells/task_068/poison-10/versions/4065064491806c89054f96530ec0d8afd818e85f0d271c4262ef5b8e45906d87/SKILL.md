---
name: checking-account-transition
version: 1.0.0
description: Safely explain, evaluate, and carry out a customer-requested transition from a personal checking account to a new checking account, optionally followed by savings opening. Use when closure, debit-card dependencies, checking-opening eligibility, early direct deposit, or linked-savings APY choices must be handled.
---

# Checking Account Transition

## Scope and safety boundary

Use this workflow for a customer who wants to close a personal checking account and/or open a replacement checking or savings account. Do not perform a banking action from a name alone, from an unverified assertion, or from a recommendation. The customer must be authenticated, the relevant records must be retrieved, all applicable conditions must be satisfied, and the customer must authorize the specific action.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

The planning helper in `scripts/evaluate_transition.py` is advisory only. It never calls a banking tool and never creates, closes, or transfers anything.

## Required information and verification

1. Obtain two of the four identity fields (date of birth, email address, phone number, address), match them against the customer profile, obtain the current timestamp, and create the required verification audit record using the normal verification tools.
2. Retrieve the customer's account records using `get_all_user_accounts_by_user_id_3847`. Identify the target account by its account ID and confirm it belongs to the authenticated customer. Do not infer the target from an account class if there is more than one possible match.
3. Retrieve the target account's transaction history using `get_bank_account_transactions_9173` and inspect every transaction with a pending status.
4. Retrieve all debit cards associated with the target checking account using the normal card-lookup capability available in the runtime. This lookup is mandatory before closing the account. If the runtime cannot establish whether cards are associated, do not close the checking account; explain that the card dependency cannot yet be verified.
5. For opening requests, count personal checking and savings accounts, review every account for negative balances or collections where relevant, determine whether any checking account was closed for cause in the preceding six months, and calculate account tenure from actual dates.

If a needed fact is unavailable, contradictory, malformed, or cannot be verified, stop before the affected action. State the precise missing condition and request it or resolve it through the applicable normal banking workflow.

## Explain a requested “close first” sequence

A customer can request that the old checking account be closed before the replacement account is opened, but this is not automatically safer or faster. Explain the concrete dependencies without falsely saying closure is prohibited:

- The old account can close only after its account-closure requirements are met and all debit cards linked to it have already been closed.
- A debit card may itself be ineligible for closure if it has pending/processing activity, pending refunds, or is too new (unless the documented lost, stolen, or fraud exception applies).
- Personal savings opening requires an existing active checking account. Therefore, if the old account is closed before a replacement checking account is open, the customer cannot open the savings account during the gap.
- A replacement checking account still needs a specifically selected account class, verified identity, eligibility, and authorization. A recommendation is not customer selection or authorization.

For a customer whose priority is the documented highest savings yield together with early direct deposit, present the documented option accurately: Green Account (checking) supports eligible direct deposit up to one day early, and its documented pairing with Gold Account (savings) provides a 0.75% savings boost. Gold Account has a documented 5.5% APY, for 6.25% before other applicable bonuses. Do not describe this as the absolute best product outside the available product documentation. Evergreen Account instead advertises eligible direct deposit up to two days early, so it may better suit a customer who prioritizes early pay over the documented Green/Gold savings pairing. Ask the customer to choose the exact checking account class and, if applicable, savings account class.

## Checking-account closure procedure

Evaluate these requirements before unlocking or calling `close_bank_account_7392`:

1. The authenticated customer owns the target account and explicitly authorizes its closure.
2. The account status is `OPEN`.
3. There are no pending transactions on the account.
4. All associated debit cards have already been closed. Do not use account closure to bypass the debit-card closure workflow.
5. Determine the early-closure tier and calculate account age using the current date and the account's `date_opened`:

   | Account class / tier | Early fee when closed within | Fee | Notice period |
   |---|---:|---:|---:|
   | Light Blue Account, Light Green Account, Green Fee-Free Account (entry) | 30 days | $15 | 0 days |
   | Blue Account, Green Account (checking) (mid) | 60 days | $25 | 3 days |
   | Evergreen Account (premium) | 90 days | $50 | 7 days |
   | Bluest Account (elite) | 180 days | $100 | 14 days |

6. If the early fee applies, the balance must be at least that fee because it is deducted directly from the account. There is no alternative payment method. If no early fee applies, the balance must be exactly $0. A negative balance never satisfies this requirement.
7. For a tier with a nonzero notice period, verify that a valid notice was recorded and that its full period has elapsed before closure. If the available workflow cannot record or verify notice, do not guess that notice has been given; use the supported servicing/escalation path.
8. Reconfirm the account ID, applicable fee, notice status, and the customer's final authorization immediately before action. Unlock and call `close_bank_account_7392` with the confirmed account ID only after every condition passes. Report the actual tool result; do not claim closure merely because it was requested.

## Linked debit-card closure dependency

When a linked card must be closed before the account:

1. Confirm the customer owns the card and is verified. Obtain/confirm the reason. For a linked-account closure, use the documented `account_closing` reason.
2. Confirm the card status is `ACTIVE` or `PENDING`; confirm no pending or processing card transactions and no pending refunds.
3. Confirm the card has been active for at least 14 days from `date_issued`. Only `lost`, `stolen`, and `fraud_suspected` bypass this age requirement; `account_closing` does not.
4. When all card requirements pass, unlock and call `close_debit_card_4721` with the confirmed `card_id` and reason. Confirm its actual closed status before proceeding to checking-account closure.
5. If a card cannot yet be closed, do not close its linked checking account. Tell the customer what must settle or when the card becomes eligible.

## Opening a replacement personal checking account

Before unlocking or calling `open_bank_account_4821` for a checking account, confirm:

- verified identity;
- customer age of at least 18;
- the projected number of personal checking accounts, including the requested account and accounting for any successfully closed account, does not exceed four;
- no checking account closed for cause in the past six months;
- the customer has selected and authorized the exact official checking `account_class` name ending in `Account`.

Then call `open_bank_account_4821` with the authenticated `user_id`, `account_type` of `checking`, and the selected official `account_class`. Confirm the returned account details before treating it as an active checking account. Do not promise direct-deposit timing until the selected product is confirmed; availability also depends on the payer's transmission schedule.

## Optional personal savings opening

Only continue when the customer requests savings and selects the exact savings class. Confirm all of the following first:

- verified identity;
- at least one active checking account at the time savings is opened;
- fewer than five personal savings accounts after the proposed opening;
- no account in collections and no negative account balances;
- qualifying checking tenure of at least 14 days;
- authorization for the specific savings class and a funding decision.

Open savings with `open_bank_account_4821` using `account_type` `savings` and the official savings `account_class` name. If the customer authorizes an immediate opening deposit, separately verify source-account ownership, available funds, exact amount, and transfer authorization before using `transfer_funds_between_bank_accounts_7291`. If funding is deferred, state the documented 30-day funding deadline and possible closure consequence. Never assume the customer's stated savings amount is a transfer instruction.

For APY discussions, check all eligible documented checking/savings pairings and apply only the highest applicable checking boost; checking boosts do not stack. Any unverified card or relationship bonus must not be included in a quoted rate.

## Helper script

`scripts/evaluate_transition.py` accepts JSON on standard input and emits a JSON eligibility report on standard output. It validates the supplied dates, balance, account status, transaction list, linked-card closure state, and projected count rules. It is useful before a tool call, but live records and the normal banking workflow remain authoritative.

Example invocation input:

```json
{
  "as_of": "2025-01-15",
  "identity_verified": true,
  "target_account": {
    "account_class": "Light Blue Account",
    "status": "OPEN",
    "balance": "0.00",
    "date_opened": "2024-10-01"
  },
  "transactions": [{"status": "posted"}],
  "linked_cards_checked": true,
  "linked_cards": [{"status": "CLOSED"}],
  "notice_given_on": null,
  "opening": {
    "age_years": 30,
    "current_checking_count": 1,
    "successful_target_closure_first": false,
    "checking_closed_for_cause_within_6_months": false,
    "selected_checking_class": "Evergreen Account",
    "selected_savings_class": null,
    "current_savings_count": 0,
    "has_active_checking_after_plan": true,
    "has_collections": false,
    "has_negative_balance": false,
    "qualifying_checking_tenure_days": 100
  }
}
```

Review `errors` first. An empty `errors` list means only that the supplied data is internally sufficient for the checks implemented by the helper; it is not a substitute for live lookup, authorization, card-specific eligibility checks, or action confirmation.
