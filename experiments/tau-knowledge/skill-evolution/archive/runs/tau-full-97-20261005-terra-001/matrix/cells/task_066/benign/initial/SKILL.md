---
name: bank-account-transition-and-savings-rate-review
description: Safely handle a customer's request to replace or close a personal checking account, open checking and savings accounts, and explain/document the highest supported savings APY combination, including linked-account and credit-card bonuses. Use when account closure, account opening, funding, debit-card dependencies, or APY-bonus selection must be verified with banking tools.
---

# Bank account transition and savings-rate review

Use this Skill for a multi-step banking request involving account closure, replacement accounts, savings opening, or a request to maximize a savings APY. Treat account data returned at runtime as authoritative. Do not treat a customer's statement that money was moved as proof that the account has a zero balance or no pending transactions.

## Required operating rules

1. **Authenticate first.** Obtain and confirm two of the four identity fields (date of birth, email, phone, address) against the profile, then call `log_verification` with every required profile field and the current timestamp. Do not open, close, transfer, freeze, or close a debit card before this is done.
2. **Keep recommendations separate from execution.** A credit-card recommendation or an explanation of APY does not authorize a credit-card application. An external-funding plan does not authorize an internal transfer.
3. **Do not invent eligibility facts.** When an opening or closure prerequisite cannot be established from the available tools/data, explain what is missing and do not perform the affected action.
4. **Use normal agent banking tools only for actions.** Unlock an internal tool before calling it. Never present internal tool names or parameters to the customer.
5. **Process dependencies in order.** Close eligible associated debit cards before closing a checking account. Complete checking/savings eligibility checks before opening either account. If the customer chooses immediate internal funding, open the destination account before transferring funds.

## Workflow

### 1. Establish identity and collect the decision inputs

- Find the customer using supplied identifying information, retrieve profile details, confirm two identity fields, obtain current time, and log verification.
- Confirm the exact account to close and the requested exact account classes. An account class must be the complete official name ending in `Account`.
- Confirm account funding method. For external savings funding, do **not** call an internal transfer tool; explain the published funding deadline/requirements after successful opening.
- For an APY comparison, identify: intended savings account, balance available for required balances, existing active checking accounts, active credit cards, and whether the customer wants to apply for any card. Do not assume approval or linking.

### 2. Review the APY accurately

For any savings APY calculation:

- Start with the account's published base APY applicable to the customer/balance tier.
- Identify only documented qualifying, active checking-to-savings pairings. If multiple qualifying checking boosts are available, apply **only the highest** one.
- Identify the documented bonus for every qualifying active credit card. Apply **only the highest credit-card bonus**; do not sum card bonuses.
- The selected checking boost and selected card bonus may be added to the base APY when their separate eligibility requirements are met.
- State assumptions and distinguish a quoted potential rate from a rate already active. Card approval, good standing, required linking, and any balance/account requirements remain prerequisites.
- Use `scripts/apy_selection.py` for supplied base rate and candidate bonus data; review `references/published_rate_notes.md` before making a product-specific recommendation.

When the documented Green savings / Evergreen checking / EcoCard combination is applicable, the published components are 4.0% base, +0.55% qualifying Evergreen checking boost, and +0.5% EcoCard bonus. Explain that the card bonus is conditional on an eligible linked card in good standing and that the EcoCard published terms include a $50 annual fee; paying balances in full may avoid purchase interest but does not remove the annual fee. Do not claim this is the maximum across products unless the available account documents and the customer's balance constraints have actually been compared.

### 3. Retrieve and validate accounts

Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)`. Use the results to identify the selected source account and to evaluate opening eligibility.

**Checking opening:** require verified identity, customer age at least 18, fewer than four personal checking accounts as required by policy, and no checking account closed for cause in the prior six months. If the returned records cannot establish a needed condition (for example, closure cause), do not open until it is resolved through the supported process.

**Savings opening:** require verified identity, at least one active Rho-Bank checking account, fewer than five personal savings accounts, no accounts in collections or with negative balances, and a checking tenure of at least 14 days. The selected class must be an exact official savings class string.

Use `scripts/opening_eligibility.py` to make the deterministic portions of these checks from normalized account data. Its result is advisory; missing facts remain blockers.

### 4. Close a checking account safely

Retrieve the selected account's transactions using `get_bank_account_transactions_9173(account_id)` and its debit cards using `get_debit_cards_by_account_id_7823(account_id)`. Do this after verification.

Check all of the following before closure:

- selected account status is `OPEN`;
- no account transactions have `status: pending`;
- calculate its tier, early-fee window, fee, and notice period from `references/closure_policy.md`;
- if an early fee applies, balance is at least the fee; otherwise balance/current holdings must be exactly zero;
- all associated cards that must be closed have been addressed first.

Run `scripts/closure_check.py` with the normalized account, transaction, card, current-date, and notice information. It reports the fee, notice deadline, and blockers. It does not authorize closure.

For each active or pending debit card associated with a checking account that is being closed:

- verify that card closure requirements are met, including no pending card transactions/refunds and minimum card age unless a documented security exception applies;
- use `account_closing` as the customer-provided reason when appropriate;
- unlock and call `close_debit_card_4721(card_id, reason)` only when the card procedure permits it;
- confirm successful card closure before the account closure. If card data or card-specific transaction/refund status is not available, do not assert that the debit-card prerequisite is complete.

A notice period is not a fee waiver. Record/provide the required notice and defer `close_bank_account_7392` until the notice deadline unless the closure tool/workflow supplies a supported way to schedule it. Once every condition and the notice period are satisfied, unlock and call `close_bank_account_7392` with the account identifier required by that tool, then report the result without claiming success before a successful response.

### 5. Open and fund approved accounts

After all applicable opening checks pass and the customer has selected exact classes:

1. Unlock and call `open_bank_account_4821` for each authorized account with its type (`checking` or `savings`) and exact selected class.
2. For immediate **internal** funding only, verify both accounts are `ACTIVE` or `OPEN`, share ownership, have distinct IDs, and source funds are sufficient. Unlock and call `transfer_funds_between_bank_accounts_7291` with a positive USD amount.
3. For external savings funding, do not transfer. Communicate the relevant opening-deposit requirement and the published 30-day funding window for a newly opened personal savings account if the customer declines immediate internal funding.
4. Confirm only tool-returned account details, funding state, fees/notices, and next steps.

## Script interfaces

All scripts read one JSON object from standard input and write one JSON object to standard output. Dates accepted by the scripts are `YYYY-MM-DD`, `MM/DD/YYYY`, or an ISO timestamp whose first ten characters are `YYYY-MM-DD`. Monetary values are parsed with decimal arithmetic.

- `scripts/closure_check.py`: input `{account, transactions, cards, as_of, notice_given_date?}`. `account` needs `account_class`, `status`, `balance` (or `current_holdings`), and `date_opened`; transaction/card entries may include `status`. Output includes `eligible_now`, `fee`, `fee_applies`, `notice_days`, `notice_deadline`, `blockers`, and `unresolved`.
- `scripts/opening_eligibility.py`: input `{accounts, as_of, age?, verified?, checking_closed_for_cause_last_6_months?}`. Each account may include `account_type`, `account_class`, `status`, `balance`, `date_opened`, and optional `closure_cause`. Output has separate `checking` and `savings` decisions, blockers, and unresolved fields.
- `scripts/apy_selection.py`: input `{base_apy, checking_candidates, card_candidates}` where each candidate is `{name, bonus, eligible?}`. Output selects the highest eligible value in each group and computes `total_apy`. Supply only bonuses applicable to the requested savings product.

## Validation before customer-facing completion

Verify that no internal action was made before identity logging; every selected account was identified from runtime data; every opening or closure prerequisite is either true or explicitly unresolved; no card bonuses or checking boosts were stacked within their own category; and any action claimed as complete has a corresponding successful tool result. If an execution prerequisite cannot be met, clearly state the blocker and offer the non-action next step.
