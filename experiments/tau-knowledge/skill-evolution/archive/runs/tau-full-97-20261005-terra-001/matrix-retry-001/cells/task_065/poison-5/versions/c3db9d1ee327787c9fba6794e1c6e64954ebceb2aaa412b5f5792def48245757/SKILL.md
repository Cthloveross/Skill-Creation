---
name: checking-replacement-and-savings-apy-executor
description: Executes an authorized personal-checking replacement, a personal-savings opening, and an evidence-based highest-achievable-APY selection. Use for verified customers who want to close a checking account, open replacement checking and savings, choose the best documented savings rate for a stated deposit, or arrange external versus internal initial funding.
---

# Checking Replacement and Savings APY Executor

Use this Skill only for an authenticated customer's requested banking changes. Product research is not a reason to transfer the customer to a human agent. When the customer delegates selection (for example, asks the bank to choose the highest achievable APY), use the available product terms to make and execute that selection after the required controls below are satisfied.

## Controls and evidence review

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

1. Use the established identity-verification record where one is current and valid. Otherwise, compare two customer-provided identity fields (email, phone, address, or date of birth) with the customer record, obtain the current time, and call `log_verification`.
2. Retrieve current accounts with `get_all_user_accounts_by_user_id_3847(user_id)`. Use the result, not customer recollection, for account IDs, ownership, account counts, status, balances, collections/negative-balance review, and checking tenure.
3. Check personal-checking eligibility: verified adult, no more than four checking accounts after opening, and no checking account closed for cause in the prior six months.
4. Check personal-savings eligibility: verified customer, fewer than five savings accounts, no collection or negative balance, and an active Rho checking relationship held at least 14 days. Keep that qualifying checking open through the savings opening. A just-opened replacement checking account does not by itself meet the 14-day requirement.
5. Use exact official `account_class` strings, including the word `Account` and any parenthetical qualifier. Do not abbreviate product names.

If a required eligibility condition fails or cannot be established from current records and supported verification, do not perform the affected action. Explain the specific blocker and the safe next step.

## Determine the highest achievable APY

Build a comparison from the current request, the supplied product terms, and customer-confirmed conditions. `scripts/select_savings_plan.py` can rank the normalized candidates, but the executor remains responsible for collecting accurate terms and eligibility facts.

For each candidate, evaluate the stated deposit against all of the following:

- savings opening minimum, ongoing minimum, and the applicable APY-tier threshold;
- whether the replacement checking can be opened and is an explicitly documented eligible pairing;
- only the highest applicable linked-checking boost, never a sum of checking boosts;
- only the highest applicable credit-card bonus, never a sum of card bonuses; and
- separately documented bonuses, such as direct-deposit bonuses, only when their actual conditions are met.

Do not count a direct-deposit bonus merely because direct deposit was offered for or will be sent to a different account. State any enrollment, balance, or product-pairing condition necessary to retain the quoted APY.

### Documented selection pattern

Where the available terms establish all of these facts—Green savings has a 4.0% base APY, accepts and can maintain the proposed deposit, and Evergreen checking supplies its documented 0.55% Green-savings boost—select **Evergreen Account** checking with **Green Account** savings. The resulting documented rate is 4.55% before any separately applicable eligible card bonus. Do not add a direct-deposit bonus unless Green savings itself documents one.

For a $6,000 savings deposit under the supplied terms, exclude products whose opening or ongoing minimum exceeds $6,000. In particular, a product requiring a $10,000 ongoing balance is not sustainable at that deposit, and a checking product requiring a $75,000 opening deposit is not an available replacement choice. Compare tiered products at the actual $6,000 tier, not their advertised upper tier.

A customer's explicit instruction to choose the highest-APY combination is delegated authorization for the resulting documented checking and savings selection; do not require a redundant product-choice question. The original request to replace checking, open savings, and close the outgoing account supplies the requested action authority. Still disclose material requirements and do not make an unauthorized funding transfer.

## Agent-tool sequence

The account tools are discoverable internal agent tools. Unlock each needed tool with `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool` using a JSON-object `arguments` value.

1. Unlock and call `get_all_user_accounts_by_user_id_3847` with the authenticated `user_id`.
2. Select the viable documented plan as described above.
3. Unlock and call `open_bank_account_4821` for the replacement checking account:
   ```json
   {"user_id":"<verified user id>","account_type":"checking","account_class":"<exact official checking class>"}
   ```
4. While the established qualifying checking account remains open, unlock and call `open_bank_account_4821` for savings:
   ```json
   {"user_id":"<verified user id>","account_type":"savings","account_class":"<exact official savings class>"}
   ```
5. Confirm successful opening results before proceeding. Meet or clearly communicate product enrollment conditions. For Green savings, paperless statements are required and the account needs at least $100 to open and $500 ongoing.
6. Complete outgoing-checking closure only after the fresh closure review below. Unlock and call `close_bank_account_7392` with the outgoing `account_id` once its prerequisites are satisfied.

Never claim an opening or closure succeeded until its tool result is successful. Do not escalate merely because account changes are irreversible when the customer has already authorized the requested, eligible changes.

## Fresh outgoing-account closure review

Perform this review immediately before closure rather than relying on an old statement.

1. Re-read the current account record. The account must be owned by the verified customer, `OPEN`, and have the required closure balance.
2. Determine the account tier and early-closure window from its retrieved opening date. For Light Blue, Light Green, and Green Fee-Free checking, a $15 early-closure fee applies only within 30 days; no notice period applies. Outside that window, balance must be exactly $0. Within it, balance must be at least $15 because the fee is deducted from that account and cannot be paid another way.
3. Verify no pending account transaction using an available supported pending-activity lookup when one exists. Do not invent a tool or tool parameter. If no dedicated lookup is supplied, obtain a contemporaneous customer confirmation of no pending transactions alongside the fresh account record and document that this is the available closure-control evidence.
4. Unlock and call `get_debit_cards_by_account_id_7823(account_id)`. If it returns no cards, record that result and continue. If cards exist, each linked card must be closed before checking closure: verify owner, allowed status, pending transactions/refunds, card age, and the closure reason; close eligible cards using the documented debit-card tool. A card that cannot be closed blocks checking closure.
5. Call `close_bank_account_7392` only after all applicable conditions pass.

## Funding and customer completion message

After savings opens, ask for no internal transfer when the customer selected external funding. In particular, do not debit the outgoing checking account or substitute an internal transfer for the customer's stated external $6,000 deposit.

For external or deferred funding, clearly say all of the following:

- the deposit remains **pending** and has not been moved by the bank;
- the customer will fund the savings account externally for the stated amount; and
- the new savings account must be funded within **30 days** or it will be closed.

Confirm the exact opened checking and savings classes, the selected APY and conditions, the outgoing-account closure result, and the external-funding status. If any tool action fails, describe only the successful changes and the failed action's next safe resolution.

## Plan-ranking helper

Run the deterministic helper with current, normalized product facts:

```text
python scripts/select_savings_plan.py < input.json
```

It reads one JSON object from stdin and emits one JSON object on stdout. It performs no banking actions.

Input fields:

- `deposit`: proposed savings deposit as a nonnegative number.
- `direct_deposit_confirmed`: boolean.
- `savings_products`: objects with `account_class`, `base_apy`, `opening_minimum`, `ongoing_minimum`, optional `tiers` (`minimum_balance`, `apy`), optional `direct_deposit_bonus`, optional `direct_deposit_required_for_bonus`, and optional string `requirements`.
- `checking_options`: viable checking objects with `account_class`, `available` boolean, and `boosts`, a map from exact savings class to APY boost.
- `credit_card_bonuses`: optional map from exact savings class to a map of eligible card label to bonus. Supply only cards actually held in good standing and applicable to that savings class.

Validate the chosen result by checking that its displayed total is the sum of the displayed base rate, one checking boost, one card bonus, and any earned direct-deposit bonus; that its checking class is an available documented pairing; and that the savings product meets the deposit constraints.
