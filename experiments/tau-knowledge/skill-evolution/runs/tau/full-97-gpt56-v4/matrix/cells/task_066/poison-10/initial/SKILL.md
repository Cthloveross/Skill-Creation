---
name: safe-account-switch-and-savings-opening
description: Safely assist a verified bank customer who wants to close or replace a personal checking account and/or open and fund a personal savings account. Use for account-switch recommendations, eligibility checks, closures, account opening, and internal funding transfers.
---

# Safe Account Switching and Savings Opening

Use this workflow for a customer who wants to replace a checking account, close an account, open a savings account, or maximize savings yield subject to their actual balance and eligibility. It separates advice from irreversible account actions and does not assume that a request to “swap” is authorization to close or open a particular product.

## Safety and identity gate

Before accessing account-specific details or taking any banking action:

1. Identify the customer profile from the supplied name or email.
2. Ask the customer to confirm **two of the four** profile fields: date of birth, email address, phone number, and address. Do not present undisclosed values as a challenge response.
3. Compare both responses to the authenticated profile. If both match, obtain the current timestamp and call `log_verification` with the complete profile fields and timestamp.
4. Do not open, close, or transfer funds unless verification has been logged successfully. If a value does not match, stop and use the institution's normal identity-resolution process.

Before every banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

A customer name, a prior account lookup, or a statement that an account is empty is not a substitute for the two-field confirmation and logged verification.

## Gather facts without guessing

After verification, obtain current account records through a supported read-only account lookup, if one is available in the runtime. Establish the following from records, customer confirmation, and applicable product documentation:

- account IDs, ownership, type, class, status, opened date, current/available balance, and pending activity;
- number of personal checking and personal savings accounts;
- whether any checking account was closed for cause in the last six months;
- whether any account is negative or in collections;
- age and any product-specific age or balance qualification;
- each candidate product's official account class, opening-funding requirement, ongoing fee/waiver threshold, rate tier applicable to the customer's expected balance, ATM benefits, and any bonus eligibility;
- any active checking account and its tenure for a savings application; and
- the funding source, available funds, and explicit authorization if an internal transfer is requested.

Do not invent an account lookup tool, account ID, opening date, account status, fee, bonus, or product term. If a required fact cannot be established with available tools and the customer cannot provide reliable documentation, explain the blocker and do not perform the affected action.

## Give an evidence-based recommendation

When the customer asks for a better checking account or the highest savings rate:

1. Translate priorities into constraints, such as low expected checking balance, no monthly fee, ATM benefits, liquidity, and required opening deposit.
2. Compare only products whose terms are supported by the available product material. Include recurring fees that would apply at the customer's expected balance; do not advertise a waived fee as free when the waiver will not be met.
3. For savings, eliminate products the customer cannot open or maintain with the stated funds before comparing APYs. Apply the rate tier corresponding to the actual expected balance, not a higher tier requiring more funds.
4. Treat linked-checking and credit-card boosts as conditional. Check qualifying products on the same customer profile. Where several checking boosts or several card bonuses are available, only the highest boost of that category applies; do not add boosts within a category. Other documented additive bonuses may be considered only after their eligibility is confirmed.
5. State the recommendation, material tradeoffs, and the exact requirements that remain unverified. A product that is unavailable at the stated balance is not a valid “highest possible” recommendation.
6. Obtain explicit confirmation of the exact replacement checking and/or savings product. The selected `account_class` must be the exact official product name supplied by the product source; do not abbreviate, normalize, or infer it from a nickname.

If no candidate meets all stated priorities, say so plainly and offer the nearest documented alternatives. Do not close an existing account merely because the customer asked for recommendations.

## Checking account opening

A new personal checking account may be opened only after confirming all of the following:

- logged identity verification;
- customer is at least 18, unless the selected product's documented eligibility rules specifically permit another age range;
- opening the account will not put the customer above the maximum of four personal checking accounts;
- no checking account was closed for cause in the past six months;
- the selected class is an exact official class confirmed by the customer; and
- all selected-product requirements are met.

Unlock `open_bank_account_4821` if necessary, inspect its available schema, and call it only with the verified customer ID, `account_type` of `checking`, and the confirmed official `account_class`. Record the returned account ID and verify the result before treating the account as open.

## Savings account opening and funding

Before opening a personal savings account, confirm all of the following:

- logged identity verification;
- at least one active Rho-Bank checking account held for at least 14 days;
- fewer than five existing personal savings accounts;
- no accounts in collections and no negative account balances;
- the selected official savings class and product-specific opening conditions; and
- the customer's explicit decision about funding and the funding source.

Use `open_bank_account_4821` with the verified customer ID, `account_type` of `savings`, and the exact confirmed official `account_class`. Do not claim that opening itself funded the account.

If the customer authorizes an immediate internal opening-deposit transfer, unlock and use `transfer_funds_between_bank_accounts_7291` only after the new account exists and all of these are true:

- source and destination are distinct accounts owned by the customer;
- both are `ACTIVE` or `OPEN`;
- the source has sufficient available funds;
- the amount is a positive USD amount and meets the documented required deposit; and
- the customer confirmed the source, destination, and amount.

Verify that the transfer posted and do not retry an operation with an unknown outcome. If the customer declines internal funding, disclose the documented funding deadline and consequence, if one is specified for the product.

### Sequencing a switch with a savings opening

Do not accidentally invalidate savings eligibility by closing the customer's only established checking account first. If the existing checking account is the only active account that may satisfy the 14-day requirement, determine its tenure before closure. If it qualifies, savings may be completed before closing it, subject to the customer's confirmed sequence and funding plan. If the replacement checking account is the only qualifying account, wait until it has met the required tenure before opening savings.

## Checking account closure

A request to close an account requires its own final confirmation after the customer has been shown any applicable fee and consequences. Before calling the closure tool, verify:

- the exact account is owned by the verified customer;
- its status is `OPEN`;
- it has no pending transactions;
- its opening date and applicable tier-specific early-closure window;
- the applicable early-closure fee, if any; and
- its balance meets the closure rule.

For checking closure, if an early-closure fee applies, the account balance must be at least the fee because the fee is deducted from that balance and cannot be paid by another method. If no fee applies, the balance must be exactly $0. A $0 balance does not permit a closure with an applicable fee.

Unlock `close_bank_account_7392`, inspect its schema, and call it only after the above checks and final confirmation. Confirm the returned closure status and fee outcome. If the opening date is unknown, retrieve it from a supported account record; do not estimate based on the customer's memory.

## Failure handling and customer response

- **Identity or authority not established:** request the missing verification data; do not access or alter accounts further.
- **Missing selection or authorization:** provide recommendation details and ask for the exact account class and required confirmation. Do not select on the customer's behalf.
- **Eligibility failure:** identify the specific unmet requirement and do not call an opening tool.
- **Closure fee cannot be covered or pending activity exists:** do not close; explain the condition that must be resolved.
- **Savings tenure/funding failure:** preserve an existing qualifying checking account where appropriate, explain the earliest eligible point, or offer documented funding alternatives.
- **Tool error or uncertain result:** do not assume success and do not blindly repeat a state-changing request. Re-check status with supported read-only information or escalate under normal operations.

Conclude with the accounts actually opened or closed, IDs or other details only when returned by tools, funding status, applicable deadlines, and any remaining next step.

## Optional deterministic eligibility helper

`scripts/account_workflow_gate.py` checks supplied facts against the core procedural gates. It does not contact bank systems, choose products, verify identity, or execute banking actions. Its output is decision support only; the executor must still validate live records and tool results.

Run it by passing one JSON object on stdin. It emits one JSON object on stdout.

Supported `action` values and required fact groups:

- `open_checking`: `identity_verified`, `age`, `checking_count_before`, `closed_for_cause_last_6_months`, `account_class`, and `official_class_confirmed`.
- `open_savings`: `identity_verified`, `active_checking_exists`, `checking_tenure_days`, `savings_count_before`, `has_negative_balance`, `has_collections`, `account_class`, and `official_class_confirmed`.
- `close_checking`: `identity_verified`, `account_owned`, `account_status`, `has_pending_transactions`, `balance`, `fee_applicable`; include `fee_amount` when a fee applies.
- `transfer`: `identity_verified`, `customer_authorized`, `same_owner`, `source_account_id`, `destination_account_id`, `source_status`, `destination_status`, `source_available_balance`, and `amount`.

Example input:

```json
{"action":"open_savings","identity_verified":true,"active_checking_exists":true,"checking_tenure_days":21,"savings_count_before":1,"has_negative_balance":false,"has_collections":false,"account_class":"An Official Savings Account","official_class_confirmed":true}
```

An output with `allowed: false` lists blockers. An output with `allowed: true` means only that the submitted facts satisfy these core gates; it is not authorization to bypass product-specific checks, customer confirmation, or live-tool validation.
