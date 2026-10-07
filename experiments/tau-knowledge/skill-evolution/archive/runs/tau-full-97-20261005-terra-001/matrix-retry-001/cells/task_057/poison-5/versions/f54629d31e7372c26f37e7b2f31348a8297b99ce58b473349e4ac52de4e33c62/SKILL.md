---
name: personal-checking-account-fit-and-opening
description: Recommend a documented personal checking account based on no-overdraft-fee, overdraft-protection, and early-direct-deposit needs, then safely verify eligibility and open the selected account when all required information and banking-tool prerequisites are available.
---

# Personal Checking Account Fit and Opening

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For an account-opening request, apply the relevant portions before acting: identity, authority to open the requested account, ownership of any account proposed for overdraft protection, product eligibility, disclosed fees and limits, and explicit confirmation of the account class. Do not claim a prerequisite is verified when it is unavailable or not applicable.

## Use cases

Use this Skill when a customer wants an additional personal checking account, wants a recommendation among documented checking products, or wants an account that combines no account overdraft fee, optional linked-account overdraft protection, and early direct deposit.

Do not use this Skill to enroll overdraft protection by itself, transfer money, or modify a profile. Those actions require their own applicable workflows and confirmations.

## Product recommendation method

1. Translate the customer’s stated needs into explicit requirements. Keep separate:
   - the checking account’s ordinary overdraft fee;
   - the optional overdraft-protection transfer fee; and
   - early-direct-deposit timing, which depends on the payer transmitting funds early.
2. Use only product features documented in the supplied knowledge. Do not infer that a product supports a feature merely because it has a $0 overdraft fee.
3. A documented fit for all of these requirements is **Blue Account**:
   - its account overdraft fee is $0.00;
   - optional overdraft protection can transfer funds from a linked eligible account for $12.50 per protection-triggered transfer; and
   - early direct deposit is available 1 day before payday when the payer sends the deposit early.
   Its $20 monthly maintenance fee can be waived by maintaining a $625 minimum daily balance. Disclose this separately; it is not an overdraft fee.
4. State clearly that protection is optional, requires an eligible linked funding account, and can cost $12.50 each time it triggers. Do not describe it as free overdraft coverage or promise a deposit date.
5. A recommendation is not account-class confirmation. Ask the customer to explicitly confirm the exact official account class, for example: “Would you like to open a Blue Account?”

For a reusable structured comparison, run `scripts/match_products.py` with current, documented product records. The script excludes products with unknown required features rather than guessing.

## Recommended customer response for this fact pattern

When the customer has expressed all three needs but has not yet confirmed an account class, explain that Blue Account meets the documented requirements: no account overdraft fee, optional linked-account protection at $12.50 per transfer, and direct deposit up to 1 day early when the payer submits funds early. Mention the monthly fee and waiver threshold. Ask whether they want to proceed with the exact class **Blue Account** and request the email address on their bank profile for the identity and eligibility process.

Do not open an account from the customer’s interest in a recommendation alone.

## Identity, authority, and eligibility workflow

Perform the following in order after the customer asks to proceed.

1. **Locate the profile.** Obtain the email address on the customer’s bank profile and call `get_user_information_by_email`. If it does not yield one unambiguous profile, stop and request corrected identifying information. Do not change the profile email as part of this workflow.
2. **Verify identity.** Ask the customer to confirm enough profile information to match at least two of: date of birth, email, phone number, and address. Compare the provided values to the retrieved profile; do not expose unconfirmed full profile values. A profile lookup is not, by itself, successful identity verification.
3. **Create the verification record.** Once two fields match, get the current timestamp using `get_current_time`, then call `log_verification` with the retrieved profile fields and that timestamp. The logging tool requires all profile fields even though the verification standard is two matched fields. If a supplied field mismatches, do not log verification or continue to opening.
4. **Confirm authority and selection.** Confirm that the verified customer is requesting the opening and explicitly confirms the exact official personal checking `account_class`. Retain the official product name exactly; do not abbreviate, invent, or substitute a near match.
5. **Retrieve accounts.** Unlock `get_all_user_accounts_by_user_id_3847` and call it with the verified `user_id`. Confirm returned accounts belong to the verified profile. Review account type, class, status, balance, and date opened as returned.
6. **Check opening eligibility.** Before opening, establish all of the following:
   - verified customer;
   - age 18 or older, calculated from the verified date of birth at the current date;
   - the customer currently has fewer than four personal checking accounts, so the new account will not make the total exceed four; and
   - no checking account was closed for cause during the preceding six months.

   The account-list response may not expose closure cause or enough historical information to establish the final condition. Never treat an absent closure record as proof. If a required eligibility fact is unavailable, do not open the account; obtain it through an approved documented source or explain that eligibility cannot yet be completed.
7. **Optional protection discussion.** If the customer wants overdraft protection after opening, identify the particular linked funding account, confirm that it is eligible and belongs to the customer, disclose the $12.50 per-transfer charge, and obtain explicit acceptance. Do not enroll it merely because the customer asked for a checking account.
8. **Open only when ready.** Unlock `open_bank_account_4821` and use the runtime-exposed signature only after every check above passes and the customer has confirmed the exact class. The supplied knowledge names this tool but does not provide its parameter schema; inspect the runtime-exposed requirements and do not invent arguments. Report the actual resulting account details only after a successful tool result.

Use `scripts/validate_opening.py` to record a deterministic readiness assessment before the opening call. It is a guardrail, not a substitute for profile retrieval, identity comparison, account retrieval, closure-history verification, or the banking tools.

## Failure and stop conditions

- Missing email, ambiguous profile, mismatched identity field, or fewer than two confirmed identity fields: request the missing/correct information; do not log verification or open an account.
- Customer is under 18, has four or more current personal checking accounts, or has a qualifying closure for cause: explain that the account cannot be opened under the stated eligibility requirements.
- Closure-cause history unavailable: explain that eligibility remains incomplete; do not assume a pass.
- Account class not explicitly confirmed or not an official personal checking class: ask for a valid exact class.
- Tool failure or unavailable opening-tool schema: do not retry blindly, fabricate completion, or claim an account was opened.

## Script interfaces and validation

### `scripts/match_products.py`

Input JSON:

```json
{
  "needs": {
    "no_overdraft_fee": true,
    "overdraft_protection": true,
    "minimum_early_direct_deposit_days": 1
  },
  "products": [
    {
      "account_class": "Official class name",
      "ordinary_overdraft_fee": "0.00",
      "supports_overdraft_protection": true,
      "overdraft_protection_transfer_fee": "12.50",
      "early_direct_deposit_days": 1,
      "evidence_complete": true
    }
  ]
}
```

Output JSON contains `matching_products`, `recommended_account_class`, and `excluded` reasons. Validate that every recommended product has complete documented evidence for every requested feature. Unknown or malformed product fields are excluded.

### `scripts/validate_opening.py`

Input JSON includes a current eligibility record: `identity_verified`, `customer_authorized`, `age_years`, `existing_personal_checking_count`, `closure_for_cause_last_6_months`, `closure_history_verified`, `account_class_confirmed`, and `official_personal_checking_class`.

Output JSON contains `ready_to_open`, `checks`, and `blocking_reasons`. Validate that `ready_to_open` is true only if every required item is known and passes. In particular, an existing count of four fails because opening another account would exceed the maximum.
