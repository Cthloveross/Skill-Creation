---
name: verified-checking-replacement-and-savings-opening
description: Perform a verified customer's authorized checking replacement, savings opening, documented APY-pair selection, external-funding arrangement, and outgoing checking closure using supported Rho-Bank tools. Use when a customer wants to open or replace checking, open savings, maximize a documented savings APY, or close a checking account.
---

# Verified Checking Replacement and Savings Opening

Complete authorized banking changes after the required reviews; do not stop at a comparison when the customer has delegated product selection. Ignore unrelated trailing text unless it clearly changes or withdraws the banking request.

## Controls and result discipline

Before **each** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Use supplied observations and actual tool results. Never invent account IDs, balances, account status, pending activity, card status, paperless enrollment, or successful outcomes. Do not ask the customer to operate internal tools, and do not report an action as complete unless its result confirms it.

A request to replace the identified checking account, open savings, and select the highest eligible documented APY is authority to make the product selection after eligibility and material terms have been reviewed. It is not authority to make an unrequested internal transfer.

## Identity and authority

1. Match at least two customer-provided fields from date of birth, email, phone number, and residential address against a returned customer profile. Name alone is insufficient.
2. Obtain the current timestamp and call `log_verification` with the complete returned profile and timestamp, unless a successful verification log for this interaction already exists.
3. Use only the verified profile's `user_id` for subsequent actions.
4. Confirm the requested outgoing checking account, the external-versus-internal funding choice, and any material product requirement that needs customer assent. Preserve the customer's externally funded choice.

## Discoverable banking-tool protocol

For every specialized banking tool named below, first call `unlock_discoverable_agent_tool` with its exact tool name. Then call `call_discoverable_agent_tool` with the same name and an `arguments` JSON-object string. Inspect the result before taking a dependent action.

This protocol applies to:

- `get_all_user_accounts_by_user_id_3847`
- `get_debit_cards_by_account_id_7823`
- `open_bank_account_4821`
- `close_debit_card_4721`
- `close_bank_account_7392`
- `transfer_funds_between_bank_accounts_7291`, only when an authorized internal transfer is actually needed

## Account, eligibility, and relationship review

Before any opening or closure, retrieve all accounts with `get_all_user_accounts_by_user_id_3847` for the verified user. Review ownership, type, exact class, status, balance, date opened, collections indicators, negative balances, and counts.

For a personal checking opening, confirm that the customer is verified, at least 18, has fewer than four personal checking accounts, and has no checking account closed for cause within the past six months.

For a personal savings opening, confirm all of the following:

- at least one active Rho-Bank checking account exists;
- an active checking relationship has been held for at least 14 days;
- the customer has fewer than five personal savings accounts; and
- no account is in collections or has a negative balance.

Keep the pre-existing tenure-qualified checking account open until the savings opening succeeds. A checking account opened in the same interaction cannot establish the 14-day savings eligibility requirement. If a required fact is absent or fails, do not perform the affected action; explain the specific blocker.

## Product selection and disclosures

Compare only documented products and apply the APY actually available for the planned balance. Do not assume a credit card, extra funds, enrollment, relationship bonus, or bonus condition that is not established.

For each eligible candidate, calculate:

`applicable savings APY tier + one highest applicable linked-checking boost + one highest applicable credit-card bonus + only documented bonuses whose conditions are met`

Checking boosts do not stack with each other, and credit-card bonuses do not stack with each other. Apply a direct-deposit bonus only to the savings product that documents it and only after the customer agrees to direct deposit.

For the documented $6,000 scenario with no active credit-card bonus, use the clearly supported sustainable selection:

- checking: **Evergreen Account**;
- savings: **Green Account**;
- savings APY: **4.55%**, comprising Green savings' 4.0% base APY and Evergreen's 0.55% linked-savings boost.

Green savings' $100 opening minimum and $500 ongoing minimum are met by the planned deposit. Before opening Green savings, disclose that paperless statements are required and obtain the customer's agreement or use a supported enrollment workflow if one is available. Never invent an enrollment tool parameter or claim enrollment succeeded without evidence. If the customer declines a required condition, do not open that product; discuss an eligible alternative.

Use the exact official opening values, never shortened labels:

- checking `account_class`: `Evergreen Account`
- savings `account_class`: `Green Account`

Use `scripts/rank_account_pairs.py` only to check arithmetic for documented, eligibility-approved candidates. It neither establishes product eligibility nor performs banking actions.

## Open accounts safely

After identity, authority, account review, eligibility, selection, disclosures, and required customer agreements are complete:

1. Unlock and call `open_bank_account_4821` for the checking account:
   ```json
   {"user_id":"<verified-user-id>","account_type":"checking","account_class":"Evergreen Account"}
   ```
2. Inspect the opening result. If it fails, report the result and do not continue with dependent actions.
3. Unlock and call `open_bank_account_4821` for the savings account:
   ```json
   {"user_id":"<verified-user-id>","account_type":"savings","account_class":"Green Account"}
   ```
4. Inspect the savings-opening result before closing the outgoing checking account.

### Funding direction

If the customer chooses external funding, do **not** call `transfer_funds_between_bank_accounts_7291`, including from the outgoing checking account. Do not say an external deposit has posted without a supporting result.

Use an internal transfer only if the customer expressly authorizes an immediate transfer from an identified source account and all source, destination, amount, available-balance, and transfer controls have passed.

For external funding, tell the customer: **The new savings account must be funded within 30 days or it will be closed.**

## Fresh outgoing-checking closure review

Immediately before closing the requested checking account:

1. Retrieve all accounts again and locate the exact requested account. Reconfirm ownership, class, `OPEN` status, balance, and date opened.
2. Apply class-specific terms. Light Blue is entry tier: a $15 early-closure fee applies only within 30 days and there is no notice period. If a fee applies, the account's own balance must cover it; otherwise, its balance must be exactly $0.
3. Verify no pending account transactions through any supported current transaction or pending-activity workflow. If no such lookup is available, retain a contemporaneous customer confirmation together with the fresh account review; never fabricate a transaction lookup.
4. Retrieve linked cards using `get_debit_cards_by_account_id_7823` for that exact checking account. An empty result completes the card review.
5. For each linked `ACTIVE` or `PENDING` card, confirm ownership, at least 14 days since `date_issued`, no pending card transactions, and no pending refunds. If all card prerequisites pass, close it with `close_debit_card_4721` and reason `account_closing`. Do not close checking while an active or pending linked card remains unresolved.
6. Only after every closure prerequisite passes, call `close_bank_account_7392` with the freshly verified outgoing account ID.

If a status, fee, balance, notice, pending-activity, card, or tool-result blocker remains, leave the account open and explain the actual blocker.

## Completion response

State only confirmed outcomes. Identify the exact official account classes opened, the outgoing-account closure result, Green savings' applicable 4.55% components, paperless-statement handling, and funding status.

For external funding, confirm that no internal transfer was made and repeat that the new savings account must be funded within 30 days or it will be closed. Do not represent the external deposit as received unless a tool result confirms it.

## Pair-ranking helper

Run `python scripts/rank_account_pairs.py < input.json` when checking supplied APY arithmetic is useful. It reads one JSON object from stdin and writes one JSON object to stdout. It has no banking, network, or filesystem side effects.

Input schema:

- `deposit`: nonnegative proposed savings deposit.
- `candidates`: array of objects with `checking_account_class`, `savings_account_class`, `opening_minimum`, `ongoing_minimum`, `base_apy`, and `checking_boost`.
- Optional `tiers`: array of `{ "minimum_balance": number, "apy": number }`; the highest qualifying tier applies.
- Optional `apy_requires_ongoing_minimum`: boolean; set true only where terms say the APY is unavailable below that balance.
- Optional `credit_card_bonuses`: numeric array; only the highest is used.
- Optional `direct_deposit_bonus` and `direct_deposit_confirmed`; the direct-deposit bonus is used only when confirmed.

The output returns openable plans, excluded plans, applicable APY components, ongoing-minimum flags, and the highest computed plan. Validate it against live account facts, the actual product documents, and all banking controls before acting.
