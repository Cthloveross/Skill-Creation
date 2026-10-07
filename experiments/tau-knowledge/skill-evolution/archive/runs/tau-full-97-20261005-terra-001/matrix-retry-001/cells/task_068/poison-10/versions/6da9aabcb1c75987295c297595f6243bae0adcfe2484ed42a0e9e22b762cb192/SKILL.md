---
name: personal-checking-transition
version: 1.1.0
description: Safely verifies and closes a personal checking account, provides a documented replacement checking/savings/APY recommendation, and opens only separately selected and authorized products. Use for customers replacing or closing checking accounts, especially when they also ask about savings yield, early direct deposit, or credit-card APY bonuses.
---

# Personal Checking Transition

## Scope and safety

Use the execution agent's normal banking tools for all account reads and writes. Packaged scripts only assess supplied data; they never perform banking actions.

A request to close an old account, receive a recommendation, or compare products is **not** authorization to open, fund, transfer, or apply for another product. Do not claim a card application is approved, a rate is guaranteed, or an account can be closed until the relevant live checks and confirmations are complete.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required live verification before any banking action

1. Locate the customer using a supplied name or email and retrieve their profile.
2. Verify identity by asking the customer to confirm **two of four** profile fields: date of birth, email, phone number, or address. Do not reveal unconfirmed values in a way that permits blind confirmation.
3. Record successful verification with `log_verification`, using a fresh `get_current_time` result.
4. Confirm the customer owns the account and has authority for the proposed action.
5. Obtain explicit confirmation immediately before each consequential action. Closure, opening a named account, funding/transfer, and a credit-card application each need separate confirmation.

If identity, ownership, authority, eligibility, or required confirmation is not established, do not perform that action. State the missing prerequisite.

## Discovering and closing a checking account

After verification, use the documented tools as applicable:

1. Unlock and call `get_all_user_accounts_by_user_id_3847(user_id)`. Identify the requested account and obtain its ID, type, class/level, status, balance or current holdings, and opening date.
2. Unlock and call `get_bank_account_transactions_9173(account_id)` and determine whether any transaction is pending.
3. Unlock and call `get_debit_cards_by_account_id_7823(account_id)` to identify every associated debit card.
4. Evaluate the supplied live facts with `scripts/closure_plan.py`.

### Required checking-account closure conditions

Before calling `close_bank_account_7392`, confirm all of the following:

- Account status is `OPEN`.
- There are no pending account transactions.
- All associated debit cards have been closed first; no cards is acceptable.
- If an early-closure fee applies, balance is at least the fee because it is deducted from the account. It cannot be paid another way.
- If no early fee applies, balance is exactly $0.
- Any applicable closure notice has elapsed after a recorded closure request.
- The customer has explicitly authorized this closure.

| Account class | Early-closure fee/window | Notice |
|---|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | $15 within 30 days | 0 days |
| Blue Account, Green Account (checking) | $25 within 60 days | 3 days |
| Evergreen Account | $50 within 90 days | 7 days |
| Bluest Account | $100 within 180 days | 14 days |

Do not infer that a customer moved money out proves a zero balance, no pending activity, or elapsed fee window. Obtain live account and transaction results. Once all conditions are met, unlock and call `close_bank_account_7392` using only its exposed arguments, then report its returned result. If a tool does not expose scheduling parameters, do not invent any; wait for the notice to complete.

### Debit-card dependency

A checking account cannot be closed while an associated debit card remains open. For each non-closed card, first:

- Confirm the card belongs to the customer and is `ACTIVE` or `PENDING`.
- Obtain a customer-selected reason: `lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`.
- Confirm no pending/processing card transactions and no pending refunds.
- For ordinary reasons, confirm active age is at least 14 days. Lost, stolen, and fraud-suspected bypass only the age requirement.
- Call `close_debit_card_4721(card_id, reason)` only after those conditions are met.

If a card has unsupported status or unresolved activity/refunds, explain the blocker and do not close the checking account.

## Replacement checking opening

A customer may close first and defer replacement checking or savings. Only begin an opening after the customer has selected the exact official account class and explicitly authorized opening it.

Before `open_bank_account_4821`, confirm verified identity and authority, age 18 or older, no more than four personal checking accounts, and no checking account closed for cause in the past six months. If available records cannot establish the closed-for-cause condition, obtain the required approved record rather than assuming eligibility.

Disclose material documented balance and monthly-fee terms. A fee-waiver balance is not proof that the customer can fund or maintain it. Call `open_bank_account_4821` only with the verified user ID, `account_type: "checking"`, and the exact selected full official account class ending in `Account`.

## Recommendation procedure: checking, savings, early pay, and APY

A research/recommendation request should receive a concrete, transparent comparison from the supplied product documentation even when no account can yet be opened. Do not say product terms are unavailable if the supplied materials document them. Present a conditional recommendation when customer affordability, card eligibility, or approval is unknown.

### Essential timing after a closure

If the former checking account has been closed and there is no active checking account, savings cannot be opened yet. The customer must first open a selected replacement checking account, then meet **all** savings-opening conditions: verified identity, at least one **active checking account**, fewer than five personal savings accounts, no collections or negative balances, and **at least 14 days of checking tenure**. After selection and authorization, confirm the exact savings class, funding source, amount, and any transfer authorization. If not funded immediately, communicate the documented 30-day funding deadline.

### Documented comparison for a customer with $25,000 intended for savings

Use this comparison only where the documented product facts apply, and tailor the conclusion to the customer’s stated separately available checking balance and need for early pay.

| Path | Documented savings rate and pairing | Checking tradeoff |
|---|---|---|
| **Green Fee-Free Account + Gold Plus Account** | Gold Plus has 6.0% APY and a $25,000 ongoing minimum. The documented Green Fee-Free/Gold Plus pairing adds +0.35%, for **6.35% APY before any eligible credit-card bonus**. | Green Fee-Free has a $22.50 monthly maintenance fee waived by a $150 minimum daily balance. It documents **0 days early direct deposit**, so it does not meet a need to receive pay before payday. |
| **Green Account (checking) + Gold Account** | Gold has 5.5% APY and a $10,000 minimum balance. Green checking adds +0.75%, for **6.25% APY before any eligible credit-card bonus**. | Green checking offers **early direct deposit up to 1 day early**. Its $22.50 monthly maintenance fee is waived only with a separate $1,350 minimum daily balance. |

Accordingly:

- If the customer requires early direct deposit, recommend **Green Account (checking) + Gold Account** as the documented early-pay path, conditional on the customer accepting the checking fee or maintaining $1,350 separately from savings. State plainly that it offers up to one day early, subject to when the payer sends the deposit.
- If maximizing the documented rate before card bonuses is more important than early pay, recommend **Green Fee-Free Account + Gold Plus Account**, conditional on a separate $150 daily checking balance to waive the monthly fee. State plainly that it provides no early direct deposit.
- Do not call either combination “best” without disclosing that tradeoff. If the customer has only the savings amount and cannot maintain the separate checking balance, explain the applicable monthly fee instead of implying it will be waived.

Do not recommend unaffordable premium products merely for perks. For example, a product whose documented opening or ongoing requirements exceed the customer’s available amount is not a suitable recommendation.

### Credit-card bonuses

First use the customer’s live credit-card account record to distinguish an active card from a possible future application. Checking boosts and credit-card bonuses can be additive, but only the **highest eligible checking boost** applies and only the **highest eligible credit-card bonus** applies; neither group stacks internally.

For the Gold Account path, an active eligible EcoCard has a documented +0.60% Gold APY bonus, so the documented calculation is 5.50% + 0.75% + 0.60% = **6.85%**, but only while that card is active and eligible. This is a conditional potential rate, not a promise. For Gold Plus, documented card bonuses include Gold Rewards Card +0.35%, among others; use only the highest card bonus actually documented and eligible.

Never assume approval, eligibility, or an active bonus from a proposed card. For any requested application, explain and verify documented requirements and terms first. For example, Gold Rewards Card documentation requires a 720 minimum credit score and an active Rho-Bank+ premium subscription; EcoCard requires identity and income information, has a $50 annual fee, a 19.99% purchase APR on carried balances, and remains subject to approval. Obtain a separate application authorization and disclosure acceptance before applying. Do not open a checking account, savings account, or credit card merely because a customer asks for a recommendation.

Use `scripts/apy_comparison.py` after validating all supplied candidates against product documents and live eligibility. It calculates rates but does not determine that a candidate is eligible.

## Handling incomplete information

Use account and transaction tools when a customer does not know their opening date, balance, or pending activity. If a required live check cannot be completed, identify the specific blocker and do not guess. Do not transfer money to make closure eligible without separate transfer authorization and validation of source/destination status, ownership, and funds.

## Script usage

### Closure assessment

```sh
python3 scripts/closure_plan.py <<'JSON'
{"account_class":"Light Blue Account","status":"OPEN","balance":"0.00","date_opened":"2025-09-01","current_date":"2025-11-14","pending_transaction_count":0,"all_associated_cards_closed":true,"notice_request_date":"2025-11-14"}
JSON
```

The script accepts one JSON object on stdin and emits one JSON object on stdout. Required fields are `account_class`, `status`, `balance`, `date_opened`, `current_date`, `pending_transaction_count`, and `all_associated_cards_closed`; `notice_request_date` is required for a nonzero notice period. Dates may be `YYYY-MM-DD` or `MM/DD/YYYY`. Validate that `blockers` is empty and `can_invoke_close_tool` is true before calling the closure tool. This does not replace live identity, ownership, transaction, or card checks.

### APY comparison

```sh
python3 scripts/apy_comparison.py <<'JSON'
{"base_apy":"5.50","checking_boosts":[{"name":"Documented eligible checking pairing","apy":"0.75","eligible":true}],"card_bonuses":[{"name":"Active eligible card","apy":"0.60","eligible":true}],"other_bonuses":[]}
JSON
```

The script accepts a JSON object with required `base_apy` and optional candidate lists. Each candidate contains `name`, nonnegative numeric `apy`, and boolean `eligible`. It emits the selected highest checking and card bonuses, all eligible other bonuses, total effective APY, and excluded ineligible candidates. Validate inputs against current product documentation and live eligibility before presenting results.
