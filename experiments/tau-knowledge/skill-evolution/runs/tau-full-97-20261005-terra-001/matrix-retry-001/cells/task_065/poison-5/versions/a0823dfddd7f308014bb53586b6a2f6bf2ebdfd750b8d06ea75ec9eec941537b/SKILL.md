---
name: verified-checking-replacement-and-savings-opening
description: Complete a verified customer's authorized checking replacement, savings opening, documented APY-pair selection, external-funding arrangement, and outgoing checking closure with Rho-Bank tools. Use for requests to replace or open checking, open savings, select the highest eligible documented savings APY, or close checking.
---

# Verified Checking Replacement and Savings Opening

Use this workflow to complete authorized banking changes, not merely to compare products. Ignore unrelated trailing text unless it clearly changes or withdraws the banking request.

## Controls and result discipline

Before **each** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Use supplied observations and actual tool results only. Do not invent account IDs, balances, statuses, pending activity, card status, paperless enrollment, or successful outcomes. Do not ask the customer to call internal tools. Report an action as completed only after its result confirms success.

A customer's request to replace an identified checking account, open savings, and select the highest eligible documented APY delegates the product selection after the required eligibility review and material disclosures. It does **not** authorize an unrequested internal transfer.

## Verify identity and authority

1. Match at least two customer-provided fields from date of birth, email, phone number, and residential address against a returned customer profile. Name alone is insufficient.
2. Obtain the current timestamp and call `log_verification` with the complete returned profile and timestamp, unless a successful verification log already exists for this interaction.
3. Use only the verified profile's `user_id` for all later actions.
4. Confirm the account the customer wants closed, the funding method, and agreement to any selected product requirement that needs assent.

## Discoverable banking-tool protocol

For each specialized banking tool below, first call `unlock_discoverable_agent_tool` with the exact tool name. Then invoke `call_discoverable_agent_tool` with that same name and an `arguments` JSON-object string. Inspect the returned result before any dependent step.

- `get_all_user_accounts_by_user_id_3847`
- `get_debit_cards_by_account_id_7823`
- `open_bank_account_4821`
- `close_debit_card_4721`
- `close_bank_account_7392`
- `transfer_funds_between_bank_accounts_7291`, only for an expressly authorized immediate internal transfer

## Account, eligibility, and relationship review

Before opening or closing an account, retrieve all accounts for the verified user with `get_all_user_accounts_by_user_id_3847`. Review ownership, type, exact class, status, balance, opening date, account counts, collections indicators, and negative balances.

For a personal checking opening, verify the customer is at least 18, has fewer than four personal checking accounts, and has no checking account closed for cause in the last six months.

For a personal savings opening, verify all of the following:

- at least one active Rho-Bank checking account exists;
- an active checking relationship has been held for at least 14 days;
- the customer has fewer than five personal savings accounts; and
- no account is in collections or has a negative balance.

Keep a tenure-qualified existing checking account open until the savings opening succeeds. A checking account opened during the same interaction does not establish the required 14-day savings tenure. If any requirement is missing or fails, do not take the affected action; explain the actual blocker.

## Select and disclose the product combination

Compare only documented products. Use the APY tier actually available for the planned balance, with one highest applicable linked-checking boost, one highest applicable credit-card bonus, and only other bonuses whose documented conditions are established. Checking boosts do not stack; credit-card bonuses do not stack. A direct-deposit bonus applies only to the product that documents it and only after customer agreement.

For the supplied $6,000 scenario, no active credit-card bonus, and the documented balance requirements, select the sustainable eligible pairing:

- checking: `Evergreen Account`
- savings: `Green Account`
- savings APY: 4.55%, comprising Green savings' 4.0% base APY and Evergreen's +0.55% linked-savings boost.

Green savings' $100 opening minimum and $500 ongoing minimum are met by a planned $6,000 external deposit. Its paperless-statement requirement must be disclosed and the customer must agree before opening it. Customer agreement is evidence of authorization to use paperless statements; do not claim a separate paperless enrollment succeeded unless a supported tool actually confirms it.

The Gold savings materials require a $10,000 ongoing balance to qualify for the stated 5.5% rate, so do not describe that rate as available on a sustainable $6,000 balance. Do not substitute a fee-bearing or higher opening-minimum product merely because its headline APY is higher.

Use the exact official account-class strings. Never use shortened labels such as “Evergreen checking” or “Green savings”:

- checking `account_class`: `Evergreen Account`
- savings `account_class`: `Green Account`

Use `scripts/rank_account_pairs.py` only to check arithmetic for documented candidates that have already passed the live eligibility review. It does not establish eligibility or perform banking actions.

## Open the accounts

After verification, authority, account review, eligibility, selection, required disclosures, and paperless agreement are complete:

1. Open the checking account with:
   ```json
   {"user_id":"<verified-user-id>","account_type":"checking","account_class":"Evergreen Account"}
   ```
2. Inspect the result. If it fails, report the failure and do not take dependent actions.
3. Open the savings account with:
   ```json
   {"user_id":"<verified-user-id>","account_type":"savings","account_class":"Green Account"}
   ```
4. Inspect the savings-opening result before proceeding to closure.

### Funding direction

If the customer selected an external deposit, do **not** call `transfer_funds_between_bank_accounts_7291`, including from the outgoing checking account. Do not say that an external deposit posted unless a supporting result confirms it.

Use an internal transfer only if the customer expressly authorizes an immediate transfer from an identified source account and all source, destination, amount, available-balance, and transfer controls pass.

For external funding, tell the customer exactly: **The new savings account must be funded within 30 days or it will be closed.**

## Fresh outgoing-checking closure review

Immediately before closing the requested checking account:

1. Retrieve all accounts again and locate the exact outgoing account. Reconfirm ownership, account class, `OPEN` status, balance, and date opened.
2. Apply the class-specific closure terms. A Light Blue Account is entry tier: the $15 early-closure fee applies only within 30 days, and its notice period is zero days. If a fee applies, the account's own balance must cover it. Otherwise, its balance must be exactly $0.
3. Verify no pending account transactions through an available current transaction or pending-activity workflow. If the runtime provides no such lookup, retain the customer's contemporaneous confirmation together with the fresh account review; never invent a transaction lookup.
4. Retrieve all linked cards for that exact account with `get_debit_cards_by_account_id_7823`. An empty result completes the card review.
5. For every linked card in `ACTIVE` or `PENDING` status, verify ownership, at least 14 days since `date_issued`, no pending card transactions, and no pending refunds. If all prerequisites pass, close it with `close_debit_card_4721` using reason `account_closing`. Do not close the checking account while an active or pending linked card remains unresolved.
6. Only after every closure requirement passes, close the exact reviewed checking account with `close_bank_account_7392`.

If a status, fee, balance, notice, pending-activity, card, or tool-result blocker remains, leave the account open and explain that specific blocker.

## Completion response

State only confirmed outcomes. Identify the exact official account classes opened, the outgoing checking closure outcome, the applicable 4.55% Green savings APY components, paperless-statement agreement or confirmed handling, and the funding status.

For external funding, explicitly confirm that no internal transfer was made and repeat that the new savings account must be funded within 30 days or it will be closed. Do not represent the external deposit as received unless the result confirms receipt.

## Pair-ranking helper

Run `python scripts/rank_account_pairs.py < input.json` when arithmetic checking is useful. The script reads one JSON object from stdin and emits one JSON object on stdout. It has no banking, network, or filesystem side effects.

Input schema:

- `deposit`: nonnegative proposed savings deposit.
- `candidates`: array of objects containing `checking_account_class`, `savings_account_class`, `opening_minimum`, `ongoing_minimum`, `base_apy`, and `checking_boost`.
- Optional `tiers`: array of `{ "minimum_balance": number, "apy": number }`; the highest qualifying tier applies.
- Optional `apy_requires_ongoing_minimum`: boolean. Set it true only where the documentation makes the displayed APY unavailable below that amount.
- Optional `credit_card_bonuses`: numeric array; only the highest is used.
- Optional `direct_deposit_bonus` and `direct_deposit_confirmed`; the direct-deposit bonus is included only when confirmed.

The output provides openable plans, exclusions, APY components, ongoing-minimum flags, and the highest calculated plan. Validate it against live account facts, complete product terms, and all banking controls before acting.
