---
name: bank-account-transition-and-savings-optimization
description: Safely handles a customer's request to replace or close a personal checking account and open a checking and/or savings account, including identity verification, eligibility, closure prerequisites, exact product confirmation, funding, and APY comparison. Use whenever account-opening, account-closing, internal funding, or linked savings APY analysis is requested.
---

# Bank Account Transition and Savings Optimization

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Purpose and boundaries

Use this workflow for a customer who wants to close, replace, open, fund, or compare personal checking and savings accounts. Never open, close, or transfer funds merely because the customer expressed a general goal such as “something better” or “the highest interest.” Those are preferences, not a confirmed product selection or transfer authorization.

Do not expose internal tools or ask the customer to call them. Agent-only account tools must be unlocked and called by the agent. Treat an action with an unknown outcome as **not safe to repeat**; inspect the available records or escalate rather than attempting a duplicate action.

## Required inputs and verification

Before any account action:

1. Identify the customer using a supplied name, email, or user ID and retrieve the profile only as needed.
2. Ask the customer to confirm **two of these four profile fields**: date of birth, email, phone number, and address. Do not treat a name alone, a previously displayed profile, or an unconfirmed clarification as identity verification.
3. After two fields are confirmed, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete profile values and timestamp.
4. Confirm the customer is requesting the action for their own accounts and has authority to make each requested opening, closure, or transfer.
5. For any product opening, obtain the exact full official `account_class` selected by the customer. It must end in `Account`; do not silently normalize a nickname, infer a choice, or choose a product from a goal alone.
6. For a transfer, obtain explicit authorization for the source account, destination account, and positive USD amount.

If verification or confirmation is missing, explain exactly what is needed and pause. A customer’s selection must be confirmed even when a comparison makes one option appear preferable.

## Obtain account facts before deciding or acting

Unlock `get_all_user_accounts_by_user_id_3847`, then call it for the verified customer. Use the returned account ID, account type, class, status, balance, and date opened to establish ownership and eligibility. Do not infer an account is active, empty, old enough, or in good standing from the customer’s statement.

When closing an account, also unlock and call `get_bank_account_transactions_9173` for the specific account. Review all returned records for `pending` status. When evaluating card-linked APY, obtain the customer’s card accounts with `get_credit_card_accounts_by_user`; use only active, same-profile cards and do not assume a card exists or is eligible.

Record or communicate material limits, fees, account status, balance restrictions, cutoffs, and required funding before making a commitment.

## Personal checking opening workflow

A personal checking account may be opened only after all of the following are established:

- verified customer identity and authority;
- customer is at least 18, unless the selected product has a documented different age rule that is satisfied;
- the customer currently holds fewer than four personal checking accounts (opening another must not cause the customer to exceed four);
- no checking account was closed for cause in the preceding six months;
- the requested product’s own requirements are met; and
- the customer has selected the exact official checking `account_class`.

Unlock `open_bank_account_4821` only after these checks. Call it with the verified user ID, `account_type` set to `checking`, and the exact confirmed class. Preserve the tool result, including the newly created account ID.

If the customer is replacing an account and needs a checking account to support savings eligibility, ordinarily open the confirmed replacement first, then complete a savings opening if eligible, and only then close the old account. This avoids unnecessarily removing an active checking relationship. Do not change that sequence when the customer’s account-count limit prevents the new checking account from being opened; explain the conflict and obtain a safe, confirmed plan.

## Personal savings opening workflow

Before opening personal savings, verify all of these conditions from the account record and customer profile:

- verified identity and authority;
- at least one active Rho-Bank checking account;
- the relevant checking relationship has been held for at least 14 days;
- fewer than five personal savings accounts already held;
- no account in collections and no negative account balance;
- the selected savings product’s stated opening-deposit and product requirements are met or can be met; and
- the customer confirmed the exact full official savings `account_class`.

Unlock `open_bank_account_4821` and call it with `account_type` set to `savings` and the exact confirmed class. Do not assert that an account is funded merely because it was created.

After a successful savings opening, ask whether the customer authorizes an immediate opening-deposit transfer from a specified checking account. If yes, verify both accounts are owned by the customer, their statuses are `ACTIVE` or `OPEN`, the source has sufficient available funds, IDs differ, and the amount is positive USD. Then unlock and call `transfer_funds_between_bank_accounts_7291` with the confirmed source ID, new savings ID, and amount. Check the transfer result and do not duplicate it.

If the customer declines or cannot authorize an internal transfer, clearly state that the account must be funded within 30 days through an internal transfer or external deposit or it will be closed. Do not transfer external savings the bank cannot observe or control.

## Closing a personal checking account

Do not close an account until all closure conditions are confirmed for the exact account:

1. It is `OPEN`.
2. Its transaction history contains no pending transactions.
3. Determine its tier, account-open date, and whether the early-closure window remains active.
4. If an early-closure fee applies, the account balance must be at least the fee. The fee is deducted from the account; there is no alternate payment method. If no fee applies, `current_holdings` must be $0.
5. Observe the required notice period before closing, where applicable.
6. Confirm the customer still wants this particular account closed after the fee, balance treatment, and consequences are disclosed.

Checking closure tiers are:

| Tier | Account classes | Early closure fee | Fee window | Notice period |
|---|---|---:|---:|---:|
| Entry | Light Blue Account; Light Green Account; Green Fee-Free Account | $15 | first 30 days | 0 days |
| Mid | Blue Account; Green Account (checking) | $25 | first 60 days | 3 days |
| Premium | Evergreen Account | $50 | first 90 days | 7 days |
| Elite | Bluest Account | $100 | first 180 days | 14 days |

Use the current time and account date opened to calculate the applicable window. For example, an empty entry-tier account cannot be closed while its $15 fee applies because the fee cannot be paid from a zero balance. Never waive or move the fee to another account unless a separate documented policy and authorized tool expressly permits it.

After all prerequisites are satisfied, unlock `close_bank_account_7392` and call it for the selected account according to its discovered signature. Confirm the returned closure result. If an account is outside the documented tiers, account data is contradictory, or a notice requirement cannot be performed with available capabilities, do not guess; explain the limitation and escalate when appropriate.

## APY comparison and product recommendation

“Highest possible interest” requires a rate comparison, but not an automatic opening. Use current account and card information, the amount the customer plans to deposit, opening minimums, ongoing requirements, and the customer’s willingness to meet them.

For every plausible savings option:

1. Start with its applicable base APY tier for the planned balance.
2. Exclude or flag options whose minimum opening deposit or documented eligibility is not met.
3. From the customer’s active checking accounts (and any checking option the customer has actually selected and is eligible to open), identify matching checking/savings pairs in `references/linked_apy_pairs.md`.
4. Apply only the **single highest** applicable checking boost. Checking boosts never stack with one another.
5. Identify bonuses for the exact savings class from the relevant product documentation and active same-profile cards. Apply only the **single highest** card bonus. Card bonuses never stack with one another.
6. Add the base rate, the one checking boost, and the one card bonus. A valid checking boost and a valid card bonus may both be additive.
7. State important qualifications separately: balance tiers, minimum balance, card status, account linkage, and whether the comparison is a rate estimate rather than a guarantee.

Use `scripts/apy_optimizer.py` for deterministic ranking once the executor has collected current product rates, pairings, account records, and card records. The script only calculates a comparison; it does not establish eligibility, select a product for the customer, or invoke bank tools.

### Optimizer input and output

The script reads one JSON object from standard input and emits one JSON object on standard output.

Input fields:

- `deposit_amount`: nonnegative number or numeric string in USD.
- `savings_options`: list of objects with `account_class`, `base_apy`, and optional `minimum_opening_deposit`. `base_apy` is the applicable APY in percentage points for the planned balance.
- `checking_accounts`: list of `{ "account_class": string, "active": boolean }`. Include only current eligible accounts and already-confirmed, eligible proposed checking choices.
- `checking_boosts`: list of `{ "checking_class": string, "savings_class": string, "apy_boost": number }` derived from the current pairing policy.
- `cards_confirmed`: boolean. Set `true` only after checking the card account records.
- `credit_card_accounts`: list of `{ "card_class": string, "active": boolean }`.
- `card_boosts`: list of `{ "card_class": string, "savings_class": string, "apy_boost": number }` from the relevant savings product documentation.

The output contains a descending `ranked_options` list. Each entry reports the selected highest checking and card boosts, `estimated_total_apy`, opening-deposit feasibility, and warnings. Review warnings before communicating a recommendation.

## Communicating and completing the request

Give a concise comparison tied to the customer’s stated deposit and preferences. Clearly distinguish facts already verified from conditions still awaiting confirmation. Ask for the exact checking and savings classes before opening either one. Ask separately for authorization and source account before an internal funding transfer.

After successful actions, provide the created or closed account result, funding status or 30-day deadline, any fee or notice outcome, and the APY qualifications. Never claim a tool action succeeded without its successful returned result.

If the customer cannot be verified, required data is unavailable, a product is ineligible, a closure prerequisite fails, or the tool reports an error, do not bypass the requirement. Explain the blocker and available safe next step. Use `transfer_to_human_agents` only when the request cannot be resolved through the documented process or the customer requests a human; select the most specific available reason and summarize verified facts and unresolved blocker.
