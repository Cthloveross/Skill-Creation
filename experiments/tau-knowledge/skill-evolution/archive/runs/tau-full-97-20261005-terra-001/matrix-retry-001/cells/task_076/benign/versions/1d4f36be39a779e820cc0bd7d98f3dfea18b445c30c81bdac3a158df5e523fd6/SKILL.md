---
name: open-personal-checking-account
description: Complete a personal checking account opening request after product selection, including identity verification, documented eligibility checks, account lookup, and the bank-account opening action. Use when a customer wants a new personal checking account or when an earlier conversation stopped before the account was opened.
---

# Open a Personal Checking Account

Use this Skill only for a **personal checking** opening. It does not apply the distinct personal-savings, business-checking, or business-savings requirements.

## Required inputs and evidence

Collect or reuse, from the current conversation and tool results:

- A reliably identified customer and `user_id`.
- The customer's selected personal checking `account_class` in its exact official form. It must end in `Account`.
- Identity-verification evidence: at least two customer-supplied profile fields that match the authoritative profile among date of birth, email, phone number, and address.
- Current time for the verification audit record.
- A current complete bank-account lookup for the customer.
- A determination that the customer has no checking account closed for cause in the preceding six months. Use an available system/history result where it exists; otherwise an explicit customer confirmation can support this item. Do not claim that a generic account-status response reveals a closure cause when it does not.

Prior clarifications in the same customer interaction remain usable when they unambiguously supply these facts. Do not ask again for information that is already present and matched.

## Procedure

1. **Confirm the product choice.** If multiple accounts are being compared for travel, distinguish bank foreign-ATM fees from third-party ATM operator fees. Consider documented foreign ATM fees, rebates, direct-deposit timing, and any disclosed balance or opening-deposit prerequisites. Once the customer selects an account, retain their exact official account-class string; do not silently substitute another product.

2. **Identify the customer and verify identity.** Look up the customer profile using a customer-provided identifier. Compare the customer's stated fields with that profile. If at least two of the four supported fields match, obtain the current timestamp and call `log_verification` with the complete authoritative profile values and timestamp. A statement that the customer was not previously verified does not itself prevent a new verification; it means this authentication and audit step must be completed now.

   Do not log verification if fewer than two customer-provided fields match, if the profile lookup is ambiguous, or if supplied values conflict with the profile. Request the missing verification information instead.

3. **Retrieve current accounts before opening.** Unlock and call the documented agent tool `get_all_user_accounts_by_user_id_3847` with the authenticated `user_id`. Do not rely solely on the customer's account-count statement when the account lookup is available. Normalize its response for the eligibility helper if useful.

4. **Evaluate all personal-checking eligibility conditions.** The customer must be:
   - identity-verified;
   - at least 18 on the current date;
   - below four currently held personal checking accounts, so the new account will not take the customer above the four-account maximum; and
   - free of any checking account closure for cause in the last six months.

   Use `scripts/evaluate_personal_checking_eligibility.py` for deterministic age, count, and input-completeness checks. The helper is advisory only: the execution agent must still inspect the current tool results and resolve classification ambiguity. In particular, do not count business checking accounts as personal checking accounts, and do not guess whether an unclear record is personal.

5. **Open only after every requirement passes.** Unlock `open_bank_account_4821`, then call it with:
   - `user_id`: the authenticated customer's identifier;
   - `account_type`: `checking`;
   - `account_class`: the exact confirmed official personal checking account name.

   The tool must be called by the agent, not handed to the customer. Do not open an account with a shortened product name or a name that does not end in `Account`.

6. **Report the outcome accurately.** On success, give the customer the new account details returned by the opening tool and any relevant already-disclosed product terms. On a failed verification, failed eligibility check, unavailable required fact, or failed opening tool call, do not state that the account was opened. Explain the specific unresolved requirement or operational failure and the appropriate next step.

## Runtime tool sequence

The normal sequence is:

1. Profile lookup (`get_user_information_by_email`, `get_user_information_by_name`, or `get_user_information_by_id`) when needed.
2. `get_current_time`, then `log_verification` after two matching customer-provided fields have been confirmed.
3. `unlock_discoverable_agent_tool` for `get_all_user_accounts_by_user_id_3847`, followed by `call_discoverable_agent_tool` with the customer `user_id`.
4. Assess eligibility, optionally using the helper.
5. `unlock_discoverable_agent_tool` for `open_bank_account_4821`, followed by `call_discoverable_agent_tool` with the authenticated `user_id`, `checking`, and the selected account class.

If a needed tool was already successfully called in the current interaction and its result is current and complete, reuse that result rather than repeating it. Never fabricate a tool result, account classification, verification record, or successful opening.

## Eligibility helper

`scripts/evaluate_personal_checking_eligibility.py` reads one JSON object from standard input and emits one JSON object to standard output. It does not call bank tools or expose customer data.

Input schema:

- `current_date` (required): ISO date (`YYYY-MM-DD`) used for age calculation.
- `date_of_birth` (required): `YYYY-MM-DD` or `MM/DD/YYYY`.
- `identity_verified` (required): `true` only after successful identity verification and audit logging.
- `closure_for_cause_in_last_6_months` (required): boolean, where `false` is a confirmed pass and `true` is a failure.
- `accounts_complete` (required): whether the supplied account list is a complete current lookup.
- `accounts` (required): array of normalized account records. Each record must contain `counts_toward_personal_checking_limit` as a boolean. Set it to `true` only for a currently held personal checking account; set it to `false` for savings, business accounts, closed/non-held accounts, and records that policy confirms do not count.
- `account_class` (required): selected exact account name.
- `official_account_classes` (optional): approved names available for this case. When provided, the selected class must be in this list.

Output schema:

- `eligible`: `true` when all supplied checks pass, `false` when any fail, or `null` for malformed/insufficient inputs.
- `age_years`, `personal_checking_count`, and `new_total_personal_checking_count`: calculated values when available.
- `checks`: individual pass/fail values.
- `blocking_reasons`: actionable failures.
- `next_action`: either `open_account` or `do_not_open`.

Before acting on an `open_account` recommendation, verify that the normalized account records truly came from the current lookup, the verification audit call succeeded, and the class is an official personal checking class. A meaningful validation is that `eligible` is `true`, `next_action` is `open_account`, no blocking reasons are returned, and the computed new total is no greater than four.
