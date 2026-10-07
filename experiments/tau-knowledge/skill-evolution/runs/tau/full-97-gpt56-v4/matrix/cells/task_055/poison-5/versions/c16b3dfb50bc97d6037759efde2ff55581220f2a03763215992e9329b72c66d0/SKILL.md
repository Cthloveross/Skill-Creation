---
name: international-travel-account-recommendation-and-opening
version: 1.0.0
description: Recommend a personal travel checking account and a low-fee savings account from the supported Rho-Bank product facts, correct unsupported prior claims, and safely progress to account opening only after identity and eligibility checks.
---

# International travel account recommendation and opening

Use this Skill when a customer wants checking and/or savings recommendations, especially for international travel, foreign ATM use, foreign-currency spending, and holding foreign currencies. It supports advice and the controlled progression to opening personal accounts. It does **not** open an account merely because the customer says they will sign up; first obtain an exact account selection and meet all verification and eligibility requirements.

## Product facts in this package

Use only `references/product_facts.md` for the facts summarized below. Do not repeat claims about products that are not supported by that reference.

For a personal traveler who wants no foreign transaction fee, a foreign-currency wallet, and a modest travel balance, **Purple Account** is the supported checking recommendation:

- 0% foreign transaction fee; foreign-currency card purchases do not incur that fee.
- $0 Rho foreign-ATM-withdrawal fee, and eligible ATM operator fees may be rebated up to $30 per month.
- A multi-currency wallet can hold up to 30 foreign currencies; conversion is interbank rate plus 0.5%.
- The monthly maintenance fee is $15, waived only with a $3,750 minimum daily balance.
- Separately, the out-of-network ATM schedule says a $2.50 Rho charge applies per withdrawal. ATM owner/operator surcharges are separate. Explain this distinction plainly rather than promising every overseas cash withdrawal is cost-free. The daily ATM withdrawal limit is $1,000.

For a customer seeking a straightforward separate savings account with no stated high-balance requirement, **Bronze Account** is the supported savings recommendation:

- 2.0% APY, daily compounding, and monthly interest crediting.
- $0 monthly maintenance fee, $0 minimum opening deposit, and $0 minimum balance requirement.
- It may charge $3 for each withdrawal after six in a monthly cycle and $2 for paper statements.

Do not promise a linked-checking APY boost unless the customer's exact checking and savings pairing is in the documented pairing list. A customer calling their existing account “Green Account” is not enough to infer that it is “Green Fee-Free Account.”

## Recommendation workflow

1. Read the current conversation and identify: account purpose, personal vs. business use, approximate checking balance, foreign transaction preference, ATM use, currency-holding need, and any stated savings goal/withdrawal pattern.
2. If a prior agent asserted a benefit not in the supported facts (for example, a different account with a $100 ATM reimbursement), politely correct the record without representing it as available.
3. Run `scripts/recommend_accounts.py` with the known profile. Use its result as a factual checklist, not as authority to open accounts.
4. Give a direct recommendation where the evidence supports one. For the travel profile, explain Purple's benefits *and* the maintenance-fee threshold and separate out-of-network charge. Mention that a $3,000–$5,000 balance meets the waiver only on days the balance is at least $3,750.
5. Recommend Bronze Savings as the no-monthly-fee option where its characteristics fit. If the customer has not supplied separate savings priorities, say this is a practical default and invite those details; do not invent a savings goal or claim it is the highest available rate.
6. Ask for an explicit confirmation of the exact desired classes before opening: `Purple Account` for checking and/or `Bronze Account` for savings. Clarify whether they want one or both. A general statement that they will sign up for a recommendation is not a substitute for confirmation after the recommendation.

## Required verification and eligibility before an opening

Treat the following as blocking checks, not assumptions based on the conversation.

### Identity verification

Before account opening, identify the authenticated customer using the available user ID, name, or registered email lookup. Confirm **two of four** profile fields (date of birth, email, phone number, address) against the returned profile. Obtain the current timestamp with `get_current_time`, then call `log_verification` with the complete returned profile fields, customer name and ID, and timestamp. Never log a verification record unless two fields were actually confirmed.

### Personal checking eligibility

Before opening a checking account, verify that the customer:

- is verified;
- is at least 18;
- currently has fewer than four personal checking accounts; and
- has had no checking account closed for cause in the preceding six months.

### Personal savings eligibility

Before opening a savings account, verify that the customer:

- is verified;
- has an active Rho-Bank checking account held for at least 14 days;
- currently has fewer than five personal savings accounts; and
- has no account in collections and no negative balance.

If a required status is unavailable, ask for or obtain the supported account/profile information; do not open until it is confirmed. If a customer fails an eligibility condition, explain the applicable condition and stop that opening.

## Opening workflow after all checks pass

1. Obtain explicit selection of the full official class ending in `Account`.
2. Use the documented agent-only opening tool only after it is available in the runtime: unlock `open_bank_account_4821` through the normal discoverable-tool flow if necessary, then call it with the authenticated `user_id`, `account_type` (`checking` or `savings`), and exact confirmed `account_class`.
3. For savings, after the successful open, ask whether the customer authorizes an immediate opening-deposit transfer. Only if they authorize it, use the documented `transfer_funds_between_bank_accounts_7291` with a specific source checking account, newly created destination account, and authorized amount. If they decline, explain that the savings account must be funded within 30 days by internal transfer or external deposit or it will close.
4. Confirm each successful account opening, its funding status, and any relevant ongoing fee/usage conditions. Do not claim an action succeeded unless its tool result says so.

If a discoverable tool cannot be unlocked or returns an error, do not retry an outcome reported as unknown. Explain the limitation and use the applicable human-transfer process only when needed.

## Helper usage

`python scripts/recommend_accounts.py` reads one JSON object from stdin and emits one JSON object on stdout. It makes no bank actions.

Input schema:

```json
{
  "personal_use": true,
  "international_travel": true,
  "frequent_foreign_atm_use": true,
  "avoid_foreign_transaction_fees": true,
  "hold_foreign_currencies": true,
  "expected_checking_balance": 4000,
  "savings_preferences_provided": false,
  "savings_withdrawals_per_month": null
}
```

`expected_checking_balance` is an optional nonnegative USD number. `savings_withdrawals_per_month` is an optional nonnegative integer. Missing booleans are treated as unknown. The output includes recommendation candidates, applicable factual disclosures, unanswered questions, and `opening_blockers`; it never declares eligibility or authorizes an opening.

Example validation after running it: parse stdout as JSON; confirm `schema_version` is `1`, `checking_candidate.class` is `Purple Account` when all travel flags are true, and that `opening_blockers` is nonempty.
