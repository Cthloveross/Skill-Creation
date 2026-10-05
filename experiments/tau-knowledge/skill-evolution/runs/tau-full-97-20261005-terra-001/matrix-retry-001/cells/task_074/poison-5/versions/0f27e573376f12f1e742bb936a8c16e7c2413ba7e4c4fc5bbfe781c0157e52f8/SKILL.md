---
name: review-atm-fees-and-correct-eligible-checking-credits
description: Review a verified customer's checking-account ATM activity for documented fee mischarges or missing ATM rebates, calculate product-specific expectations, explain findings, and—only when the evidence supports an exact eligible correction—apply one consolidated checking-account credit per account.
---

# Review ATM Fees and Eligible Credits

Use this Skill when a customer asks to review ATM-related charges, ATM rebates, or possible fee errors on one or more checking accounts. It supports a transaction-history review and an authorized checking-account credit only for documented fee mischarges or missing rebates.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this workflow, identity, authority, account ownership, applicable account product, ATM type/network/location, posting status, monthly usage, rebate eligibility/caps, transaction matching, and any required customer confirmation must be established before an account credit. Available balance, recipient, and card details are not inputs to a fee credit unless the particular correction or related transaction makes them relevant; record them as not applicable rather than assuming them.

## Required information and supported tools

The executor needs access to these discoverable agent tools:

- `get_all_user_accounts_by_user_id_3847(user_id)`
- `get_bank_account_transactions_9173(account_id)`
- `apply_checking_account_credit_5829(account_id, amount, credit_type)`

Unlock each tool before calling it. The accounts tool returns account identity, type/class, status, balance, and opening date. The transactions tool returns posted and pending transaction records in reverse chronological order. The credit tool is an action tool and must not be called until all credit prerequisites below are satisfied.

## Procedure

### 1. Verify the customer before retrieving account data

1. Identify the customer with a supplied name or email, using the appropriate customer lookup tool.
2. Obtain and compare **two of the four** verification fields: date of birth, email, phone number, and address. A name alone is not one of the two fields.
3. Obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete returned customer record and timestamp.
4. Confirm the customer is requesting review of their own accounts. If identity, authority, or account ownership cannot be established, do not access account history or apply a credit.

A previously observed lookup is not a substitute for a completed two-field verification and verification log in the current interaction.

### 2. Retrieve and scope the accounts

1. Call `get_all_user_accounts_by_user_id_3847` for the verified `user_id`.
2. Retain only accounts that are both checking accounts and relevant to the customer's request. Record account ID, product/account class, status, balance, and opening date.
3. Confirm each candidate account is open and belongs to the verified customer. Do not apply a credit to savings, a non-checking account, a closed account, or an account whose product cannot be identified.
4. For each in-scope checking account, call `get_bank_account_transactions_9173(account_id)`.
5. Limit the review to the requested statement month using transaction dates, while noting that a fee or rebate can post later than its associated withdrawal. Keep both posted and pending records visible, but only treat posted items as completed charges or credits unless a documented policy says otherwise.

Do not use credit-card history as a substitute for checking-account ATM history.

### 3. Classify the evidence; do not guess

For every possible ATM event, preserve the transaction ID, account ID, date, description, amount, type, and status. Match a withdrawal to its separate bank ATM-fee line, ATM-operator surcharge, and rebate only when the descriptions, dates, amounts, or other transaction evidence support the match.

Determine and document:

- whether the ATM was Rho/in-network or out-of-network;
- whether the withdrawal was domestic or foreign;
- cash amount withdrawn (not the total debited including fees);
- whether a fee was a Rho bank fee or an ATM-operator surcharge;
- whether the transaction and associated fee have posted; and
- chronological qualifying withdrawals and rebates already posted during the relevant calendar month.

Descriptions or amounts that do not establish these facts are insufficient. Request a receipt/statement detail or explain the limitation; do not assign a location, network, fee source, membership status, or rebate eligibility by inference alone.

### 4. Apply the documented product rules

Calculate only the Rho bank fee for a qualifying out-of-network withdrawal. ATM-owner surcharges are separate from bank fees.

| Product | Domestic out-of-network Rho fee | Foreign ATM Rho fee / benefit |
|---|---|---|
| Purple | $2.50 per withdrawal | $0 foreign ATM withdrawal fee. Eligible ATM-operator fees are rebated after posting, up to $30 per month. |
| Light Blue | First 2 qualifying withdrawals per month free; then $2.50 each | First 2 foreign withdrawals per month free; then $4 each. |
| Dark Green | 1% of cash withdrawn, minimum $1.50 | 2.5% of cash withdrawn, maximum $6.00. |
| Evergreen | 1% of cash withdrawn, maximum $2.50 | 2% of cash withdrawn, minimum $3.00. |

For Light Blue, count domestic and foreign free allowances separately and in chronological order. For Purple rebate review, verify eligible operator-fee coding, posted status, and total rebates already credited in that month before applying the $30 cap. A missing Purple rebate is not established merely because an ATM fee exists.

If the customer may have had Rho Bank Plus, search the retrieved checking histories for its $4.99 monthly membership charge and any reimbursement entries. Its documented benefit is reimbursement of eligible out-of-network ATM **operator** fees up to $32 monthly and excludes currency conversion and certain other third-party charges. A historical $4.99 charge can support further review, but if it does not establish active coverage for the relevant period or the relevant reimbursement terms are unclear, state that membership eligibility is unresolved. Do not assume that Plus reimbursement stacks with Purple's $30 benefit or combine the two possible entitlements without documentation establishing the relationship.

Use `scripts/review_atm_fees.py` after manual classification to make the repeated fee arithmetic and usage ordering auditable. The script never guesses missing classifications and never authorizes a banking action.

### 5. Decide whether a credit is authorized

A checking credit is permitted only when all of the following are true:

1. The verified customer owns an open checking account.
2. Transaction history and the applicable product terms document either a fee mischarge or a missing rebate.
3. The exact positive correction can be calculated; do not round, estimate, or credit unresolved candidate amounts.
4. The history has been checked for an existing matching credit/rebate and for whether a credit was already applied to that account during this interaction or is subject to the 14-day cooldown.
5. The total correction and reason have been reviewed against all applicable fees, rebates, caps, and benefits.

If evidence is incomplete, report what can be confirmed and what detail is needed. Do not use a goodwill credit or a credit for customer inconvenience.

When multiple valid corrections exist on the same checking account, consolidate them into **one** credit call for that account. Sum the exact corrections. Use `fee_refund` when fee-mischarge corrections are the majority of the consolidated corrections; use `rebate_credit` when missing rebates are the majority. If the count is tied or the reason cannot be represented accurately by the required type, do not improvise—seek an authorized resolution path before calling the tool.

Call `apply_checking_account_credit_5829` at most once per checking account in the interaction, with the checking `account_id`, a positive exact decimal amount, and either `fee_refund` or `rebate_credit`. The tool is limited to one call per account per interaction and enforces a 14-day cooldown.

### 6. Complete the customer response

For each reviewed account, clearly distinguish:

- withdrawals reviewed and posted versus pending;
- expected Rho fee, actual Rho fee, and separate ATM-operator surcharge;
- usage of free-withdrawal allowances and rebate caps;
- confirmed correct charges, confirmed mischarges, and unresolved items; and
- any credit applied, its reason, amount, and resulting balance returned by the action tool.

If no correction is justified, explain the applicable rule without claiming an unverified classification. If a transaction appears unauthorized or otherwise disputed rather than mischarged, do not file a dispute as part of this Skill; follow the separate debit-card dispute workflow.

## Calculation helper

### `scripts/review_atm_fees.py`

The script reads one JSON object from standard input and emits one JSON object on standard output. It has no external dependencies.

**Input schema**

- `period` (string): calendar month as `YYYY-MM`.
- `accounts` (array): each object has `account_id`, `product` (`Purple`, `Light Blue`, `Dark Green`, or `Evergreen`), `account_type` (`checking`), `status` (`open`), and `events`.
- Each event has `date` (`YYYY-MM-DD`), `cash_amount` (positive number/string), `network` (`out_of_network`, `in_network`, or `unknown`), `locale` (`domestic`, `foreign`, or `unknown`), and `bank_fee` (number/string or `null`). Optional trace fields such as `withdrawal_transaction_id`, `fee_transaction_id`, `operator_surcharge`, `rebate_credited`, and `notes` are preserved in output.
- `bank_fee` must be the explicitly matched Rho bank fee only; do not place an operator surcharge in this field.

**Output schema**

The output provides per-event expected/observed fee comparisons, review insufficiencies, a per-account exact `fee_refund_total` when proven, and Purple rebate-cap calculations. `credit_recommendations` are arithmetic suggestions only; the executor must still perform the policy, identity, ownership, duplicate-credit, cooldown, and tool-result checks above.

Example runtime invocation: call `run_skill_script` with `relative_path` set to `scripts/review_atm_fees.py` and `input_json` set to a normalized review payload matching the schema above. Validate that `unsupported_or_incomplete` is empty for every amount proposed for a credit, that every recommended account remains an open checking account in the live lookup, and that the totals match the selected transaction IDs before an action call.
