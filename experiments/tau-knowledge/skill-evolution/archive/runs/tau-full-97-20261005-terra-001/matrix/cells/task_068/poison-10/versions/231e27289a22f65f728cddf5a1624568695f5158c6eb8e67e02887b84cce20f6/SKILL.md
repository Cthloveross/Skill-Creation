---
name: personal-banking-product-transition
version: 1.0.0
description: Handle a verified customer's request to close a personal checking account, open replacement checking and savings accounts, evaluate documented APY combinations, and arrange savings funding. Use when a customer wants product recommendations or banking account opening/closure actions.
---

# Personal Banking Product Transition

Use this Skill for a combined checking replacement, savings opening, and APY recommendation request. Recommendations are informational; account openings, transfers, and closures are banking actions and require all applicable checks and customer confirmation before execution.

## Safety and verification gates

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

1. Resolve the customer profile using an approved identifier.
2. Ask the customer to confirm **two** profile fields among date of birth, email, phone number, and address. Compare them against the retrieved record.
3. After two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete retrieved profile and timestamp.
4. Retrieve accounts using `get_all_user_accounts_by_user_id_3847` before any account action. Do not treat the customer's recollection of balance, status, pending activity, or opening date as verification.
5. Do not open, close, or transfer until the needed eligibility and ownership checks have a confirmed result. State what is missing when a check cannot be completed.

## Required tool workflow

Unlock only the tools needed for the request:

- `get_all_user_accounts_by_user_id_3847` — account IDs, types, classes, statuses, balances, and opening dates.
- `get_bank_account_transactions_9173` — inspect the account to be closed for pending transactions.
- `open_bank_account_4821` — open a selected checking or savings account after all eligibility checks.
- `transfer_funds_between_bank_accounts_7291` — only for a customer-authorized internal funding transfer.
- `close_bank_account_7392` — close an eligible account after required checks and any notice requirement.

Use `unlock_discoverable_agent_tool` before calling an unlocked tool through `call_discoverable_agent_tool`. Agent tools are executed by the agent; never ask the customer to supply tool parameters or call an internal tool.

## 1. Determine the recommendation

Collect the customer's hard requirements separately from preferences:

- savings amount available to fund and whether it is internal or external;
- required direct-deposit timing;
- whether travel insurance must be provided by the card itself or another product is acceptable;
- willingness and ability to meet each checking, savings, and credit-card eligibility requirement;
- desired account class and consent to open each product.

Use only documented rates, eligibility conditions, and benefits. Never infer that an undocumented card benefit exists. A combination qualifies only if every stated requirement is satisfied, including product minimum balances, linked-product pairing, and same-profile status.

For each candidate, calculate:

`effective APY = savings base APY + highest applicable linked-checking boost + highest applicable credit-card bonus + other explicitly documented additive bonuses`

Do not add multiple checking boosts together. Do not add multiple credit-card APY bonuses together. A checking boost and a card bonus may both be additive when the documentation says they apply to the same savings product. Use `scripts/rank_apy_options.py` to perform this calculation from runtime-supplied candidate data.

### Documented selection logic for the supplied product material

For a customer with $25,000 who requires early direct deposit and documented card travel insurance, the documented qualifying high-rate path is:

- **Gold Years Account** checking: direct deposit up to two days early and a documented +0.5% boost for Gold Plus savings.
- **Gold Plus Account** savings: 6.0% base APY and a $25,000 ongoing minimum balance.
- **Silver Rewards Card**: documented travel-insurance coverage up to $15,000 per trip, subject to policy terms, and a +0.1% Gold Plus APY bonus.

When all products are approved, active, held under the same profile, and linked as required, this produces **6.60% APY** on the Gold Plus savings balance (6.0% + 0.5% + 0.1%). Explain that insurance remains subject to card policy terms, exclusions, charging requirements, and documentation requirements. Do not claim that another card has travel insurance unless its coverage is documented.

The available account-opening tools do not include a credit-card application action. Give the card's documented application path and eligibility requirements, or direct the customer to the normal application experience; do not fabricate a credit-card opening action.

## 2. Check checking-account opening eligibility

Before opening personal checking, confirm all of the following:

- identity is verified;
- customer is at least 18;
- customer will not exceed four personal checking accounts;
- customer has no checking account closed for cause in the last six months;
- desired `account_class` is the full official name ending in `Account`.

If eligible and the customer explicitly confirms the selected checking product, call:

`open_bank_account_4821(user_id, "checking", account_class)`

Record the returned account ID and status. If eligibility information is unavailable, do not call the opening tool; explain the blocking item.

## 3. Check savings-account opening eligibility

Before opening personal savings, confirm all of the following:

- identity is verified;
- at least one active Rho-Bank checking account exists and has been open at least 14 days;
- customer has fewer than five personal savings accounts;
- no customer account is in collections or has a negative balance;
- selected `account_class` is the exact full official name ending in `Account`.

Run `scripts/evaluate_account_state.py` on the retrieved account data to make the count, tenure, balance, and status checks reproducible. The script reports unknown evidence rather than treating it as a pass. Resolve every unknown before opening.

If eligible and the customer explicitly confirms the savings selection, call:

`open_bank_account_4821(user_id, "savings", account_class)`

Use the returned savings account ID for later funding. Do not promise a rate or bonus until all qualifying products are active and linked under the same profile.

## 4. Funding the new savings account

Ask whether the customer authorizes an immediate internal opening-deposit transfer. For an internal transfer, verify the source checking account is owned by the customer, source and destination are distinct, both are ACTIVE or OPEN, the amount is positive USD, and available funds cover it. Then call:

`transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`

Confirm the transfer posted and was not duplicated.

If funds are outside Rho-Bank or the customer declines an internal transfer, do not call the transfer tool. Explain that the customer must fund the account by external deposit or later internal transfer within 30 days or the account will be closed. Also communicate the selected product's documented opening-deposit and ongoing-balance requirements.

## 5. Close the old checking account

Do not close the old account merely because the customer says it is empty. Retrieve its account record and transaction history. Confirm:

- the account belongs to the verified customer;
- status is OPEN;
- no transaction is pending;
- exact opening date and current holdings are known;
- applicable early-closure fee and notice period have been determined;
- account balance is $0 if no early fee applies, or is at least the applicable fee if the fee applies.

For Light Blue Account, the early-closure fee is $15 when closed within 30 days and the notice period is zero days. If the fee applies, it is deducted from the account balance; there is no alternate payment method. If the balance cannot satisfy the applicable condition, do not close it.

After all checks and a final customer confirmation to close that specific account, call `close_bank_account_7392` with its documented required arguments. Confirm the result and disclose any deducted fee. If the account is no longer needed to satisfy savings-opening eligibility, it may be closed only after the savings opening has succeeded.

## Completion response

Summarize only completed actions and verified facts: account classes and IDs returned by tools, funding status or 30-day deadline, closure status and fee if any, conditions needed for APY bonuses, and any remaining credit-card application or linking step. Clearly distinguish recommendations, pending customer actions, and completed bank actions.

## Script interfaces

### `scripts/evaluate_account_state.py`

Reads JSON from stdin and writes JSON to stdout.

Input:

```json
{
  "accounts": [{"account_id": "...", "account_type": "checking", "account_class": "...", "status": "OPEN", "balance": 0, "date_opened": "YYYY-MM-DD", "collections": false}],
  "as_of_date": "YYYY-MM-DD",
  "identity_verified": true
}
```

Output contains `savings_opening_eligible`, `checks`, `blockers`, and `unknowns`. `collections` may be omitted, in which case the script returns an unknown and does not declare eligibility.

### `scripts/rank_apy_options.py`

Reads JSON from stdin and writes JSON to stdout. Supply only options supported by current documentation. It selects the highest single checking boost and highest single card bonus for each option, verifies hard requirements supplied in the input, and ranks qualifying options by effective APY.
