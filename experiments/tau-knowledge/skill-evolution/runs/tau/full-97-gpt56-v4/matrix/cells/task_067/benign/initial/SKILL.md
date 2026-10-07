---
name: personal-account-transition
version: 1.0.0
description: Safely handle a customer's request to replace or close a personal checking account while opening a personal savings account, including identity verification, account eligibility, product/rate comparison, required funding, and correctly sequenced bank actions. Use when an account closure and new checking/savings opening are requested together.
---

# Personal Account Transition

Use this Skill for a customer who wants to close or replace a checking account and/or open a savings account. Treat all account actions as agent actions: never ask the customer to call an internal bank tool or expose its parameters.

## Core safety rules

1. **Verify identity before any account action.** Locate the customer record, then ask the customer to confirm any two of date of birth, email, phone number, and address. Compare both values to the record, obtain the current timestamp, and call `log_verification` only after both match. A name, user ID, or previously displayed profile data alone is not identity verification.
2. **Use live account data, not customer estimates.** Retrieve all accounts before deciding eligibility, closing an account, choosing a funding source, or calculating tenure. “Basically empty” is not a $0 balance confirmation.
3. **Never close the only qualifying checking account too early.** Savings opening requires an active checking account held at least 14 days. If the current checking account is the only qualifying account, complete the savings opening before closing it, or explain that the customer must retain/open and hold a checking account for 14 days first.
4. **Do not select or open a product without clear customer confirmation.** Recommendations are allowed; the exact, full official account class ending in `Account` must be confirmed before opening.
5. **Do not infer pending transactions, account status, balances, collections status, prior closures for cause, or consent to transfer.** Obtain each from a reliable system result or the customer when appropriate. Stop the affected action if required evidence is unavailable.
6. **Do not retry an action reported as unknown.** State that it needs review and do not duplicate it.

## Runtime tools and order

The executor can unlock these internal tools when the relevant procedure applies:

- `get_all_user_accounts_by_user_id_3847` — retrieve account ID, type, class, status, balance, and opening date.
- `open_bank_account_4821` — open a confirmed checking or savings product.
- `close_bank_account_7392` — close an eligible account.
- `transfer_funds_between_bank_accounts_7291` — transfer an authorized opening deposit between the customer's accounts.

Unlock a tool before calling it. Use `call_discoverable_agent_tool` with the exact tool name and JSON arguments. The tool result, rather than a proposed action, is the source of truth.

## End-to-end procedure

### 1. Identify and verify the customer

1. Locate the customer by the identifier they provided.
2. Ask for two identity fields without volunteering values from the profile. Match them exactly to the retrieved profile.
3. Call `get_current_time`, then `log_verification` with the complete profile fields and timestamp.
4. If either field does not match, do not act on accounts. Request a corrected field or use an appropriate escalation only when required.

### 2. Retrieve and assess accounts

After verification, retrieve all accounts. Also retrieve credit cards if a rate comparison depends on credit-card bonuses. Record each account's ID, class, type, status, balance, opening date, and any available collections/pending information.

Run the packaged assessment helper after converting the live result to its documented JSON schema:

```text
python scripts/assess_account_workflow.py < assessment-input.json
```

The helper is advisory only. It does not call bank tools and does not replace checking live facts or customer authorization. Treat `unknown` findings as blockers, not passes.

### 3. Confirm eligibility separately for each opening

**New personal checking** requires all of:

- verified identity;
- customer is at least 18;
- fewer than four existing personal checking accounts before opening;
- no checking account closed for cause in the last six months; and
- an exact official checking `account_class` selected by the customer.

**New personal savings** requires all of:

- verified identity;
- at least one active Rho-Bank checking account, opened at least 14 days ago;
- fewer than five existing personal savings accounts;
- no account in collections and no negative account balance; and
- an exact official savings `account_class` selected by the customer.

Opening a checking account today does **not** satisfy the savings account's 14-day checking-tenure requirement today. If an existing qualifying checking account is available, it may establish savings eligibility even if a newly opened checking account will later replace it.

### 4. Discuss choices and funding before acting

Explain meaningful, documented tradeoffs and ask the customer to select exact products. For a customer seeking the highest rate, distinguish a headline rate from the requirements needed to keep the account benefits/rate. Use `scripts/compare_savings_rates.py` to calculate documented base rates plus applicable linked-checking and highest-card bonuses for a stated deposit and known holdings.

Important documented examples of this comparison:

- Diamond Elite has a 7.5% base APY, a $100,000 opening deposit, and a $250,000 ongoing minimum balance.
- Platinum Plus has a 7.0% base APY, a $50,000 opening deposit, and a $100,000 ongoing minimum balance.
- Purple checking paired with Platinum Plus savings has a +0.3% linked-checking boost.
- Credit-card bonuses do not stack: only the highest applicable active-card bonus counts. A qualifying checking boost can stack with that one card bonus.

Never describe an account as the customer’s best sustainable choice without considering the amount they can maintain, documented opening/ongoing requirements, and known eligible cards/checking accounts. Do not invent a bonus when a pairing is not documented.

Before a savings opening, establish how it will be funded:

- If the customer authorizes an immediate internal transfer, identify a distinct, active/open checking source with sufficient funds and transfer the required positive USD amount only after the new savings account exists.
- If the customer declines or lacks a usable internal source, state that the account must be funded within 30 days by internal transfer or external deposit or it will close.
- Do not transfer merely because the customer says they have savings elsewhere; explicit transfer authorization and a valid internal source are required.

### 5. Preserve eligibility and perform actions in the safe sequence

For a transition involving the customer's only seasoned checking account, generally use this order after all confirmations:

1. Open the selected new checking account, if requested and eligible.
2. While the old seasoned checking remains active, open the selected savings account if its eligibility is satisfied.
3. Perform an internal opening-deposit transfer only if the customer expressly authorized it and all transfer preconditions pass.
4. Re-check the old checking account's closure requirements from live data.
5. Close the old checking account only after it is confirmed eligible.

When opening, call `open_bank_account_4821` with the authenticated user ID, `account_type` set to `checking` or `savings`, and the customer-confirmed full official account class. Report the returned new account details, not assumed IDs.

### 6. Close a checking account only when eligible

For closure, verify all of the following immediately before calling the closure tool:

- account status is `OPEN`;
- there are no pending transactions;
- determine the tier and whether the account is within its early-closure window;
- if an early fee applies, current holdings are at least the fee; otherwise current holdings must be exactly $0.

Tier schedule:

| Tier | Account classes | Early fee/window | Notice |
|---|---|---:|---:|
| Entry | Light Blue Account, Light Green Account, Green Fee-Free Account | $15 within 30 days | 0 days |
| Mid | Blue Account, Green Account (checking) | $25 within 60 days | 3 days |
| Premium | Evergreen Account | $50 within 90 days | 7 days |
| Elite | Bluest Account | $100 within 180 days | 14 days |

If the balance is nonzero and no early fee applies, or if it is below the applicable early fee, do not close it. Do not assume an “essentially zero” balance is eligible. If the account's opening date or pending status cannot be verified, do not close it.

### 7. Complete the customer-facing response

State, separately and accurately:

- which actions completed and their returned account details;
- any account not opened/closed and the precise unmet condition;
- whether savings was funded by internal transfer or has the 30-day funding deadline;
- any rate/product limitations that remain relevant; and
- any next customer confirmation needed.

Do not claim a rate, transfer, opening, or closure completed until its tool reports success.

## Failure and escalation handling

- For an explicit request to close an account that cannot be completed due to a technical/system failure, transfer to a human using `account_closure_request` (higher-priority than a generic technical reason) and summarize verified facts and the failed step.
- For an actual technical error that prevents the broader requested workflow and is not specifically a closure issue, use `technical_system_error`.
- Do not transfer just because routine eligibility is unmet; explain the objective requirement and next step.
- If a customer requests a human for an ordinary preference after the request is complete, use the applicable lower-priority transfer reason. Always choose the highest-priority applicable reason.

## Helper script contracts

`assess_account_workflow.py` reads one JSON object from stdin and emits one JSON object to stdout. Input fields are documented in that script. It validates current checking/savings-opening gates and closure facts from normalized account records.

`compare_savings_rates.py` reads one JSON object from stdin and emits documented modeled savings candidates with base APY, applicable linked-checking/card bonuses, effective APY, and opening/ongoing balance findings. It supports only the product/bonus rows contained in the supplied knowledge; an omitted product or unavailable fact must be handled manually rather than guessed.
