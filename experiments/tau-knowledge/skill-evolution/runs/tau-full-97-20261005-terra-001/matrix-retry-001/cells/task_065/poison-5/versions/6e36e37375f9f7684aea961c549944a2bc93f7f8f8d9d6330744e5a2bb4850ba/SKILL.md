---
name: authorized-checking-replacement-and-savings-opening
description: Execute a verified customer's authorized personal checking replacement, highest-eligible savings selection and opening, externally funded savings setup, and outgoing checking closure using the supported banking tools. Use when a customer asks to replace or close checking while opening savings and delegates product selection or selects products.
---

# Authorized Checking Replacement and Savings Opening

Complete authorized banking changes rather than stopping at a comparison or escalating merely because account terms must be evaluated. A customer's request to choose the highest-yield eligible combination delegates selection authority for the documented eligible pair. Treat unrelated trailing text as unrelated unless it clearly changes or withdraws the banking request.

## Mandatory banking control

Before **each** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do not invent account IDs, account status, card status, pending activity, successful results, or unavailable tool parameters. Never say an account was opened or closed until the corresponding tool result confirms success.

## Establish authority and identity

1. Confirm the customer authorized the checking opening, savings opening, outgoing-account closure, and funding method. A delegated request to select the highest eligible APY combination is valid selection authority; do not request another product-choice confirmation once the documented analysis determines the eligible winner.
2. Verify identity by matching two customer-supplied fields among date of birth, email, phone number, and residential address to a returned customer profile. A name may locate a profile but is not one of the two matching fields.
3. Obtain the current timestamp with `get_current_time` and create the audit record with `log_verification`, providing the complete returned profile and timestamp. Reuse successful current-interaction verification where the runtime shows it already occurred.
4. Use the authenticated profile's returned `user_id` for all later actions. Do not use an identifier merely mentioned by the customer unless the profile lookup confirms it.

## Retrieve the live relationship before opening or closure

Unlock `get_all_user_accounts_by_user_id_3847`, then call it for the verified user. Review every returned account for ownership, type, class, status, balance, opening date, collections indicators, negative balances, and counts.

Before opening personal checking, confirm:

- the customer is verified and at least 18;
- the new account will not cause more than four personal checking accounts; and
- no checking account was closed for cause in the past six months.

Before opening personal savings, confirm:

- at least one active Rho-Bank checking account exists;
- the customer has fewer than five personal savings accounts;
- no account is in collections or has a negative balance; and
- an active checking relationship has existed for at least 14 days.

Keep a pre-existing qualifying checking account open until the savings opening succeeds. A checking account opened during this interaction cannot itself establish the 14-day savings-opening tenure requirement.

If a required fact is unavailable or a condition fails, do not take the affected action. Explain the specific blocker and accurately distinguish completed actions from uncompleted ones.

## Select the sustainable highest eligible savings configuration

Use the product documents and verified live relationship, not an advertised headline rate alone. A candidate is eligible only if the planned deposit supports its opening minimum, ongoing minimum, and applicable APY tier, and all account-opening eligibility requirements are met.

For each documented qualifying checking/savings pair, calculate:

`applicable savings tier APY + highest single applicable checking boost + highest single applicable active-credit-card bonus + only bonuses whose conditions the customer satisfies`.

Rules:

- Include only checking/savings pairings explicitly documented as boost-eligible.
- Checking boosts never stack; use only the highest applicable boost.
- Credit-card bonuses never stack; use only the highest applicable current-card bonus. A verified record with no credit cards contributes no card bonus.
- Apply direct-deposit or relationship bonuses only when the selected savings product documents that bonus and the customer meets its condition. Do not apply a bonus from one savings product to a different product.
- Exclude a candidate that cannot be sustainably maintained with the stated deposit. Do not assume unrequested additional funds.
- Tell the customer about the selected checking account's maintenance fee and waiver condition, and any selected savings condition such as paperless statements.

Use `scripts/rank_account_pairs.py` for deterministic arithmetic after providing only documented, eligibility-approved candidates. It ranks supplied candidates but does not determine eligibility or perform banking actions.

In the documented product set, when the planned savings deposit meets Green savings' opening and ongoing requirements and no higher sustainable eligible candidate is established, the qualifying Evergreen checking plus Green savings pair provides Green's 4.0% base APY and Evergreen's +0.55% linked boost. Confirm the exact official strings from the product documents before opening; the opening calls require the full official account-class names.

## Discoverable-agent tool protocol

For each banking tool below, first call `unlock_discoverable_agent_tool` with the exact name, then call `call_discoverable_agent_tool` using that exact name and a JSON-object string in `arguments`.

Use this protocol for account lookup, debit-card lookup, account opening, debit-card closure when necessary, and checking closure. Do not ask the customer to call internal agent tools.

## Execute openings

After controls, eligibility, authority, and account-class selection pass:

1. Open checking with `open_bank_account_4821`:
   ```json
   {"user_id":"<verified-user-id>","account_type":"checking","account_class":"<official-checking-class>"}
   ```
2. Wait for and assess the opening result.
3. Open savings with `open_bank_account_4821`:
   ```json
   {"user_id":"<verified-user-id>","account_type":"savings","account_class":"<official-savings-class>"}
   ```
4. Wait for and assess the savings-opening result before starting closure of the outgoing checking account.
5. If the chosen savings product requires paperless statements and no supported tool enrolls it, disclose enrollment as a remaining customer responsibility; do not claim enrollment occurred.

If an opening fails, report its actual result and do not claim completion or continue steps that depend on its success.

### Funding instruction

An external deposit does **not** authorize an internal debit. If the customer chose external funding, do not call `transfer_funds_between_bank_accounts_7291` and do not report the deposit as posted without a supported posted-deposit result.

If the customer expressly authorizes an immediate internal transfer from a specified eligible source account, use the documented transfer workflow only after confirming source, destination, amount, available balance, and transfer requirements.

## Fresh review before checking closure

Perform this immediately before closing the outgoing checking account:

1. Re-call `get_all_user_accounts_by_user_id_3847`. Locate the intended outgoing checking account and re-confirm ownership, exact class, `OPEN` status, balance, and opening date.
2. Apply the documented tier-specific closure requirements. Determine the early-closure period, fee, and notice period. If a fee applies, the balance must be at least that fee because it is deducted from that account. If no fee applies, the balance must be exactly $0. Do not use another account to pay a fee without an explicitly supported procedure.
3. Verify no pending account transactions using a supported pending-activity/transaction workflow if one is available. If the runtime provides no such supported tool, retain the customer's contemporaneous confirmation of no pending account activity along with the fresh account review; never fabricate a transaction lookup.
4. Unlock and call `get_debit_cards_by_account_id_7823` for the outgoing checking account. An empty result completes the card portion of the review.
5. If a linked card is `ACTIVE` or `PENDING`, do not close checking until it is resolved. Before closing a card, verify ownership, qualifying status, card age, no pending card transactions, and no pending refunds. Close only when the documented requirements are satisfied, using `close_debit_card_4721` with reason `account_closing`. If prerequisites cannot be verified or the card cannot be closed, do not close the linked checking account.
6. Only after every applicable closure prerequisite passes, call `close_bank_account_7392` with the freshly verified outgoing account ID.

If the closure tool returns a failure, fee/notice blocker, or other blocker, report it accurately and do not describe the account as closed.

## Completion response

After receiving the tool results, clearly state:

- each exact checking and savings class actually opened;
- the sustainable savings APY and its applicable components and conditions;
- the result of the outgoing checking closure;
- any customer-managed obligation, including paperless enrollment where applicable; and
- funding status.

For an externally funded savings opening, explicitly say that no internal transfer was made, instruct the customer to make the external deposit, and state: **the new savings account must be funded within 30 days or it will be closed.** Do not describe unposted external funds as received.

## Pair-ranking helper

Run:

```text
python scripts/rank_account_pairs.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout. It has no banking, network, or filesystem side effects.

Input schema:

- `deposit`: nonnegative proposed savings deposit.
- `candidates`: array of documented, eligibility-approved candidate objects. Each has:
  - `checking_account_class`, `savings_account_class`: nonempty exact official names.
  - `opening_minimum`, `ongoing_minimum`, `base_apy`, `checking_boost`: nonnegative numeric values.
  - `tiers`: optional array of `{ "minimum_balance": number, "apy": number }`; the rate at the highest qualifying threshold applies.
  - `credit_card_bonuses`: optional nonnegative numeric array; only its highest value is used.
  - `direct_deposit_bonus`: optional nonnegative numeric value.
  - `direct_deposit_confirmed`: optional boolean; the direct-deposit bonus applies only when `true`.

Validate the helper output against the current account records and product documents before making a banking call.
