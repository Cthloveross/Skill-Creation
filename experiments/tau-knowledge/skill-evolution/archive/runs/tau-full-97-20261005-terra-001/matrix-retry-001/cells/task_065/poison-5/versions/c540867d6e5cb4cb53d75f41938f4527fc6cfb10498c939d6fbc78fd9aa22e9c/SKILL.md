---
name: authorized-checking-replacement-and-savings-opening
description: Complete a verified customer's authorized checking replacement, savings opening, product-pair selection, funding arrangement, and outgoing checking closure through supported banking tools. Use for requests to replace checking, open savings, maximize a documented savings APY, or close an outgoing checking account.
---

# Authorized Checking Replacement and Savings Opening

Complete authorized banking changes after the required reviews; do not stop at a product comparison. A request to select the highest eligible documented APY delegates the product choice after eligibility and terms have been evaluated. Ignore unrelated trailing text unless it clearly changes or withdraws the banking request.

## Banking control and result discipline

Before **each** banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Use supplied observations and actual tool results. Never invent account IDs, status, balances, pending activity, card facts, enrollment, or successful outcomes. Do not claim that an account, card, deposit, transfer, or enrollment succeeded unless the relevant tool result supports that claim. Do not ask the customer to operate internal agent tools.

## Identity and authority

1. Confirm authority to open the requested accounts, close the specifically requested outgoing checking account, and use the stated funding method. Delegation to choose the highest eligible product combination is selection authority.
2. Verify identity by matching at least two customer-provided fields among date of birth, email, phone number, and residential address against a returned customer profile. A name alone is insufficient.
3. Obtain the current time and call `log_verification` with the complete verified profile and timestamp, unless the same interaction already contains a successful verification log.
4. Use only the verified profile's `user_id` in subsequent banking actions.

## Relationship and eligibility review

Before opening or closing an account, unlock and call `get_all_user_accounts_by_user_id_3847` for the verified user. Review all returned accounts for ownership, type, exact class, status, balance, date opened, collections indicators, negative balances, and counts.

For checking opening, confirm that the customer is at least 18, holds fewer than four personal checking accounts, and has no checking account closed for cause in the prior six months.

For savings opening, confirm all of the following:

- at least one active Rho-Bank checking account exists;
- an active checking relationship has existed at least 14 days;
- fewer than five personal savings accounts exist; and
- no account is in collections or has a negative balance.

Keep the pre-existing, tenure-qualified checking account open until the savings opening has succeeded. A checking account opened during this interaction does not establish the 14-day savings-tenure requirement. If a required fact is unavailable or fails, do not perform the affected action; explain the actual blocker.

## Select the highest documented applicable APY

Assess only products supported by available product materials. Compare the rate applicable to the customer's planned balance, not a headline rate that requires an unfulfilled tier threshold. Never assume additional funds, a credit card, relationship benefit, enrollment, or bonus condition.

For each viable pair, calculate:

`applicable savings APY tier + highest applicable linked-checking boost + highest applicable active credit-card bonus + documented product-specific bonuses whose conditions are met`

Checking boosts do not stack with other checking boosts. Credit-card bonuses do not stack with other credit-card bonuses. Apply direct-deposit bonuses only to the savings product that documents one and only after the customer agrees to the condition. Do not transfer a bonus from one product to another. A verified result showing no credit cards means no credit-card APY bonus.

An ongoing balance requirement is material and must be disclosed. Do not automatically discard a product solely because a planned deposit is below its ongoing requirement when the terms still expressly state that its APY applies at that balance and instead prescribe a fee or other consequence. Conversely, exclude the product if its documents make the rate unavailable below that balance.

For the documented $6,000 configuration with no credit-card bonus, select:

- checking: **Green Account (checking)**;
- savings: **Gold Account**;
- disclosed documented rate: **6.25% APY** (Gold's 5.5% APY plus Green checking's 0.75% linked Gold-savings boost).

Gold's $5,000 opening minimum is met. Its $10,000 ongoing minimum is not met by a $6,000 planned balance, so disclose the documented $10 monthly maintenance fee below that level and that maintaining $10,000 is required for good standing. The available documents state Gold's 5.5% APY on the maintained balance and do not state that the 5.5% APY is lost below $10,000. Do not characterize the rate as guaranteed beyond the documented terms.

This exceeds Evergreen Account plus Green Account savings (4.55%) and Blue Account plus Silver Plus Account at the $6,000 tier even when the documented Silver Plus direct-deposit bonus applies (3.60%). The customer's direct-deposit willingness is not required for the Green/Gold selection.

Use exact official class strings in opening calls: `Green Account (checking)` for checking and `Gold Account` for savings. Do not substitute shortened labels.

Before opening any selected product, disclose and satisfy every documented opening requirement. If a selected product requires a preference such as paperless statements, obtain affirmative customer agreement and use a supported enrollment workflow when available. Never invent an opening-tool argument or claim an unsupported enrollment result.

Use `scripts/rank_account_pairs.py` only after candidates are documented and eligibility-approved. It validates supplied arithmetic and balance annotations; it does not establish banking eligibility or execute actions.

## Discoverable-agent tool protocol

For each specialized banking tool, first call `unlock_discoverable_agent_tool` using its exact name. Then call `call_discoverable_agent_tool` with that same name and a JSON-object string in `arguments`. Inspect the result before any dependent action.

## Open accounts in the safe order

After identity, authority, account review, eligibility, selected-product requirements, and required disclosures are complete:

1. Unlock and call `open_bank_account_4821` for checking:
   ```json
   {"user_id":"<verified-user-id>","account_type":"checking","account_class":"Green Account (checking)"}
   ```
2. Confirm the checking-opening result. If it fails, report the actual result and do not continue with dependent work.
3. Unlock and call `open_bank_account_4821` for savings:
   ```json
   {"user_id":"<verified-user-id>","account_type":"savings","account_class":"Gold Account"}
   ```
4. Confirm the savings-opening result before proceeding with the requested closure.

### Funding direction

External funding does not authorize an internal debit. If the customer chooses an external deposit, do **not** call `transfer_funds_between_bank_accounts_7291`, including from the outgoing checking account. Do not say that the external deposit has posted without a supporting posted-deposit result.

Use an internal transfer only where the customer explicitly authorizes an immediate transfer from an identified source account and all source, destination, amount, available-balance, and transfer controls have passed.

## Fresh outgoing-checking closure review

Immediately before closing the outgoing checking account:

1. Re-call `get_all_user_accounts_by_user_id_3847`, locate the exact requested account, and reconfirm ownership, exact class, `OPEN` status, balance, and opening date.
2. Apply the class-specific closure terms. Light Blue is entry tier: it has a $15 early-closure fee only if closed within 30 days and has no notice period. If the fee applies, its own balance must cover it; otherwise, its balance must be exactly $0.
3. Verify that there are no pending account transactions through an available current transaction or pending-activity workflow. If no supported lookup exists, retain a contemporaneous customer confirmation together with the fresh account review; never fabricate a transaction lookup.
4. Unlock and call `get_debit_cards_by_account_id_7823` for the exact outgoing checking account. An empty result completes the card review.
5. For each linked card in `ACTIVE` or `PENDING` status, verify ownership, at least 14 days of card age, no pending card transactions, and no pending refunds. When every card prerequisite passes, unlock and call `close_debit_card_4721` with reason `account_closing`. Do not close checking while a qualifying linked card remains unresolved.
6. Only after every closure prerequisite passes, unlock and call `close_bank_account_7392` using the freshly verified outgoing account ID.

If a fee, balance, status, notice, card, pending-activity, or tool-result blocker remains, state that the account remains open and explain the specific unresolved condition.

## Completion response

After results are available, state only actual outcomes: the exact official account classes opened, the applicable savings-rate components and material Gold balance/fee terms, the outgoing-account closure result, and funding status.

When the customer selected external funding, explicitly say that no internal transfer was made and: **The new savings account must be funded within 30 days or it will be closed.** Do not state that an external deposit has arrived unless a tool result confirms it.

## Pair-ranking helper

Run `python scripts/rank_account_pairs.py < input.json` when ranking documented candidates is useful. The helper reads one JSON object from standard input and writes one JSON object to standard output. It has no banking, network, or filesystem side effects.

Input schema:

- `deposit`: nonnegative proposed savings deposit.
- `candidates`: array of objects containing `checking_account_class`, `savings_account_class`, `opening_minimum`, `ongoing_minimum`, `base_apy`, and `checking_boost`.
- Optional `tiers`: array of objects with `minimum_balance` and `apy`; the highest qualifying tier is used.
- Optional `apy_requires_ongoing_minimum`: boolean. Set true only if documented terms make the selected APY unavailable below the ongoing minimum.
- Optional `credit_card_bonuses`: numeric array; only the highest value is used.
- Optional `direct_deposit_bonus` and boolean `direct_deposit_confirmed`; the bonus is used only when confirmed.

The output identifies plans openable at the deposit, rates, components, and ongoing-minimum flags. Validate every result against live relationship facts, actual terms, and banking controls before making a banking call.
