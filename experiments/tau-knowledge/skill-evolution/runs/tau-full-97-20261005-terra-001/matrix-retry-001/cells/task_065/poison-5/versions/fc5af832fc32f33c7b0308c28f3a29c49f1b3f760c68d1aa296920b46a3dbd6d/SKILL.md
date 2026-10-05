---
name: authorized-checking-replacement-and-savings-opening
description: Complete a verified customer's authorized personal checking replacement, highest-eligible savings selection, externally funded savings opening, and outgoing checking closure using supported banking tools. Use when a customer wants to replace or close checking while opening savings and either selects products or delegates the product choice.
---

# Authorized Checking Replacement and Savings Opening

Complete authorized account changes; do not stop at a comparison or escalate merely because product terms must be evaluated. A request to choose the highest eligible APY combination delegates selection authority for the documented eligible winner. Ignore unrelated trailing text unless it clearly changes or withdraws the banking request.

## Mandatory banking control

Before **each** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do not invent account IDs, account status, card status, pending activity, enrollment, or successful tool results. Do not describe an account or card as opened or closed until its corresponding tool result confirms success.

## Identity and authority

1. Confirm authority for the requested checking opening, savings opening, outgoing-checking closure, and funding method. Delegated highest-eligible product selection is sufficient selection authority after the documented analysis identifies the winner.
2. Verify identity by matching two customer-supplied fields among date of birth, email, telephone number, and residential address against a returned profile. A name alone does not count as one of those two fields.
3. Obtain the current timestamp and log the complete returned profile with `log_verification`. Reuse a successful current-interaction verification only where the runtime already shows it occurred.
4. Use only the authenticated profile's returned `user_id` for later account actions.

## Review the live relationship

Unlock and call `get_all_user_accounts_by_user_id_3847` for the verified user before any account opening or closure. Review all returned accounts for ownership, account type/class, status, balance, opening date, collections indicators, negative balances, and account counts.

Before a checking opening, verify the customer is at least 18, has fewer than four personal checking accounts after the requested opening, and has no checking account closed for cause in the prior six months.

Before a savings opening, verify all of the following:

- at least one active Rho-Bank checking account exists;
- the customer has fewer than five personal savings accounts;
- no account is in collections or has a negative balance; and
- an active checking relationship has existed at least 14 days.

Keep the pre-existing qualifying checking account open through successful savings opening. A checking account opened during this interaction cannot establish the 14-day savings-tenure requirement. If any required fact is unavailable or a condition fails, do not perform the affected action; state the specific blocker.

## Select the sustainable highest eligible configuration

Use product terms and verified relationship data, not a headline APY alone. A plan is eligible only when the stated deposit meets opening, ongoing-balance, and applicable-rate-tier requirements, and all opening eligibility conditions pass. Do not assume unrequested additional funds.

For each documented qualifying checking/savings pair, calculate:

`applicable savings-tier APY + highest single applicable checking boost + highest single applicable active-credit-card bonus + bonuses whose conditions the customer satisfies`

Checking boosts do not stack. Credit-card bonuses do not stack. Apply direct-deposit, relationship, or card bonuses only if they are documented for the selected savings product and their individual conditions are met. A no-credit-card lookup contributes no credit-card bonus.

Use `scripts/rank_account_pairs.py` only after supplying documented, eligibility-approved candidates. The helper performs arithmetic; it does not establish eligibility or take banking actions.

For a $6,000 proposed deposit, the documented sustainable winner is:

- checking: **Evergreen Account**;
- savings: **Green Account**;
- Green savings APY: **4.55%** = 4.0% base + 0.55% Evergreen linked-checking boost.

Green's $100 opening minimum and $500 ongoing minimum are supported by $6,000. Gold's $10,000 ongoing minimum is not. Silver Plus earns its 3.0% lower tier at $6,000, so its Blue checking and direct-deposit bonuses do not exceed 4.55%. Do not apply Silver Plus's direct-deposit bonus to Green. Confirm the exact full official class strings immediately before calling the opening tool: `Evergreen Account` and `Green Account`.

Tell the customer about material selected-product conditions, including Evergreen's $6 monthly fee waived with a $500 minimum daily balance and Green's $100 opening deposit, $500 ongoing minimum, and paperless-statement requirement.

### Paperless statements are an opening prerequisite

Green Account savings requires paperless statements to open. Handle this **before** the Green opening call:

1. Explain that paperless statements are required and obtain the customer's affirmative agreement to use them if it has not already been provided.
2. Where the supported account-opening workflow provides a paperless-preference step, select/record paperless there before opening.
3. The documented opening-tool schema has no paperless argument. Do not invent one and do not claim that this tool enrolled the customer. If no supported workflow can record the required enrollment and no customer agreement exists, do not open Green savings; explain that enrollment must be arranged first.
4. In completion messaging, distinguish an enrollment actually confirmed by a supported result from a paperless enrollment the customer still must complete. Never say that no paperless enrollment was performed after representing Green savings as successfully opened in compliance with its opening requirements.

## Discoverable-agent tool protocol

For each banking tool below, first call `unlock_discoverable_agent_tool` with the exact tool name. Then call `call_discoverable_agent_tool` with that exact tool name and a JSON-object string in `arguments`. Do not ask the customer to call internal agent tools.

## Execute the openings

Once controls, eligibility, delegated selection, and the Green paperless prerequisite are satisfied:

1. Open replacement checking with `open_bank_account_4821` using exactly:
   ```json
   {"user_id":"<verified-user-id>","account_type":"checking","account_class":"Evergreen Account"}
   ```
2. Assess the result. If it fails, report the actual failure and do not claim completion.
3. Open savings with `open_bank_account_4821` using exactly:
   ```json
   {"user_id":"<verified-user-id>","account_type":"savings","account_class":"Green Account"}
   ```
4. Assess the result before beginning outgoing-checking closure. Do not proceed with dependent steps after a failed opening.

### Funding

An external deposit never authorizes an internal debit. If the customer chooses external funding, do **not** call `transfer_funds_between_bank_accounts_7291` and do not describe the external deposit as posted without a supported posted-deposit result.

Use an internal transfer only if the customer expressly authorizes an immediate transfer from a specified source account and all source, destination, amount, available-balance, and transfer controls pass.

## Fresh review and closure of outgoing checking

Immediately before closing the requested checking account:

1. Re-call `get_all_user_accounts_by_user_id_3847`. Locate the exact intended outgoing account and reconfirm ownership, class, `OPEN` status, balance, and opening date.
2. Apply the tier-specific closure rule. For Light Blue, the early-closure fee is $15 only within 30 days and notice is zero days. If an early fee applies, the account balance must cover it because it is deducted from that account; otherwise its balance must be exactly $0.
3. Verify no pending account transactions through a supported current pending-activity or transaction workflow if one exists. If none is available, retain a contemporaneous customer confirmation of no pending activity together with the fresh account review; never fabricate a transaction lookup.
4. Unlock and call `get_debit_cards_by_account_id_7823` for the outgoing checking account. An empty result completes the card portion of the review.
5. For every linked `ACTIVE` or `PENDING` card, verify ownership, card age, no pending card transactions, and no pending refunds. Close it with `close_debit_card_4721` and reason `account_closing` only after its requirements pass. Do not close the linked checking account while an applicable card remains unresolved.
6. Only after all closure requirements pass, call `close_bank_account_7392` with the freshly verified outgoing account ID.

If closure fails or a fee, notice, pending-activity, or card blocker remains, accurately report that the account remains open.

## Completion response

After tool results, state the exact classes actually opened, the savings APY and its applicable components/conditions, the exact result of the outgoing-account closure, paperless-statement status, and funding status.

For an externally funded savings account, explicitly state that no internal transfer was made and: **The new savings account must be funded within 30 days or it will be closed.** Do not describe an unverified external deposit as received.

## Pair-ranking helper

Run `python scripts/rank_account_pairs.py < input.json` when deterministic ranking is useful. It reads one JSON object from stdin and writes one JSON object to stdout, without banking, network, or filesystem side effects.

Input schema:

- `deposit`: nonnegative proposed savings deposit.
- `candidates`: documented and eligibility-approved candidate objects containing nonempty exact `checking_account_class` and `savings_account_class`, nonnegative `opening_minimum`, `ongoing_minimum`, `base_apy`, and `checking_boost`.
- Optional `tiers`: `{ "minimum_balance": number, "apy": number }` entries; the highest qualifying threshold applies.
- Optional `credit_card_bonuses`: numeric array; only the highest is used.
- Optional `direct_deposit_bonus` and boolean `direct_deposit_confirmed`; the bonus is used only when confirmed.

Validate its result against live account records, product documents, and all opening prerequisites before making any banking call.
