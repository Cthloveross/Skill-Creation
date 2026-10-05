---
name: authorized-account-replacement-and-savings-opening
description: Execute a verified customer's authorized personal-checking replacement, personal-savings opening, external or internal funding choice, and checking closure. Use when the customer asks the bank to select eligible account products for them or to open and close accounts.
---

# Authorized Account Replacement and Savings Opening

Use this Skill to complete authorized banking changes, not merely to compare products. A customer who explicitly delegates selection of the best eligible account combination authorizes the resulting eligible documented selection; do not transfer or request a redundant product-choice confirmation solely because product terms must be compared.

## Controls before banking actions

Before every banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

1. Establish a current verification record. If a current successful verification is already available, use it. Otherwise, obtain two matching fields from date of birth, email, phone number, and address, retrieve the customer record, obtain the current timestamp, and call `log_verification` with the complete verified record. A name is useful for lookup but does not replace either of the two required fields.
2. Confirm authority for all requested changes: opening replacement checking, opening savings, closing the identified outgoing checking account, and the chosen funding method. A request to select the highest-yield eligible combination is delegated authority for the selected eligible pair.
3. Use live system records for account IDs, ownership, status, balances, dates, account counts, and account-history facts. Do not use an account ID recalled from conversation and do not claim that a tool action succeeded without its successful result.
4. Do not make an internal transfer unless the customer expressly authorizes an immediate transfer from a specified internal account. External funding is not authorization to debit any Rho-Bank account.

## Retrieve and review the customer relationship

Unlock and call `get_all_user_accounts_by_user_id_3847` for the verified customer before openings. Review the returned records to establish:

- ownership and an active checking relationship;
- checking and savings account counts;
- no negative balance or collections condition for savings eligibility;
- at least 14 days of tenure for an active checking account used to qualify savings; and
- the outgoing checking account's exact ID, class, `OPEN` status, balance, and opening date.

For checking opening, verify that the customer is at least 18, will not exceed four personal checking accounts, and has no checking account closed for cause in the prior six months. For savings opening, verify fewer than five personal savings accounts, no collection or negative-balance blocker, and at least one active checking account held for 14 days. Use returned history where available and any existing verified eligibility record; if a required adverse fact is found, do not open the affected account.

Keep an existing tenured checking account open through successful savings opening. A replacement checking account opened during this interaction cannot itself establish the 14-day savings-tenure condition.

Also review the customer's credit-card accounts when determining any credit-card APY bonus. No card bonus may be assumed when there is no eligible active card record.

## Select the highest sustainable documented APY

Build the choices from the current product documents and verified customer facts. For every candidate savings product, evaluate:

1. whether the proposed deposit satisfies both its opening minimum and its ongoing minimum;
2. the APY tier that applies to that actual balance, rather than an advertised higher tier;
3. whether a proposed replacement checking product can be opened and is an explicitly documented qualifying linked pair;
4. only the highest applicable checking boost for that savings product; checking boosts do not stack;
5. only the highest applicable eligible credit-card bonus; card bonuses do not stack; and
6. a direct-deposit or other bonus only if that exact savings product documents the bonus and the customer meets its condition.

Exclude products whose opening minimum, ongoing minimum, or applicable APY-tier threshold cannot be sustained at the proposed deposit. Do not use savings funds as an unrequested internal deposit to checking. Separately disclose any checking fee or balance condition that applies to the selected checking product.

If the selected savings product requires paperless statements or another enrollment condition that the opening tool cannot set, explain that condition plainly. Do not falsely state that enrollment has been completed. The inability to set a non-tool enrollment preference is not a reason to replace the customer's delegated product selection with an unsupported one; follow any opening-tool result and explain remaining customer setup.

Use `scripts/rank_account_pairs.py` for deterministic arithmetic after supplying the current documented catalog and verified eligibility facts. The script ranks supplied facts only; it neither verifies eligibility nor performs bank actions.

## Execute the account changes

Specialized actions are agent discoverable tools. For each specialized tool, first call `unlock_discoverable_agent_tool`, then call `call_discoverable_agent_tool` with that tool's exact name and a JSON-object string in `arguments`. Never ask the customer to invoke an internal bank tool.

After controls and eligibility pass, perform this sequence:

1. Retrieve live accounts as described above and select the documented eligible pair.
2. Unlock and call `open_bank_account_4821` for the replacement checking account:
   ```json
   {"user_id":"<verified-user-id>","account_type":"checking","account_class":"<exact full official checking account class>"}
   ```
   The `account_class` must be the official full name ending in `Account`.
3. Confirm the checking opening succeeded. While the previously qualifying checking remains open, unlock and call `open_bank_account_4821` for savings:
   ```json
   {"user_id":"<verified-user-id>","account_type":"savings","account_class":"<exact full official savings account class>"}
   ```
4. Confirm the savings opening result. For an externally funded account, do not call `transfer_funds_between_bank_accounts_7291`.
5. Immediately before closing the outgoing checking account, complete the fresh closure review below.
6. Only after the review passes, unlock and call `close_bank_account_7392` with the live verified outgoing account ID.

If an opening or closure fails, do not represent it as completed. Report successful actions separately and give the customer the actual blocker or next step for the failed action.

## Fresh outgoing-checking closure review

Perform this review immediately before calling the closure tool.

1. Re-call `get_all_user_accounts_by_user_id_3847` and identify the outgoing checking account in the fresh results. Confirm verified ownership and `OPEN` status.
2. Determine the applicable closure tier, early-closure window, fee, and notice requirement from the account's exact official class and opening date. If an early fee applies, the balance must be at least that fee because it is deducted from that account; otherwise the balance must be exactly zero. Do not use another account to pay an early-closure fee unless a supported procedure expressly permits it.
3. Verify no pending account transactions through an available supported transaction or pending-activity workflow. Do not invent a lookup tool or its parameters. If no such workflow is available, retain a contemporaneous customer confirmation together with the fresh account review. Pending activity blocks closure.
4. Unlock and call `get_debit_cards_by_account_id_7823` for the outgoing checking account. An empty card result passes this part of the review. Before closing an account with a linked active or pending debit card, verify card ownership, status, age, pending transactions, and pending refunds; then close each eligible card through its documented closure workflow using reason `account_closing`. A card that cannot be closed blocks checking closure.
5. Call `close_bank_account_7392` only when all applicable requirements pass.

## Completion response

After actual tool results, tell the customer:

- the exact official checking and savings account classes that were successfully opened;
- the applicable savings APY, its components, and the conditions required to retain it;
- the outgoing checking closure result;
- whether any paperless or other customer-managed setup remains; and
- the funding status.

For external funding, explicitly state that no internal transfer was made, the customer will deposit the stated amount externally, and the new savings account must be funded within **30 days** or it will be closed. Do not imply that an external deposit has posted until it is actually reflected in a supported result.

## Pair-ranking helper

Run the helper with:

```text
python scripts/rank_account_pairs.py < input.json
```

The program reads one JSON object from standard input and emits one JSON object on standard output. It has no banking, network, or filesystem side effects.

Input schema:

- `deposit`: nonnegative proposed savings deposit.
- `direct_deposit_confirmed`: boolean.
- `savings_products`: list of objects containing `account_class`, `base_apy`, `opening_minimum`, `ongoing_minimum`, optional `tiers` (`minimum_balance`, `apy`), optional `direct_deposit_bonus`, optional `direct_deposit_required_for_bonus`, and optional string-list `requirements`.
- `checking_products`: list of verified openable checking objects containing `account_class`, boolean `available`, and `boosts`, a mapping from exact savings account class to APY boost.
- `credit_card_bonuses`: optional mapping from savings account class to a mapping of currently eligible card labels to bonus APY values.

Validate the selected result before acting: the deposit must satisfy the displayed minimums, the checking product must be available, and the displayed total must equal base rate plus at most one checking boost, at most one card bonus, and any documented earned direct-deposit bonus.
