---
name: checking-account-recommendation-and-opening
version: 1.0.0
description: Recommend and, after required identity, eligibility, product, fee, and confirmation checks, open a personal checking account. Use when a customer wants help selecting or opening a checking account, including requests involving overdraft handling or early direct deposit.
---

# Checking Account Recommendation and Opening

Use this workflow to give an accurate recommendation without treating a recommendation as authorization to open an account. All bank mutations must be performed only through the declared normal banking tools.

## Product facts used by this workflow

Read [references/checking_product_rules.md](references/checking_product_rules.md) before giving a product-specific answer. In particular, distinguish an account's ordinary overdraft fee from an optional overdraft-protection transfer fee. A customer who requires both no ordinary overdraft fee and at least one day of early direct deposit can be matched to Blue Account if its other terms are acceptable:

- Blue Account's ordinary overdraft fee is $0.00.
- Optional linked-account overdraft protection may transfer funds to cover a transaction that would otherwise go negative, and costs $12.50 for each triggered transfer.
- Blue Account offers direct deposit one day early.
- Its $20 monthly maintenance fee is waived with a $625 minimum daily balance.

Do not represent this optional protection transfer as free, guarantee that a transfer will occur, or imply that it eliminates the need to maintain sufficient funds.

## Required checks before any banking action

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For an account-opening request:

1. Identify the customer by an available lookup method, but do **not** treat a name lookup or data already displayed to the agent as identity verification.
2. Ask the customer to confirm at least two of these profile fields: date of birth, email address, phone number, or street address. Compare the supplied values to the retrieved profile.
3. If two fields match, get the current time and call `log_verification` with the complete retrieved profile, the user ID, and that timestamp. If they do not match, are incomplete, or the profile is ambiguous, do not disclose profile data or proceed with account actions; ask for the missing/correct fields or use the applicable escalation path.
4. Confirm the requester is the customer/account owner and has authorized the requested opening.
5. Retrieve all customer bank accounts using the documented account-information tool. If it is discoverable, unlock `get_all_user_accounts_by_user_id_3847` first, then call it with the verified user ID.
6. Check and document each opening prerequisite: verified customer; age at least 18; no more than four personal checking accounts; and no checking account closed for cause during the previous six months. Do not infer account count, status, closure history, linked-savings eligibility, or balance from a customer statement.
7. Confirm the official full `account_class` name ending in `Account`, explain any relevant fee/feature terms, and obtain explicit authorization to open that exact product. A statement of product preferences or a request for a recommendation is not opening authorization.

If information is unavailable or a prerequisite fails, explain the specific blocking prerequisite and do not attempt the opening.

## Conversation method

1. Extract the customer's must-have and nice-to-have features. When requirements conflict, say so plainly rather than recommending a product that misses a non-negotiable.
2. Use `scripts/recommend_checking.py` for deterministic feature matching when structured product options are available. The script is advisory; verify product facts against the reference before presenting them.
3. Present the best match in clear language, including relevant fees, waiver conditions, limits, and tradeoffs. For a request for no ordinary overdraft fee, optional automatic linked-account coverage, and at least one day early direct deposit, explain Blue Account's two separate fee categories and early-deposit timing.
4. Ask whether the customer wants to open the identified official account class. If identity has not been verified, also request two identity fields in the same response. Do not ask the customer to repeat a field already securely verified.
5. Once the customer explicitly authorizes Blue Account and all checks pass, unlock `open_bank_account_4821` if necessary and call it with the documented arguments, including the verified customer ID and exact official account class. Follow the tool's returned result; do not claim success before it succeeds.
6. If the customer also wants overdraft protection, complete opening first. Then retrieve and verify ownership, eligibility, and sufficient available balance of the proposed linked funding account; disclose and obtain explicit acceptance of the $12.50 per-triggered-transfer fee before enabling it. Use only the normal documented settings/action tool available in the runtime. If no such tool is available, explain how to enroll through account settings rather than claiming it was enabled.
7. Summarize the completed result, account class, material fees/waiver condition, and any action still needed. Never expose full personal data in the response.

## Opening procedure

After all required checks and explicit customer authorization are complete:

- Personal checking `account_class` must be the exact full official name ending in `Account` (for example, `Blue Account`).
- Unlock and use `open_bank_account_4821` only after validating the opening conditions above.
- Pass only the arguments documented by the runtime tool. Do not invent an opening-deposit, linked-account, or overdraft-protection parameter.
- Treat an error, timeout, or unknown result as not completed. Do not retry an operation reported as `UNKNOWN`; inform the customer and use the applicable support process.

## Runnable recommendation helper

`scripts/recommend_checking.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "requirements": {
    "no_overdraft_fee": true,
    "needs_overdraft_protection": true,
    "min_early_direct_deposit_days": 1
  },
  "products": [
    {
      "account_class": "Example Account",
      "ordinary_overdraft_fee": 0,
      "overdraft_protection_available": true,
      "overdraft_protection_transfer_fee": 12.5,
      "early_direct_deposit_days": 1
    }
  ]
}
```

Output includes `matches` (products meeting all requested hard requirements) and `rejections` (per-product reasons). It rejects malformed input rather than silently choosing a product. Validate that the selected `account_class` is an exact official class and that every claimed field was sourced from applicable product documentation before using the output in a customer response.
