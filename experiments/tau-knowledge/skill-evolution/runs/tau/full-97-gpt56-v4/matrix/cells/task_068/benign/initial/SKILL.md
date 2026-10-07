---
name: bank-account-transition-and-apy-planner
description: Safely handle a customer request to close/replace a personal checking account, open a savings account, and compare the highest attainable savings APY. Use for Rho-Bank account-opening/closure requests where eligibility, identity verification, account data, product compatibility, and credit-card bonus stacking must be considered.
---

# Bank Account Transition and APY Planner

Use this Skill to separate (1) information and rate comparisons from (2) irreversible bank actions. Never infer an account's balance, age, status, pending activity, verification status, ownership, or product eligibility from a customer's statement alone.

## Inputs and tool boundaries

At runtime, read the customer conversation, the available product documentation, and the supplied tool schemas.

* Treat read-only lookup results as evidence only for the fields actually returned.
* Do not claim that an unavailable account or transaction lookup was performed. In particular, a documented tool is not usable unless it is present in the runtime or can be unlocked as a declared agent tool.
* Use only normal banking tools declared in the runtime. A script in this package only calculates recommendations; it never opens, closes, transfers, applies for a card, or changes an account.
* Do not disclose a customer's profile fields merely because a lookup returned them. Use them only to validate fields that the customer supplies during authentication.

## 1. Authenticate before account-specific action

An email address or customer ID identifies a profile but does not itself complete identity verification.

1. Locate the profile through an allowed lookup, if needed.
2. Ask the customer to confirm at least two independent profile fields (for example, date of birth plus address, phone number, or email).
3. Compare the supplied values against the retrieved profile. Do not provide the stored values as prompts or hints.
4. Once two fields match, call `get_current_time` and `log_verification` with the complete profile fields and timestamp, if those tools are available.
5. If two fields have not been confirmed, give general product information only; do not open, close, transfer, or expose account-specific facts.

## 2. Determine what can actually be completed

### Closing personal checking

Before calling the documented closure tool, obtain and verify all of the following for the specific account:

* correct account identity and account class;
* status is `OPEN`;
* no pending transactions;
* date opened and current holdings/balance;
* the applicable tier's notice period and early-closure window.

The balance must be zero unless an early-closure fee applies; when it does, the balance must be at least that fee because the fee is deducted from the account. For an entry-tier checking account, the fee is $15 if closure is within 30 days and notice is zero days. Never assume that a customer saying they moved money out establishes an exact zero balance, absence of pending transactions, or opening date.

If all conditions are evidenced and the customer has authorized closure, unlock and call `close_bank_account_7392` only if it is available. If needed account/transaction data cannot be obtained through permitted tools, explain precisely which records must be verified and do not close the account. If the customer needs assisted completion, transfer using `account_closure_request` with a concise summary of the missing prerequisites and completed authentication; do not invent a closure result.

### Opening personal checking

Before opening, verify the customer is verified, 18 or older, has no more than four personal checking accounts, and has no checking account closed for cause in the previous six months. Confirm the exact full official checking `account_class` ending in `Account`. Only then unlock and call `open_bank_account_4821` with `account_type: "checking"` and the authenticated `user_id`.

### Opening personal savings

Before opening, verify identity; at least one active Rho-Bank checking account; checking tenure of at least 14 days; fewer than five personal savings accounts; and no collections or negative balances. Confirm the exact full official savings `account_class` ending in `Account`.

After successful eligibility checks and customer selection, use `open_bank_account_4821` with `account_type: "savings"`. Then ask whether the customer authorizes an immediate opening-deposit transfer. Do not transfer unless authorized, both accounts are `ACTIVE` or `OPEN`, are owned by the customer, have distinct valid IDs, and the source has sufficient available funds. Use `transfer_funds_between_bank_accounts_7291` only after those checks. If funding is deferred, state the documented 30-day funding deadline and possible closure.

An unavailable account lookup makes the account-count, tenure, status, negative-balance, and collections checks unverified. Do not replace these checks with guesses or a recommendation.

## 3. Answer early-direct-deposit questions

Check the exact checking-account documentation. Distinguish a feature of up to one or more days early from zero days early. Do not recommend a checking account that lacks the customer's stated early-direct-deposit requirement merely because it produces a higher linked-savings boost.

## 4. Evaluate the highest attainable APY

First establish the customer's constraints: balance to retain, duration, withdrawals/deposits, required checking features, and whether a conditional credit-card application subject to approval is acceptable.

Build a runtime product dataset from the current documentation. For each savings candidate, record the applicable base APY at the customer's stated balance, opening and ongoing balance requirements, and any tier threshold. For each checking candidate, record early-direct-deposit days and the exact savings classes to which it provides a boost. For each card candidate, record its savings-class-specific bonus and application conditions.

Run `scripts/rank_apy_options.py` with the documented schema below. Supply percentages as percentage points (for example, `5.5`, not `0.055`).

Apply these rules:

1. Exclude savings accounts whose opening, maintenance, or balance-tier requirements the stated balance cannot meet.
2. Exclude checking accounts that fail mandatory features such as the requested minimum early-direct-deposit days.
3. A checking boost applies only for an expressly documented checking/savings pairing.
4. If more than one eligible checking account could boost the same savings account, use only the highest boost; checking boosts do not stack.
5. If multiple credit cards provide bonuses for the same savings account, use only the single highest applicable card bonus; credit-card bonuses do not stack.
6. The selected checking boost and selected card bonus may be added to the savings base APY when the documentation says those categories stack.
7. Clearly identify conditions: card approval/application requirements, account-opening eligibility, required funding, and keeping linked products active and in good standing.

For a stable balance held for exactly one year, the script reports `principal × APY / 100` as the one-year interest implied by APY and the ending balance as `principal × (1 + APY / 100)`. This does not double-count daily compounding: APY is already an annual yield. Do not promise a rate, interest credit, or approval when documentation makes it conditional.

### Script input/output

`rank_apy_options.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input:

```json
{
  "principal": "25000",
  "required_early_direct_deposit_days": 1,
  "savings": [{"name":"...", "base_apy":"5.5", "opening_min":"0", "ongoing_min":"10000", "min_balance_for_rate":"0"}],
  "checking": [{"name":"...", "early_direct_deposit_days":1, "boosts":{"Savings Account":"0.75"}}],
  "credit_cards": [{"name":"...", "bonuses":{"Savings Account":"0.6"}, "conditional_note":"subject to approval"}]
}
```

`max_balance_for_rate` may be supplied on a savings candidate to exclude a rate tier when the principal exceeds it. `credit_cards` may be an empty list. The result contains `ranked_options`, exclusions, and errors. The executor must review the conditions in the selected result before communicating it.

## 5. Customer response and validation

In the final response, state separately:

* what was completed versus what cannot be completed with the available evidence/tools;
* the recommended compatible combination, effective APY, and one-year illustration, if a valid option exists;
* why other options were excluded when that clarifies a tradeoff (for example, no early direct deposit or a balance requirement);
* any required confirmation, authentication, eligibility verification, funding decision, or credit-card approval still outstanding.

Before any banking action, validate: authenticated customer, exact account class, eligibility evidence, account IDs, status, balance, amount, authorization, and tool success. After a transfer, verify posted results if a permitted tool supports it and avoid duplicate calls. Never retry an operation reported as `UNKNOWN`.

If the customer asks how to obtain missing account facts and no permitted lookup or self-service procedure is documented, state that the information must be verified through an authorized account-review channel; do not invent a portal workflow or claim it has been requested.
