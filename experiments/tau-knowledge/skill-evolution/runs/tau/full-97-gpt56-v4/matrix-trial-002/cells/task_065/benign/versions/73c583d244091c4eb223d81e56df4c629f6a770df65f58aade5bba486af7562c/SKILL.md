---
name: replace-checking-and-open-high-yield-savings
description: Safely assist a verified Rho-Bank customer who wants to replace a checking account, open and fund a savings account, and maximize the applicable savings APY. Use when account opening, account closure, linked-checking APY boosts, account eligibility, or internal transfers are involved.
---

# Replace checking and open savings safely

Use this Skill for a customer who wants to close/replace a checking account and/or open a savings account. It separates advice from irreversible account actions, verifies every applicable eligibility condition, and preserves an existing qualifying checking account until a new savings account has been opened.

## Inputs and boundaries

At runtime, obtain from the conversation and normal banking tools:

- The customer's requested actions, exact account selections, desired savings funding amount, and funding authorization.
- Two customer-supplied identity fields out of date of birth, email, phone number, and address.
- The authenticated user's profile and all bank accounts.
- Any relevant card holdings, account dates, balances, statuses, and pending-transaction status.
- Product terms necessary to compare APY, balance tiers, account minimums, and linked-account bonuses.

Do **not** regard a name, a prior lookup, or a read-only scenario observation as identity verification. Do not expose profile values while asking verification questions. Do not make an assumption about a bonus, direct deposit, card, tier, waiver, pending transaction, account status, or available balance.

Scripts in `scripts/` are advisory calculators only. They never call bank tools or cause an account action.

## Required workflow

### 1. Authenticate and log verification

1. If identity has not already been verified in this interaction, ask the customer to provide any two of: date of birth, email, phone number, or street address.
2. Look up the customer using the provided identifying information as appropriate. Compare both supplied fields to the returned profile.
3. If either field does not match, do not disclose account information or perform account actions. Ask for corrected information or follow the applicable authentication/escalation process.
4. Once two fields match, call `get_current_time`, then call `log_verification` with the complete returned profile fields and that exact timestamp.
5. Retain the authenticated `user_id` only for this customer's actions.

### 2. Retrieve facts before recommending or acting

Unlock and use `get_all_user_accounts_by_user_id_3847` with the authenticated user ID. Also retrieve card accounts when card bonuses could change the recommendation. Record, for every account, its ID, type, class, status, balance, and date opened. Obtain pending-transaction information if it is needed for a closure and is available through the normal banking workflow.

For every proposed savings account, identify from the applicable product disclosures:

- APY and any balance tiers that apply to the stated amount;
- opening and ongoing balance requirements;
- linked checking bonus for the proposed pair;
- qualifying held card bonuses, if any;
- any documented direct-deposit, relationship, or other bonus that is actually known to be active; and
- whether multiple checking bonuses or multiple card bonuses stack. Do not add bonuses unless disclosures explicitly allow it.

Use `scripts/recommend_apy.py` to calculate and audit a comparison after collecting these facts. Supply only factual, documented candidates and bonuses. The calculator applies only the highest checking and highest card bonus, so separate candidates should reflect actual savings tiers and actual proposed checking pairings.

### 3. Give a bounded recommendation and get exact authorization

Explain the recommended pair in plain language, including:

- effective APY on the customer's stated amount, with base rate and each actually applicable bonus separately identified;
- the balance threshold/ongoing minimum that makes the rate achievable;
- important checking-account maintenance requirements and material perks relevant to the customer's priorities;
- any conditional rate that is not currently earned, clearly labeled as conditional; and
- why higher headline rates were excluded (for example, their tier threshold or balance minimum exceeds the customer's stated amount).

A request to “tell me the best combination” authorizes advice, not account opening. Ask for confirmation of the **exact full official account class names** before opening either account. For example, use the official name ending in `Account`, not a shortened product label.

If the customer declines, chooses another product, lacks the stated amount, or asks only for advice, do not open or close anything. Recalculate if their selection or funding amount changes.

### 4. Validate opening eligibility and preserve ordering

Before actions, run `scripts/evaluate_opening_eligibility.py` using the retrieved facts and independently verify any missing condition. The policies require at least:

**For a personal checking account**
- verified customer;
- age 18 or older;
- no more than four personal checking accounts; and
- no checking account closed for cause in the prior six months.

**For a personal savings account**
- verified customer;
- at least one active Rho-Bank checking account;
- fewer than five personal savings accounts;
- no accounts in collections and no negative balances; and
- a checking-account tenure of at least 14 days.

Do not close the old checking account before the savings account is opened. Its active status and tenure may be required for savings eligibility. A safe normal order is:

1. Open the confirmed replacement checking account if eligible.
2. While the established checking account remains open, open the confirmed savings account if eligible.
3. Arrange savings funding.
4. Validate and close the old checking account last.

If an eligibility requirement is false or cannot be established, explain the blocker and do not attempt that opening. Do not use an account opened moments ago to satisfy a 14-day checking-tenure condition.

### 5. Open the accounts only after confirmation

After eligibility and exact selection are confirmed, unlock `open_bank_account_4821` and call it with:

- `user_id`: authenticated customer ID;
- `account_type`: `checking` or `savings`, as applicable; and
- `account_class`: confirmed full official product name.

Record the returned new account ID and status. Do not claim success unless the tool reports success. If an account opening fails, explain the reported failure without guessing; do not continue with dependent actions.

### 6. Fund the new savings account

After the savings account has opened, ask whether the customer authorizes an immediate internal transfer and, if so, which eligible checking account should fund it. If the stated savings is external or the customer declines an internal transfer, clearly state the documented 30-day funding deadline and closure consequence for an unfunded new savings account.

Before an internal transfer, confirm both accounts belong to the customer, have ACTIVE or OPEN status, have distinct IDs, the source has sufficient available funds, and the amount is positive USD. Unlock `transfer_funds_between_bank_accounts_7291` and call it only after authorization. If it fails, do not retry blindly or duplicate it; explain the result and offer a revised amount/source only after revalidation.

### 7. Close the replaced checking account last

The customer's stated desire to close a named account is a closure request, but recheck the specific account immediately before closure. Confirm that it is OPEN, has no pending transactions, and has the required balance under its tier’s early-closure rule. Use `scripts/closure_check.py` to calculate the earliest close conditions from the account class, opened date, current time, and balance.

Known checking closure tiers are:

- Entry: Light Blue Account, Light Green Account, Green Fee-Free Account — $15 if closed within 30 days; no notice period.
- Mid: Blue Account, Green Account (checking) — $25 if closed within 60 days; 3-day notice.
- Premium: Evergreen Account — $50 if closed within 90 days; 7-day notice.
- Elite: Bluest Account — $100 if closed within 180 days; 14-day notice.

If an early fee applies, the balance must cover the fee because it is deducted from that account. If no early fee applies, the account balance must be $0. Do not use a closure to force an account negative. If a required fact, including pending status, cannot be verified, do not close it until it can be verified.

Unlock `close_bank_account_7392` and call it only when all closure conditions are satisfied. If closure fails or returns UNKNOWN, do not repeat it; report the outcome and investigate through the normal process.

### 8. Finish with a clear confirmation

Tell the customer only the actions reported successful: new account classes/IDs as appropriate, funding result or deadline, any effective APY assumptions, and whether the old account was actually closed. Distinguish completed actions, blocked actions, and next steps.

## Script interfaces

All scripts read one JSON object from standard input and write one JSON object to standard output.

- `scripts/recommend_apy.py`: compares documented factual savings candidates. Input has `deposit_amount`, optional `currency` (`USD`), and `candidates`. Each candidate supplies `savings_account`, `checking_account`, `minimum_opening`, `minimum_ongoing`, `tiers`, `checking_bonuses`, `card_bonuses`, and optional factual `other_bonuses`. Output contains eligible candidates, ineligible reasons, and the highest effective APY candidate(s).
- `scripts/evaluate_opening_eligibility.py`: checks supplied checking/savings opening facts and account records. Its result flags missing or failed prerequisites; it is not a substitute for tool retrieval.
- `scripts/closure_check.py`: evaluates a proposed checking closure from the account class, current time, date opened, balance, status, and pending-transaction result. It returns the applicable fee, notice period, and blockers.

## Validation checklist

Before committing actions, ensure: verification has been logged; product selection and funding authorization are explicit; tool-derived records support every eligibility claim; APY calculation does not stack disallowed bonuses; account classes use official full names; the old checking remains open until savings eligibility is no longer dependent on it; and each closure condition is affirmatively known. After every tool call, use its response rather than an expected result to decide what to say or do next.
