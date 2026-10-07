---
name: personal-checking-account-opening
description: Assist a verified customer with comparing supported personal checking products and, after all eligibility, identity, disclosure, and confirmation prerequisites are satisfied, open a selected checking account using the bank's normal discoverable tools.
---

# Personal Checking Account Opening

Use this Skill when a customer wants to compare or open a personal checking account. It supports recommendation and prerequisite tracking; it does not itself create an account or substitute for banking-tool results.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Product guidance

1. Establish the customer's requirements before recommending a product. For overdraft-related requests, distinguish an account overdraft fee from a linked-account overdraft-protection transfer fee.
2. Use `scripts/checking_workflow.py` with `operation: "recommend"` to compare the packaged product facts to stated requirements. The script only ranks products whose documented facts meet every requested boolean or minimum requirement.
3. Explain only documented product facts and material tradeoffs. Do not characterize an overdraft-protection transfer as free unless the selected product's documented transfer fee is $0.
4. For a customer who requires all three of (a) no account overdraft fee, (b) automatic linked-account protection, and (c) direct deposit at least one day early, Blue Account is the supported match in the packaged catalog. Its documented protection transfer fee is $12.50 per transfer. Light Blue Account has $0 account and transfer fees but no early-direct-deposit advance.
5. Ask the customer to select the exact official `account_class` before opening. A recommendation, a question about product features, or an expression of preference is not selection/authorization to open.

## Required opening workflow

Do these steps in order. If a prerequisite is absent, uncertain, or fails, do not open the account.

1. **Identify and verify the customer.** Obtain a profile identifier through the normal lookup tools. A name lookup or bank-held profile data alone is not identity verification. Ask the customer to provide any two of the four verification fields (date of birth, email, phone number, address), compare them to the profile, then obtain the current timestamp and call `log_verification` with the complete matching profile fields and timestamp. Do not expose undisclosed profile values while prompting or comparing.
2. **Confirm authority and intent.** Confirm that the authenticated customer is opening an account for themself and obtain explicit authorization to open the selected account.
3. **Retrieve account information.** Unlock and call `get_all_user_accounts_by_user_id_3847` with the authenticated `user_id`. Retain the returned account type, class, status, balance, and opening date for the eligibility review. Do not treat the customer's statement about an old account as a substitute for this lookup.
4. **Check all eligibility requirements.** Confirm:
   - the customer is verified;
   - the customer is at least 18 years old;
   - the customer has fewer than four existing personal checking accounts, so opening another will not exceed the four-account limit; and
   - there have been no checking accounts closed for cause during the prior six months.

   The account lookup may not expose closure cause/history. Obtain this from an authorized bank source if available. Missing closure-for-cause information is a pending prerequisite, not a pass. Use `operation: "eligibility"` in the helper to make the deterministic age, count, and six-month checks after normalizing tool data.
5. **Confirm product eligibility and disclosures.** Reconfirm the exact official product name, no-overdraft/overdraft-protection behavior, all material fees requested by the customer, and applicable balance, limit, and cutoff facts. For a linked protection source, verify that the source account is eligible, owned/authorized by the customer, active, and has sufficient available balance; confirm the customer accepts the per-transfer fee before enabling or arranging protection. Do not assume that opening a checking account automatically links protection.
6. **Open only after confirmation.** Unlock `open_bank_account_4821`, then call it with the authenticated customer's `user_id`, `account_type: "checking"`, and the customer-confirmed exact official `account_class`. Do not call it until steps 1–5 pass.
7. **Report completion.** State the account details returned by the bank tool, the selected product's relevant fees/features, and whether overdraft protection is merely available or has actually been separately enabled. If the tool fails, report that no completion is confirmed and do not claim an account was opened.

## Current-conversation handling

When the latest customer message is a product question rather than a confirmed selection, answer that question first and do not begin an account-opening action. For the supplied scenario, explain that Blue Account supports early direct deposit up to one day early, charges no account overdraft fee, and can use an eligible linked account for automatic protection at $12.50 per transfer. Then request an explicit choice of Blue Account (or another account) and complete identity verification and eligibility checks before any opening action.

## Tool-use boundaries and failures

- Use only normal banking tools for identity lookup/logging, account lookup, and account creation. Scripts in this package are advisory validation only and never initiate bank actions.
- Unlock discoverable bank tools before calling them. Use the exact tool parameters documented above.
- If identity verification fails, the customer is under 18, the count limit would be exceeded, a recent for-cause closure exists, selection/authorization is missing, or a needed fact cannot be verified, stop the opening flow and explain the blocking prerequisite.
- If the customer only wants information, provide it without logging verification or performing any banking action.
- Do not make claims about an account's availability, linked-account eligibility, or a completed protection enrollment without the relevant tool result.

## Helper interface

Run `scripts/checking_workflow.py` by sending one JSON object on stdin. It emits one JSON object on stdout and does not access banking systems.

Supported inputs:

- `{"operation":"catalog"}` returns the packaged product catalog.
- `{"operation":"recommend","requirements":{...}}` accepts optional keys: `no_overdraft_fee` (boolean), `automatic_overdraft_protection` (boolean), `min_early_direct_deposit_days` (number), `max_monthly_fee` (number), and `max_protection_transfer_fee` (number). It returns matching products, ordered by lower monthly fee and then lower protection-transfer fee.
- `{"operation":"eligibility","verified":true|false,"date_of_birth":"MM/DD/YYYY or YYYY-MM-DD","as_of":"YYYY-MM-DD or timestamp","accounts":[...],"closures_checked":true|false,"closures":[...]}` evaluates only the documented eligibility tests. Account records use `account_type` and `status`; closure records use `closed_at` and `cause`/`closed_for_cause`.

A runnable catalog call is `run_skill_script` with `relative_path` set to `scripts/checking_workflow.py` and `input_json` set to `{"operation":"catalog"}`.

Validate helper output before relying on it: require `ok: true`; for recommendations, ensure `matches` is nonempty; for eligibility, require `action_allowed: true` and no entries in `pending`. Bank-tool results and explicit customer confirmation remain required even when helper validation passes.
