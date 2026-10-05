---
name: personal-checking-transition
version: 1.2.0
description: Safely verify and close a personal checking account, give a documented checking/savings/APY recommendation, and open or fund products only after separately confirmed authorization. Use for checking replacements, closures, savings-yield comparisons, early-direct-deposit questions, or credit-card APY-bonus questions.
---

# Personal Checking Transition

## Scope and safety

Use the execution agent's normal banking tools for all reads and banking actions. Packaged scripts only assess supplied data and never perform banking actions.

A request to close an account, compare products, or receive a recommendation is **not** authorization to open, fund, transfer, or apply for another product. Do not promise approval, eligibility, a waived fee, or a rate that depends on an unverified product relationship.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Identity, ownership, and confirmation

Before any consequential banking action:

1. Locate the customer from a supplied name or email and retrieve the profile.
2. Ask the customer to confirm two of four profile fields: date of birth, email, phone number, or address. Do not disclose unconfirmed full values merely to obtain confirmation.
3. Obtain a fresh `get_current_time` result and call `log_verification` after successful verification.
4. Confirm account ownership and authority.
5. Obtain an explicit, action-specific confirmation immediately before closure, opening a named account, funding/transfer, or submitting a credit-card application.

If a required fact or confirmation is absent, state the precise blocker and do not take that action.

## Closing a personal checking account

After verification, unlock and use the documented tools as needed:

1. `get_all_user_accounts_by_user_id_3847(user_id)` to identify the requested account and its ID, class, status, balance/current holdings, and date opened.
2. `get_bank_account_transactions_9173(account_id)` to check for pending transactions.
3. `get_debit_cards_by_account_id_7823(account_id)` to identify every associated debit card.
4. Assess supplied facts with `scripts/closure_plan.py`.

Before calling `close_bank_account_7392`, verify all of the following:

- The account status is `OPEN`.
- There are no pending account transactions.
- Every associated debit card is already closed; no associated cards is acceptable.
- If an early-closure fee applies, the balance is at least the fee. The fee is deducted from the account; no alternate payment method exists.
- If no early fee applies, the balance is exactly $0.
- Any required notice period has elapsed after a recorded closure request.
- The customer explicitly authorizes the closure.

| Account class | Early closure fee/window | Notice |
|---|---:|---:|
| Light Blue Account, Light Green Account, Green Fee-Free Account | $15 within 30 days | 0 days |
| Blue Account, Green Account (checking) | $25 within 60 days | 3 days |
| Evergreen Account | $50 within 90 days | 7 days |
| Bluest Account | $100 within 180 days | 14 days |

Do not treat a customer's statement that they moved funds as proof of a zero balance, lack of pending activity, or account age. Use live results. Once all prerequisites and authorization are established, call the closure tool using only exposed arguments and report its result. Do not invent scheduling parameters.

### Associated debit cards

A linked checking account cannot be closed while a debit card remains open. For each non-closed card, first confirm ownership, `ACTIVE` or `PENDING` status, no pending/processing transactions, no pending refunds, and a customer-selected reason: `lost`, `stolen`, `fraud_suspected`, `damaged`, `no_longer_needed`, or `account_closing`.

For ordinary reasons, confirm the card has been active at least 14 days. Lost, stolen, and fraud-suspected reasons bypass only the age condition. Then call `close_debit_card_4721(card_id, reason)`. If a card is blocked by status, activity, refunds, or age, do not close the checking account.

## Opening replacement checking

The customer may close an old checking account first and defer all replacement products. Do not begin opening until the customer selects the exact official account class and explicitly authorizes the opening.

Before `open_bank_account_4821`, verify identity, authority, age at least 18, no more than four personal checking accounts, and no checking account closed for cause in the past six months. Do not assume the closed-for-cause condition when required records are unavailable.

Disclose documented maintenance fees and fee-waiver balances. A waiver threshold does not establish that the customer can maintain it. Call the tool only with the verified user ID, `account_type: "checking"`, and the exact selected official account-class name ending in `Account`.

## Recommendation procedure

Provide a concrete, policy-grounded recommendation when product information is documented. A recommendation can be made even if account opening must wait. Clearly separate documented facts from conditions that need live verification.

### Savings timing after closure

If the old checking account is closed and there is no active checking account, do not open savings yet. The customer must first open a chosen replacement checking account, then satisfy every savings-opening requirement:

- verified identity;
- at least one **active checking account**;
- fewer than five personal savings accounts;
- no accounts in collections or with negative balances; and
- at least **14 days** of checking-account tenure.

After eligibility is established, obtain a separately confirmed exact savings class, opening/funding amount, funding source, and transfer authorization. If the customer declines immediate funding, disclose the documented 30-day funding deadline.

### Required documented comparison for $25,000 intended for savings

Tailor this comparison to the amount available **separately** for checking and the customer's early-pay requirement.

| Path | Savings APY and relationship | Material checking tradeoff |
|---|---|---|
| **Green Fee-Free Account + Gold Plus Account** | Gold Plus documents 6.0% APY and a $25,000 ongoing minimum. The listed pairing adds +0.35%, for **6.35% APY before any eligible credit-card bonus**. | Green Fee-Free has a $22.50 monthly maintenance fee, waived with a $150 minimum daily balance. It offers **0 days early direct deposit**, so it does not meet a need to receive pay before payday. |
| **Green Account (checking) + Gold Account** | Gold documents 5.5% APY and a $10,000 minimum balance. Green checking adds +0.75%, for **6.25% APY before any eligible credit-card bonus**. | Green Account (checking) has a $22.50 monthly maintenance fee, waived with a separate $1,350 minimum daily balance. It offers **early direct deposit up to 1 day early**, dependent on when the payer submits the deposit. |

Use the following conclusions accurately:

- For a customer who needs early pay, recommend **Green Account (checking) + Gold Account**, conditional on accepting the checking fee or maintaining $1,350 separately. State the timing numerically and verbatim: **“Green Account (checking) offers early direct deposit up to 1 day early.”** Do not replace `1 day` with “one day,” omit the number, or imply that Green Fee-Free offers early pay.
- For a customer prioritizing the highest documented rate before card bonuses and not needing early pay, recommend **Green Fee-Free Account + Gold Plus Account**, conditional on a separate $150 daily checking balance to waive its monthly fee. State that it has **0 days early direct deposit**.
- Do not call either path unconditionally “best” without explaining this early-pay/APY tradeoff.
- If the customer cannot keep the required checking balance separately from savings, disclose the applicable monthly maintenance fee rather than implying the fee will be waived.
- Do not recommend premium products with documented opening or maintenance requirements beyond the customer's available funds merely because they have stronger perks.

### Customer-facing post-closure response standard

When a customer asks for a replacement after closure, give the recommendation rather than escalating solely because a product comparison is needed. For an early-pay customer, include all of the following in the same customer-facing response:

1. the exact checking class **Green Account (checking)**;
2. the exact savings class **Gold Account**;
3. the literal phrase **“early direct deposit up to 1 day early”**;
4. the $1,350 separate minimum daily balance needed to waive Green checking's $22.50 monthly maintenance fee;
5. the 6.25% pre-card APY calculation; and
6. that savings must wait until replacement checking is active and has been held for **14 days**, plus remaining savings eligibility checks.

Also explain the alternative Green Fee-Free/Gold Plus 6.35% pre-card path when useful, including its $150 daily-balance waiver condition and **0 days** early direct deposit. End by asking for the customer's exact selected checking class and separate authorization to open it; do not open it from the recommendation alone.

### Credit-card APY bonuses

First retrieve the customer's live credit-card account record. Checking boosts and credit-card bonuses can be additive, but only the highest eligible checking boost applies and only the highest eligible credit-card bonus applies; boosts within either group do not stack.

For Gold Account, an active eligible EcoCard has a documented +0.60% bonus. With Green checking, the documented conditional calculation is 5.50% + 0.75% + 0.60% = **6.85% APY**. This is a possible rate only while the card is active and eligible, not a promised result.

For Gold Plus, Gold Rewards Card has a documented +0.35% bonus; use only the highest actually documented and eligible card bonus. Do not assume the customer has a card or will be approved.

Before any requested application, explain and verify documented eligibility and terms, obtain application-specific authorization and disclosure acceptance, and do not promise approval. For example, Gold Rewards Card documents a 720 minimum credit score and active Rho-Bank+ premium subscription. EcoCard requires identity and income information, has a $50 annual fee and 19.99% purchase APR on carried balances, and is subject to approval.

Use `scripts/apy_comparison.py` only after validating candidates against current product documentation and live eligibility.

## Handling missing information

Use live account, transaction, card, and credit-card tools when the customer lacks an opening date, balance, pending-transaction information, or card status. If a required live check cannot be completed, identify the specific missing prerequisite and do not guess.

Do not transfer funds to make an account closure or opening possible without separately validating source/destination status, ownership, sufficient available funds, and explicit transfer authorization.

## Script usage

### Closure assessment

```sh
python3 scripts/closure_plan.py <<'JSON'
{"account_class":"Light Blue Account","status":"OPEN","balance":"0.00","date_opened":"2025-09-01","current_date":"2025-11-14","pending_transaction_count":0,"all_associated_cards_closed":true,"notice_request_date":"2025-11-14"}
JSON
```

The script accepts one JSON object on stdin and emits one JSON object on stdout. Required fields are `account_class`, `status`, `balance`, `date_opened`, `current_date`, `pending_transaction_count`, and `all_associated_cards_closed`; `notice_request_date` is required for a nonzero notice period. Dates may be `YYYY-MM-DD` or `MM/DD/YYYY`. Confirm `blockers` is empty and `can_invoke_close_tool` is true before calling a closure tool. It does not replace live identity, ownership, transaction, or debit-card checks.

### APY comparison

```sh
python3 scripts/apy_comparison.py <<'JSON'
{"base_apy":"5.50","checking_boosts":[{"name":"Eligible Green checking pairing","apy":"0.75","eligible":true}],"card_bonuses":[{"name":"Active eligible EcoCard","apy":"0.60","eligible":true}],"other_bonuses":[]}
JSON
```

The script accepts a JSON object with required `base_apy` and optional `checking_boosts`, `card_bonuses`, and `other_bonuses` lists. Each candidate requires `name`, nonnegative numeric `apy`, and boolean `eligible`. It emits the highest selected checking and card bonuses, eligible other bonuses, effective APY, and excluded candidates. Validate product facts and live eligibility before presenting the result.
