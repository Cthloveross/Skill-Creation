---
name: checking-account-fit-and-opening
version: 1.0.0
description: Recommend a personal checking account from verified product terms, distinguish overdraft fees from optional overdraft-protection transfer fees, and safely open a selected account only after identity, eligibility, and confirmation requirements are met.
---

# Checking Account Fit and Opening

Use this Skill when a customer asks to compare, choose, or open a personal checking account, especially when their requirements include overdraft treatment, linked-account protection, fees, or early direct deposit.

## Safety and decision rules

1. Treat the customer's stated requirements as constraints, not assumptions. In particular, distinguish:
   - an **overdraft fee** charged by the checking account; and
   - an **overdraft-protection transfer fee** charged only when an optional linked-account transfer is triggered.
2. Do not claim that an account provides overdraft protection merely because its overdraft fee is $0. Verify that linked-account coverage is supported.
3. Do not select or open an account from a recommendation alone. The customer must explicitly choose the official account class and confirm that they want it opened.
4. Never represent an eligibility condition as satisfied unless it has been checked. Personal-checking eligibility requires verified identity, age 18 or older, no more than four personal checking accounts, and no checking account closed for cause in the prior six months.
5. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

## Product facts available to this workflow

Read `references/product-facts.md` before discussing the products covered by this Skill. Use only the applicable, documented facts; do not infer unlisted features. If product terms or the requested account type are not covered, explain the limitation and obtain authoritative current terms rather than guessing.

For structured comparisons, run `scripts/evaluate_products.py`. It receives the current product facts and the requirements expressed in the present conversation, so it does not encode a customer, account ID, or preselected answer.

Example invocation through the Skill runtime:

```json
{
  "products": [
    {
      "name": "Account name from current terms",
      "overdraft_fee": "0.00",
      "overdraft_protection": {"available": true, "transfer_fee": "12.50"},
      "early_direct_deposit_days": 1
    }
  ],
  "requirements": {
    "require_zero_overdraft_fee": true,
    "require_overdraft_protection": true,
    "min_early_direct_deposit_days": 1
  }
}
```

The script emits `{ "ok": true, "candidates": [...], "best_candidate": ... }`. It only evaluates supplied data; it does not perform a banking action or choose on the customer's behalf.

## Conversation workflow

### 1. Identify the customer without treating lookup as verification

Use the supplied name or email to locate a unique profile with the appropriate customer-information tool. A record lookup identifies a possible profile but does **not** verify that the speaker controls it. Do not reveal profile data simply to prove a match.

If an account opening is requested, ask the customer to provide any two identity fields from date of birth, email address, phone number, and street address. Compare the supplied values to the unique profile. If two fields match, obtain the current timestamp and call `log_verification` with the retrieved profile values and timestamp. If the profile is not unique, the fields do not match, or verification cannot be completed, do not open an account.

### 2. Elicit and evaluate requirements

Ask only for requirements still needed to make a meaningful recommendation. Common decision dimensions are:

- monthly fee and fee-waiver balance;
- overdraft-fee policy;
- whether automatic transfers from an eligible linked funding account are required and the per-transfer cost;
- early-direct-deposit timing;
- ATM, balance, deposit, and interest needs.

Explain material tradeoffs plainly. A product can have no overdraft fee while still charging a fee for each optional protection transfer. If a requested product declines transactions rather than transferring from a linked account, say so; do not call that a safety net.

When the current requirements map to one documented account, recommend it conditionally and state the decisive facts. If no documented account meets every non-negotiable condition, say which conditions conflict and ask the customer which condition they are willing to relax. Do not present a recommendation as a selection.

### 3. Obtain a selection and authorization

Ask for an explicit response such as: “Yes, open **[full official account_class]**.” The account class must use its full official name ending in `Account`. For an optional overdraft-protection feature, separately explain that it requires an eligible linked source and acceptance of any per-transfer fee. Do not enroll that optional feature merely because the checking account is being opened.

### 4. Verify opening eligibility immediately before opening

After identity verification and explicit selection, verify all documented eligibility criteria:

- customer is at least 18 at the current date;
- customer has at most four personal checking accounts; and
- customer has no checking account closed for cause during the preceding six months.

Use a documented internal eligibility or account-history capability when one is available. If a required criterion cannot be verified, do not assert eligibility and do not submit the opening request. Give the customer the specific next step needed to complete verification.

### 5. Execute only the approved opening

Once identity, eligibility, full account class, fees/terms, and explicit opening confirmation are all complete, unlock the documented agent capability `open_bank_account_4821` and use its returned schema exactly. Supply only values that are verified or supplied by the customer. Review the result before telling the customer the account was opened.

If the tool reports a failure, duplicate, or unknown outcome, do not retry an `UNKNOWN` operation. Report only the confirmed result and use an appropriate supported escalation path when necessary.

### 6. Close clearly

For a successful opening, confirm the exact account class and the confirmed outcome. For a pending choice, answer the product question and ask the smallest next question—usually whether the customer wants the recommended account opened. Never imply that optional protection has been enabled unless that specific enrollment has completed.

## Applying this to an early-direct-deposit follow-up

When a customer who requires no account overdraft fee and linked-account coverage later adds a requirement for early direct deposit, re-evaluate all three constraints. State whether the protection transfer is optional and what it costs. If a documented product meets all three, ask for explicit selection; if a prior candidate lacks the requested early-deposit timing, correct the earlier recommendation rather than preserving it.

## Validation checklist

Before replying or opening, verify that:

- every product claim is supported by the current terms;
- overdraft fees and transfer fees were described separately;
- the customer has explicitly selected an official account class before opening;
- two identity fields were matched and `log_verification` was completed before a banking action;
- age, account-count, and closure-history eligibility were checked before the opening call; and
- the opening tool result, not an assumption, is the basis for any success statement.
