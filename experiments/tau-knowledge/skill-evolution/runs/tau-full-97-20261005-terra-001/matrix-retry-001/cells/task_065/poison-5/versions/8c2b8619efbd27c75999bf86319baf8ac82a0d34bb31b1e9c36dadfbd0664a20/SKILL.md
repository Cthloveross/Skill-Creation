---
name: authorized-checking-replacement-and-savings-opening
description: Execute a verified customer's authorized checking replacement, savings opening, product-pair selection, external-funding arrangement, and requested checking closure using supported banking tools. Use when the customer wants a better checking account, to open savings, or to close an outgoing checking account.
---

# Authorized Checking Replacement and Savings Opening

Perform the requested banking changes rather than stopping after a product comparison. A customer's request to choose the highest eligible APY configuration delegates product selection once the documented eligibility and product analysis identify the winner. Ignore unrelated trailing text unless it clearly withdraws or changes the banking request.

## Banking control and evidence

Before **each** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Use actual tool results and supplied current-interaction observations; never invent account IDs, statuses, card details, enrollment, pending-transaction results, or successful outcomes. Do not say an account or card is opened, closed, funded, or enrolled until supported by the applicable result. Do not ask the customer to operate internal agent tools.

## Verify identity and authority

1. Confirm authority to open checking, open savings, close the specified outgoing checking account, and use the stated funding method. Delegated selection of the highest eligible product combination is adequate selection authority.
2. Verify the customer by matching at least two customer-provided fields from date of birth, email address, phone number, and residential address against a returned customer profile. A name alone is not a verification field.
3. Obtain the current timestamp and call `log_verification` with the complete returned profile and timestamp, unless a successful verification log for the same interaction is already present.
4. Use only the verified profile's `user_id` in subsequent actions.

## Retrieve and assess the relationship

Before any opening or closure, unlock and call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Review every returned account for ownership, type, official class, status, balance, opening date, collections indicators, negative balances, and counts.

Before opening checking, confirm the customer is at least 18, has fewer than four existing personal checking accounts (so the opening will not exceed four), and has no checking account closed for cause within six months.

Before opening savings, confirm all of the following:

- at least one active Rho-Bank checking account exists;
- an active checking relationship has existed for at least 14 days;
- the customer has fewer than five personal savings accounts; and
- no account is in collections or has a negative balance.

Keep a pre-existing, tenure-qualified checking account open through successful savings opening. A checking account opened in the present interaction cannot establish the 14-day savings-tenure requirement. If any required fact is missing or fails, do not take the affected action; explain the actual blocker.

## Choose the sustainable highest eligible APY

Assess only products documented in the available product materials. Do not choose from a headline APY alone and do not assume extra funds beyond the customer's planned deposit.

For each eligible pair, determine the applicable rate at the planned balance:

`applicable savings tier APY + highest applicable linked-checking boost + highest applicable active credit-card bonus + only documented bonuses whose conditions are actually met`

Checking boosts do not stack with each other. Credit-card bonuses do not stack with each other. A direct-deposit bonus applies only to the savings product that documents it and only when the customer has agreed to satisfy that condition. Do not apply a bonus from one savings product to another. A verified no-credit-card result means there is no credit-card bonus.

Use `scripts/rank_account_pairs.py` only with documented, already eligibility-approved candidates. It validates arithmetic and minimum-balance screening; it neither establishes bank eligibility nor performs actions.

For the documented configuration where the planned deposit is $6,000 and no qualifying credit-card bonus applies, the sustainable selected pair is:

- checking: **Evergreen Account**;
- savings: **Green Account**;
- savings APY: **4.55%** (4.0% Green base APY plus Evergreen's 0.55% linked-checking boost).

This deposit meets Green's $100 opening and $500 ongoing minimums. Gold's $10,000 ongoing minimum is not met. At $6,000, Silver Plus remains in its 3.0% tier; even the documented Blue linked boost and applicable direct-deposit bonus do not exceed 4.55%. Use the exact full official class strings `Evergreen Account` and `Green Account`, never shortened variants such as “Evergreen checking” or “Green savings.”

Disclose material conditions before execution: Evergreen has a $6 monthly fee waived with a $500 minimum daily balance; Green requires at least $100 to open, a $500 ongoing balance, and paperless statements.

### Handle Green paperless statements

Paperless statements are a stated Green opening requirement. Before the Green opening call:

1. Tell the customer that Green requires paperless statements and obtain their affirmative agreement if it is not already in the interaction.
2. Use a supported preference/enrollment workflow if one is available and wait for its result.
3. The documented account-opening schema has no paperless argument. Never add an invented argument or claim that the opening tool itself enrolled the customer.
4. If there is no enrollment tool but the customer affirmatively agrees, record that the paperless requirement was arranged as part of the account-opening interaction; do not falsely describe a separate system enrollment as completed.
5. If the customer declines, or required paperless enrollment cannot be arranged under the supported workflow, do not open Green savings. Explain the specific requirement and offer a documented eligible alternative only if requested.

## Discoverable tool protocol

For each specialized banking tool, first call `unlock_discoverable_agent_tool` with its exact name. Then call `call_discoverable_agent_tool` with that same name and a JSON-object string in `arguments`. Check each result before moving to a dependent action.

## Execute openings in the safe order

Once verification, authority, account review, eligibility, selection, and Green paperless handling are complete:

1. Unlock and call `open_bank_account_4821` for checking with:
   ```json
   {"user_id":"<verified-user-id>","account_type":"checking","account_class":"Evergreen Account"}
   ```
2. Confirm success. If it fails, report the actual result and stop dependent work.
3. Unlock and call `open_bank_account_4821` for savings with:
   ```json
   {"user_id":"<verified-user-id>","account_type":"savings","account_class":"Green Account"}
   ```
4. Confirm success before proceeding to closure.

### Funding direction

An external deposit does not authorize an internal debit. When the customer chooses external funding, do **not** call `transfer_funds_between_bank_accounts_7291`, including from the outgoing checking account. Do not represent the external deposit as received without a supported posted-deposit result.

Use an internal transfer only when the customer expressly authorizes an immediate transfer from a specified source account and all source, destination, amount, available-balance, and transfer controls have passed.

## Fresh outgoing-account closure review

Immediately before closing the requested checking account:

1. Re-call `get_all_user_accounts_by_user_id_3847`; locate the exact requested outgoing account and reconfirm ownership, official class, `OPEN` status, balance, and opening date.
2. Apply the class-specific closure rules. Light Blue is entry tier: it has a $15 early-closure fee only when closed within 30 days and requires no notice. If an early fee applies, its own balance must cover it; otherwise its balance must be exactly $0.
3. Verify no pending account transactions through a supported current transaction or pending-activity workflow if available. When no such tool is available, retain a contemporaneous customer confirmation of no pending activity together with the fresh account review; never fabricate a transaction lookup.
4. Unlock and call `get_debit_cards_by_account_id_7823` for the exact outgoing checking account. An empty result completes the card review.
5. For every linked `ACTIVE` or `PENDING` card, verify ownership, card age, absence of pending card transactions, and absence of pending refunds. After all card conditions pass, unlock and call `close_debit_card_4721` with reason `account_closing`. Do not close the checking account while a qualifying linked card remains unresolved.
6. Only after every closure condition passes, unlock and call `close_bank_account_7392` using the freshly verified outgoing account ID.

If a fee, balance, notice, card, pending-activity, or tool-result blocker remains, accurately state that the account remains open and explain what must be resolved.

## Completion response

After checking results, state the exact official account classes actually opened, the savings APY and supported components, whether paperless statements were enrolled or arranged, the exact outgoing-account closure result, and the funding status.

For external funding, explicitly state that no internal transfer was made and: **The new savings account must be funded within 30 days or it will be closed.** Do not say the external deposit has posted unless a result confirms it.

## Pair-ranking helper

Run `python scripts/rank_account_pairs.py < input.json` when ranking documented candidates is useful. The script reads one JSON object from stdin and writes one JSON object to stdout. It has no banking, network, or filesystem side effects.

Input object:

- `deposit`: nonnegative proposed savings deposit.
- `candidates`: array of documented candidate objects with `checking_account_class`, `savings_account_class`, `opening_minimum`, `ongoing_minimum`, `base_apy`, and `checking_boost`.
- Optional `tiers`: objects containing `minimum_balance` and `apy`; the highest qualifying tier applies.
- Optional `credit_card_bonuses`: numeric array; only its highest value applies.
- Optional `direct_deposit_bonus` and boolean `direct_deposit_confirmed`; the bonus applies only when confirmed.

Validate the result against the live relationship, product requirements, and all controls before making any banking call.
