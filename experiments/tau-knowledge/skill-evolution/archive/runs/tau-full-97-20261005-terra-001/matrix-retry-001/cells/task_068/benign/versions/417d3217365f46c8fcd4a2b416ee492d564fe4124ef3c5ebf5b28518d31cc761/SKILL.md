---
name: bank-account-upgrade-and-savings-apy-plan
description: Safely handle a request to replace a personal checking account, open a personal savings account, fund it, and explain the highest documented APY combination subject to stated requirements such as early direct deposit and travel insurance. Use when account eligibility, closure checks, APY-bonus rules, and banking actions must be coordinated.
---

# Bank Account Upgrade and Savings APY Plan

## Scope and safety boundary

Use this Skill for Rho-Bank personal checking/savings opening, internal funding, checking closure, and related APY-product guidance. Banking actions are performed only by the execution agent through its normal banking tools. The packaged scripts only assess normalized facts and **never** perform an account, transfer, card-application, or closure action.

Do not infer authorization from an earlier, different proposal. If the customer changes a material requirement (for example, requiring documented travel insurance instead of accepting an EcoCard), obtain explicit acceptance of the revised checking/savings/card plan before performing any action.

## Facts required before any account action

1. Identify the customer and verify identity by having them confirm two of the four on-file fields: date of birth, email, phone number, or address.
2. Retrieve the on-file record and compare the customer’s confirmations. After two fields match, call `get_current_time` and then `log_verification` with all required on-file identity fields and that timestamp.
3. Unlock and call `get_all_user_accounts_by_user_id_3847` to retrieve all bank accounts. Normalize the returned facts for the assessment script.
4. For a requested checking closure, unlock and call `get_bank_account_transactions_9173` for the exact target account to determine whether pending transactions exist.
5. Do not rely on a statement that money was moved out. Verify the target account’s live balance and status.

If identity cannot be verified, account data are incomplete, or a required eligibility condition cannot be established, do not open, close, or transfer funds. Explain the missing prerequisite and request what is needed.

## APY recommendation method

Run `scripts/recommend_plan.py` after capturing the customer’s deposit amount and product requirements. The script encodes only the documented, viable combinations needed for this account-upgrade scenario and identifies whether a card benefit is conditional on approval.

For the documented plan involving a $25,000 balance and a requirement for both at least one day of early direct deposit and documented travel insurance:

- Green Account (checking) supplies direct deposit up to one day early.
- Gold Account has a 5.5% base APY and a $10,000 ongoing minimum balance.
- Green Account (checking) paired with Gold Account adds a 0.75% checking boost.
- Silver Rewards Card adds a 0.2% Gold Account card bonus and has documented travel-insurance coverage, subject to charging covered travel in full to the card and applicable policy terms.
- Thus the documented prospective rate is **6.45% APY**: 5.5% + 0.75% + 0.2%. The card bonus applies only after approval and while the required products are held.

Do not substitute EcoCard for a customer who requires documented travel insurance: its supplied materials do not document that benefit, even though it would otherwise give Gold a 0.6% card bonus. Do not add multiple checking boosts together or multiple credit-card bonuses together. Only the highest applicable boost in each category applies, although one checking boost and one card bonus can stack.

A credit-card application is not an account-opening action and no card-application agent tool is documented here. Explain the documented application process and approval conditions; do not claim to submit an application or activate a card unless a separately authorized, available tool supports it.

## Eligibility and sequencing

Run `scripts/assess_account_actions.py` with the normalized account facts before acting. Treat any `false` or `unknown` required check as a blocker.

### New personal checking

Before opening a personal checking account, confirm:

- verified customer;
- customer age is at least 18;
- fewer than four personal checking accounts;
- no checking account closed for cause in the past six months.

Confirm the exact official checking account class with the customer. Use the official documented string, such as `Green Account (checking)`. When eligible and explicitly authorized, unlock `open_bank_account_4821` and call it with the authenticated customer ID, `account_type` of `savings` only for the savings opening below; for checking, use the documented checking-opening procedure and its required account type/class parameters as supported by the unlocked tool.

### New personal savings

Before opening savings, confirm all of the following:

- identity is verified;
- at least one active Rho-Bank checking account exists;
- that checking relationship has been open for at least 14 days;
- fewer than five personal savings accounts exist;
- no account is in collections and no account has a negative balance;
- the customer confirmed the exact full official savings class ending in `Account` (for example, `Gold Account`).

Only after all checks pass and the customer authorizes the selection, unlock and call `open_bank_account_4821` with `account_type: "savings"` and the confirmed savings class. Record the newly returned savings account ID.

Do not close the customer’s only qualifying existing checking account before savings eligibility is established. A safe usual sequence is: open the replacement checking, open the eligible savings while an existing qualifying checking account remains open, handle funding, then close the old checking if its independent closure checks pass.

### Funding the savings account

After savings opens, ask whether the customer authorizes an immediate internal transfer from a specific checking account. Do not presume that the stated savings amount is present in any particular account.

If authorized, unlock `transfer_funds_between_bank_accounts_7291`. Before calling it, verify that:

- source and new destination IDs are valid and distinct;
- both accounts are `ACTIVE` or `OPEN`;
- both accounts belong to the customer;
- the amount is positive USD; and
- the source has sufficient available funds.

On a transfer error, do not silently retry or duplicate it. Revalidate the source, amount, and account statuses. If the customer declines immediate funding, tell them that the new savings account must be funded within 30 days by internal transfer or external deposit or it will be closed.

### Closing the existing checking account

Identify the exact account ID; do not close based only on an account-class label. For the requested Light Blue Account, confirm:

- status is exactly `OPEN`;
- no pending transactions exist;
- if it is fewer than 30 days old, balance is at least the $15 early-closure fee; otherwise its balance is exactly $0.

If the account is too new and lacks the fee, or if there are pending transactions, do not close it. Once all closure conditions and customer authorization are present, unlock and use `close_bank_account_7392` for that account. Confirm the result to the customer.

## Required customer communication

Before execution, summarize the selected products, the expected APY and conditions, the distinction between current and approval-contingent benefits, the proposed old-account closure, and the funding choice. Ask for a clear yes/no authorization if any of these remains unanswered.

After execution, report only returned account details and completed actions. State whether funding was completed or the 30-day funding deadline applies. For Silver Rewards Card travel insurance, avoid promising coverage for a particular trip; coverage requires charging the fare in full to the card and remains subject to policy terms, exclusions, and documentation.

## Script interfaces and validation

Both scripts read one JSON object from stdin and write one JSON object to stdout. They use only the Python standard library. The executor supplies actual runtime values rather than copying any identifiers from this document.

- `scripts/recommend_plan.py`: accepts `deposit_amount`, `requirements`, and optional `card_status`; emits `eligible_recommendations`, `recommended`, assumptions, and validation errors. Validate that the recommended APY is a number, required features are true, the balance meets the documented maintenance minimum, and any pending card is marked conditional.
- `scripts/assess_account_actions.py`: accepts normalized customer verification, age, account, closure, and proposed-funding facts; emits readiness checks, blockers, and the next safe action. Validate that no required check is `false` or `unknown` before an execution tool is called.

A runnable invocation is the executor sending one schema-valid JSON object to either listed script on stdin; the corresponding stdout JSON is the assessment record. Scripts reject malformed or missing required inputs by returning `valid_input: false` and a nonempty `errors` array.
