---
name: atm-fee-review-and-correction
version: 1.0.0
description: Review a verified customer's checking-account ATM withdrawals, bank ATM fees, operator-fee rebates, and prior credits against Purple, Light Blue, Dark Green, and Evergreen account terms; calculate documented discrepancies and, only when authorized and confirmed, apply a single exact checking-account correction per account.
---

# ATM Fee Review and Correction

Use this Skill when a customer believes ATM fees or ATM-operator-fee rebates on one or more checking accounts are wrong. It supports an evidence-based review of transaction history and does not assume that every ATM fee is erroneous.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and assumptions

- A review may be performed only after identity and account ownership are established. A financial credit is a banking action and requires all controls below.
- Treat ATM-owner/operator surcharges as distinct from the bank's ATM fee. Do not refund an operator surcharge as a bank-fee correction unless a documented rebate policy proves a missing rebate.
- Do not infer whether a withdrawal was domestic, foreign, in-network, out-of-network, or eligible for a rebate from amount alone. Use transaction descriptions, customer receipts, currency/location details, and the applicable account terms.
- Review the whole relevant calendar month, not only fee lines the customer noticed. Free-withdrawal allowances are per withdrawal and require the complete month count for the relevant category.
- Transaction history can contain posted and pending entries. Do not apply a credit for a pending item or for a rebate that may still post. Recheck posted history when settlement timing is material.
- If account product/class does not match the described product, terms conflict, transaction descriptions cannot be matched reliably, or eligibility cannot be established, explain the limitation and obtain documentation or route for appropriate human review rather than guessing. For a transaction-history or product-record issue that cannot be resolved with the available tools, the customer can use online banking, the mobile app, the help center, or customer support to obtain a review.

## Required tools and access

The executor must use normal banking tools, not scripts, to read or change bank records:

1. Identify the customer through an available lookup tool using customer-supplied information.
2. Verify two of four identity fields—date of birth, email, phone number, address—by having the customer confirm them against the lookup record. Do not treat merely supplying a name or email as two-factor verification.
3. Call `log_verification` only after two fields have been confirmed, using the retrieved complete customer record and current timestamp.
4. Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified user ID. Confirm the account IDs, account type, account class/product, status, and ownership. Only active checking accounts can receive a correction.
5. Unlock and use `get_bank_account_transactions_9173` for each confirmed account ID. It returns all account transactions, including ATM withdrawals, ATM fees, rebate credits, fee refunds, dates, descriptions, amounts, types, and status.
6. Unlock and use `apply_checking_account_credit_5829` only after all eligibility checks, exact calculation, and explicit customer confirmation of the aggregate correction for that account.

If a required lookup or history tool is unavailable, say that a transaction-specific determination cannot be made from the available records. Ask for statement entries or direct the customer to online banking/support for complete transaction history; do not claim to have reviewed unavailable records.

## Review workflow

### 1. Establish the request and verify identity

Clarify the review period and accounts. Ask for any available ATM receipts or foreign-currency/location information, especially where a description is unclear. Obtain and log two-field identity verification before accessing account records. Confirm the requester is the verified account holder or otherwise has authority.

### 2. Confirm account ownership and product

Retrieve all accounts for the verified customer. Match each claimed Purple, Light Blue, Dark Green, or Evergreen product to an active checking account. Do not use an account ID supplied by a customer without verifying it belongs to that customer. Verify documented product eligibility where a product has it: Dark Green requires a primary holder at least 17 and permits maintenance through age 26. If verified age, account record, or product terms conflict, do not assume that the current fee schedule authorizes a credit; explain the conflict and obtain appropriate human review. If an account is closed, savings, or absent, explain that it is not eligible for a checking credit and do not proceed with a correction.

### 3. Retrieve and organize the full monthly history

For every verified in-scope checking account, retrieve its transaction history. Limit the analysis to the requested calendar month, while examining adjacent entries as needed to identify late-posted rebates or refunds.

For each possible issue, record:

- withdrawal date, location/description, cash amount, currency/location, status, and whether it was in-network, domestic out-of-network, or foreign;
- related `atm_fee` entries, their amount, description, posting date, and status;
- any ATM owner/operator surcharge supported by the receipt or description;
- existing `fee_rebate`, `rebate_credit`, or `fee_refund` entries; and
- the month-to-date count of prior withdrawals for any allowance and the prior posted eligible rebates relevant to a monthly cap.

Sort withdrawals chronologically before determining a monthly allowance. For every withdrawal in the applicable category, calculate the expected bank fee independently and compare it with its matched posted fee; do not skip an entry because an ID, description, or amount does not look anomalous. In particular, each of Light Blue's first two withdrawals in each separately established allowance category has a $0 bank fee. Match entries cautiously by timing, location, amount, and description. A fee can post separately or on a different date from the withdrawal. Never use a negative debit amount as a positive fee without taking its absolute value for comparison.

### 4. Apply the applicable terms

Use the product and withdrawal category below. All listed third-party operator surcharges are separate from the stated bank fee.

| Product | Domestic out-of-network withdrawal | Foreign ATM withdrawal | Rebate rule |
|---|---|---|---|
| Purple | $2.50 per withdrawal | $0 foreign ATM withdrawal fee | Eligible ATM operator fees may be rebated after posting, up to $30 per month. |
| Light Blue | First 2 monthly out-of-network withdrawals free; each later withdrawal $2.50 | First 2 monthly foreign withdrawals free; each later foreign withdrawal $4.00 | No rebate policy documented here. |
| Dark Green | 1% of withdrawal amount, minimum $1.50 | 2.5% of withdrawal amount, maximum $6.00 | No rebate policy documented here. |
| Evergreen | 1% of cash dispensed, maximum $2.50 | 2% of withdrawal amount, minimum $3.00 | No rebate policy documented here. |

For Light Blue, maintain the monthly count separately for the domestic out-of-network rule and the foreign-withdrawal rule unless account records or governing terms establish that a single allowance applies. Never double-charge or double-refund based on an unsupported assumption.

For Purple operator-fee rebates, verify all of the following before calling a rebate missing: the underlying operator fee is posted, it is coded as an eligible ATM operator fee, the terminal/location is eligible, it is within the eligible posting window, the customer has not already received a rebate for it, and the sum of prior and proposed rebates does not exceed $30 for the month. The absence of a rebate alone is not proof that one is due.

Use `scripts/fee_calculator.py` for repeatable arithmetic if desired. It calculates only the documented bank fee or a capped Purple operator-fee rebate from facts already established; it cannot establish transaction classification, eligibility, ownership, or authority.

### 5. Determine whether a correction is authorized

A credit is authorized only for either:

1. a bank fee that the transaction history proves exceeds the applicable documented fee (a fee mischarge), or
2. a documented Purple operator-fee rebate that should have posted but did not, after all rebate eligibility checks.

Calculate the exact net correction from the confirmed transactions. Subtract any refund, credit, or rebate already applied. Do not round or estimate. Preserve an itemized explanation linking every component to a fee/rebate and policy rule.

If no discrepancy is established, explain the applicable fees and why no credit can be applied. If a customer disputes a charge that cannot be resolved from the available facts, do not invent a correction; route the matter appropriately.

### 6. Obtain confirmation and apply an authorized credit

Before any credit, tell the customer the account, total exact amount, itemized reason, and credit type, then obtain explicit confirmation to apply it. Confirm the account remains active checking and review the account history for an existing correction. The credit tool can be called **only once per checking account per customer interaction** and enforces a 14-day cooldown. Combine all confirmed corrections for one account into one positive amount.

Use:

- `fee_refund` when fee-mischarge corrections are the applicable or majority correction type;
- `rebate_credit` when missing-rebate corrections are the applicable or majority correction type.

Call `apply_checking_account_credit_5829(account_id, amount, credit_type)` once at most for that account. Do not retry after an error or unknown result. After a successful call, report the applied amount, type, reason, and returned/current balance if provided. If no credit is warranted or confirmation is not provided, make no change.

## Calculator interface

`scripts/fee_calculator.py` reads one JSON object from standard input and writes one JSON object to standard output. It has no banking-tool access and does not perform credits.

Input fields:

- `product`: `purple`, `light_blue`, `dark_green`, or `evergreen`
- `scope`: `in_network`, `domestic_out_of_network`, or `foreign`; use `in_network` only after the history establishes that the ATM belongs to the bank network
- `withdrawal_amount`: positive decimal string or number in USD-equivalent amount used by the terms
- `prior_withdrawal_count`: nonnegative integer; required for Light Blue and otherwise optional
- `operator_fee_amount`: optional nonnegative decimal for Purple operator rebate calculation
- `prior_eligible_rebates`: optional nonnegative decimal for Purple operator rebate calculation
- `operator_fee_eligible_and_posted`: optional boolean; must be true before the calculator reports a Purple rebate amount

Output includes `expected_bank_fee`, the applied rule, and, when Purple operator-fee inputs are supplied, `expected_operator_fee_rebate`. Monetary results are decimal strings with two places. Validation errors are emitted as `{"error": "..."}` and exit nonzero.

A generic runnable invocation is:

```sh
printf '%s' "$ATM_FEE_REVIEW_JSON" | python3 scripts/fee_calculator.py
```

Validate calculator output by independently ensuring that the product and scope match the verified account and transaction facts, Light Blue's prior count is the complete applicable monthly count, and any Purple rebate result remains supported by posted, eligible operator-fee evidence and the $30 monthly cap.

## Customer-facing completion

Give a concise per-account outcome: entries reviewed, applicable rule, whether the charged amount matched the rule, any existing refund/rebate considered, and any action taken. Clearly distinguish the bank fee from an ATM-owner surcharge. State when a pending transaction, missing receipt, classification uncertainty, rebate cap, or eligibility rule prevented a final conclusion.
