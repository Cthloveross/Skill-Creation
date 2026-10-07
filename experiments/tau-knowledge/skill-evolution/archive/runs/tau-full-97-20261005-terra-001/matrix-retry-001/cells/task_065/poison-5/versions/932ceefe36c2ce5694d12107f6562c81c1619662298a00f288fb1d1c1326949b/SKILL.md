---
name: authorized-checking-replacement-and-savings-opening
description: Complete a verified customer's authorized replacement of a personal checking account, opening of personal savings, evidence-based selection of the highest sustainable documented APY, external or internal opening funding, and eligible checking closure. Use when the customer asks the bank to choose and execute account changes.
---

# Authorized Checking Replacement and Savings Opening

Use this Skill for authenticated, authorized banking changes. Do not transfer a customer merely because product terms must be compared: when the customer delegates account selection, select the best eligible documented option and complete the authorized changes if all controls pass.

## Mandatory controls

Before **every** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

1. Require a current successful verification record. If none exists, compare two customer-provided identity fields from date of birth, email, phone number, and address against the customer record; obtain the current timestamp; then call `log_verification` with the complete verified customer record. A name plus email alone is only one qualifying field.
2. Confirm the requester owns the affected account and has authorized: replacement checking, selected savings, closure of the specified outgoing checking, and the funding method. A clear request to choose the highest-APY combination is delegated authorization for the resulting eligible product pair; do not ask a redundant product-choice question.
3. Retrieve live accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Use live results—not recollection—for account identifiers, ownership, type, class, status, balances, dates, account counts, negative balances, collections, and any closure-for-cause history available in the returned records.
4. Do not infer facts that a returned record does not establish. If a required eligibility or closure fact cannot be verified through available records, supported lookups, or a required contemporaneous customer confirmation, pause only the affected action and explain the blocker.

## Eligibility and sequence

### Checking opening

Before opening personal checking, establish that the verified customer is at least 18, will not exceed four personal checking accounts, and has no checking account closed for cause in the last six months. The selected `account_class` must be the exact official full product name ending in `Account`.

### Savings opening

Before opening personal savings, establish all of the following:

- verified customer;
- fewer than five personal savings accounts;
- no account in collections and no negative balance;
- at least one active Rho-Bank checking account held at least 14 days; and
- the applicable savings product's opening, ongoing-balance, and enrollment requirements.

Keep the already-tenured qualifying checking account open until the savings account has been successfully created. A newly opened replacement checking account does not itself satisfy the 14-day checking-tenure requirement. If the outgoing account is the qualifying relationship, open savings before closing it.

For a product requiring paperless statements, obtain the customer's acknowledgement or complete enrollment using only a supplied supported workflow. Do not claim enrollment occurred if no supported action completed it.

## Selecting the highest sustainable documented APY

Compare only products and bonuses supported by the supplied product terms and current customer facts. For each candidate, evaluate:

1. the proposed deposit against opening minimum, ongoing minimum, and the rate tier that actually applies at that balance;
2. whether the paired checking product is openable and is an explicitly documented qualifying pairing;
3. the single highest applicable checking boost—checking boosts never stack;
4. the single highest applicable eligible credit-card bonus—credit-card bonuses never stack; and
5. a separate bonus, such as direct deposit, only when that exact savings product documents it and the customer can meet its conditions.

Do not add a direct-deposit benefit just because direct deposit will be sent to checking. State all conditions needed to retain the quoted rate.

Under the supplied terms, when the customer delegates selection for a $6,000 external savings deposit and satisfies the opening controls, select **Evergreen Account** checking plus **Green Account** savings: Green's 4.0% base APY plus Evergreen's documented 0.55% linked-checking boost yields 4.55%, before any separately verified eligible card bonus. Green's $100 opening minimum and $500 ongoing minimum are met by $6,000. Its paperless-statement requirement still applies.

Reject options that cannot be opened and sustainably maintained at the proposed amount, including products whose ongoing minimum or applicable tier threshold exceeds the deposit. Do not use an advertised upper tier for a lower actual balance. Do not select a checking option whose own documented opening requirement cannot be met.

Use `scripts/select_savings_plan.py` to make the arithmetic reproducible after normalizing the currently documented products and currently verified customer bonuses. The helper only ranks facts supplied to it; it does not substitute for the eligibility review.

## Tool execution

Specialized bank actions are discoverable agent tools. Unlock each required tool with `unlock_discoverable_agent_tool`, then invoke it with `call_discoverable_agent_tool` and a JSON-object `arguments` value. Never ask the customer to call an internal tool.

After controls and eligibility pass, execute in this order:

1. Unlock and call `get_all_user_accounts_by_user_id_3847` for the verified user.
2. Determine the documented, eligible account pair.
3. Unlock and call `open_bank_account_4821` for checking:
   ```json
   {"user_id":"<verified-user-id>","account_type":"checking","account_class":"<exact-official-checking-class>"}
   ```
4. Confirm the checking opening succeeded. While the established qualifying checking remains active, unlock and call `open_bank_account_4821` for savings:
   ```json
   {"user_id":"<verified-user-id>","account_type":"savings","account_class":"<exact-official-savings-class>"}
   ```
5. Confirm the savings opening result. Do not make an internal transfer unless the customer expressly chose and authorized one.
6. Perform the fresh closure review below, then unlock and call `close_bank_account_7392` with the verified outgoing account ID.

Do not claim an opening or closure completed unless that specific tool returned success. If one action fails, report only completed actions and the safe next step for the failed action.

## Fresh checking-closure review

Perform this review immediately before calling the closure tool.

1. Re-retrieve accounts using `get_all_user_accounts_by_user_id_3847` and identify the outgoing checking from live data. It must be owned by the verified customer and have status `OPEN`.
2. Determine the tier and closure timing from the official class and live opening date. For Light Blue, Light Green, and Green Fee-Free checking, the $15 early-closure fee applies only within 30 days and there is no notice period. Outside that period, the balance must be exactly $0. Within it, the balance must be at least $15 because the fee is deducted from that account and no alternative payment method is allowed.
3. Verify no pending account transactions. Use a supplied supported pending-activity lookup if one is available; never invent a tool name or parameter. If none exists, obtain and retain a contemporaneous customer confirmation of no pending account transactions together with the live account review. If pending activity is found or cannot be resolved, do not close.
4. Unlock and call `get_debit_cards_by_account_id_7823` for the outgoing checking account. An empty result permits this card-control step to pass. For each linked active or pending card, verify ownership, pending transactions and refunds, age, permitted status, and closure reason; close it with the documented debit-card workflow before closing checking. A card that cannot yet be closed blocks checking closure.
5. Call `close_bank_account_7392` only after every applicable condition passes.

## Funding and completion response

When the customer chooses external funding, do not debit any Rho-Bank account and do not replace that choice with an internal transfer. After the savings account is successfully opened, clearly tell the customer:

- the stated savings deposit will be made externally and has not been moved by the bank;
- the amount and selected savings account; and
- the savings account must be funded within **30 days** or it will be closed.

Confirm the exact checking and savings classes successfully opened, the quoted APY and conditions, the closure result for the outgoing account, and the external-funding status. If paperless enrollment or any other requirement remains for the customer to complete, say so plainly.

## APY helper

Run the packaged helper as follows:

```text
python scripts/select_savings_plan.py < input.json
```

The script reads exactly one JSON object from standard input and emits exactly one JSON object to standard output. It performs no banking actions.

Input schema:

- `deposit`: nonnegative proposed savings deposit.
- `direct_deposit_confirmed`: boolean, true only if the bonus condition for that savings product is actually met or will be met as documented.
- `savings_products`: list of objects with `account_class`, `base_apy`, `opening_minimum`, `ongoing_minimum`, optional `tiers` (`minimum_balance`, `apy`), optional `direct_deposit_bonus`, optional `direct_deposit_required_for_bonus`, and optional string-list `requirements`.
- `checking_options`: list of eligible/openable checking objects with `account_class`, `available`, and `boosts`, a mapping from exact savings class to boost.
- `credit_card_bonuses`: optional mapping from savings class to currently eligible, good-standing card labels and bonus amounts.

Validate the top result before acting: its total must equal its displayed components; its selected checking class must be an available documented pairing; and the savings product must meet the proposed deposit constraints.
