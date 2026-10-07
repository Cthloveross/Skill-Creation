---
name: open-personal-checking-account
description: Assist with selecting and opening a personal checking account. Use for a customer seeking a new personal checking account, including travel-fee comparisons, identity verification, eligibility review, existing-account lookup, and the authorized opening workflow.
---

# Open a Personal Checking Account

Use this Skill only for **personal checking** openings. Do not apply the different rules for personal savings, business checking, or business savings.

## Required facts before opening

Obtain or reuse current, reliable evidence for all of the following:

- An identified customer and authenticated `user_id`.
- The exact customer-confirmed personal checking `account_class`. It must be the official full name ending in `Account`.
- Successful identity verification: at least two customer-supplied identity fields match the authoritative customer profile, followed by a successful `log_verification` audit record.
- The current date/time needed to calculate age and create the verification audit record.
- A complete current bank-account lookup for the customer.
- Confirmation that the customer is at least 18, will remain within the maximum of four personal checking accounts after opening, and has no checking account closed for cause within the last six months.

Reuse unambiguous clarifications and successful tool results from the current interaction. Do not make the customer repeat a confirmed selection or profile field.

## Product-selection response

Answer the customer’s stated product need using the supplied product documentation; never say that documented terms are unavailable when they are present.

For an international-ATM and early-direct-deposit comparison, distinguish:

- the bank's own foreign-ATM withdrawal fee;
- third-party ATM operator fees, which may still be charged;
- the monthly cap on any operator-fee rebates; and
- early-direct-deposit availability and material account prerequisites.

For example, where the documented comparison is between Bluest and Purple, both have a $0 bank foreign-ATM withdrawal fee and up to two days of early direct deposit. Bluest has up to $50 in monthly ATM-fee rebates, but requires a $75,000 opening deposit and a $112,500 daily balance to retain benefits. Purple has up to $30 in monthly ATM-operator-fee rebates; it also has a $15 monthly maintenance fee that is waived with a $3,750 minimum daily balance. If the customer cannot meet Bluest's requirements and selects **Purple Account**, acknowledge that exact choice and proceed with **Purple Account** rather than asking them to select an account again.

Do not promise that an operator surcharge will be eliminated: describe the applicable rebate cap accurately.

## Required workflow

1. **Identify the customer.** Use a customer-provided profile identifier with the appropriate profile lookup, unless a successful, unambiguous lookup is already available. Retain the authoritative `user_id` and profile values.

2. **Verify identity before opening.** Compare customer-supplied profile facts with the authoritative profile. The supported matching facts are date of birth, email, phone number, and street address. When at least two supplied facts match and no supplied fact conflicts, obtain the current timestamp if a current successful timestamp is not already available, then call `log_verification` using the complete authoritative profile and timestamp.

   A customer saying that they were not *previously* identity-verified is not a reason to skip this step or to open immediately. It means the new verification and audit record must succeed before continuing. If fewer than two facts match, the lookup is ambiguous, a fact conflicts, or `log_verification` fails, do not open the account; request or resolve the necessary information.

3. **Retrieve existing accounts before any opening call.** Unlock `get_all_user_accounts_by_user_id_3847`, then call it for the authenticated `user_id`. This lookup is mandatory for the personal-checking eligibility review. Do not substitute a customer assertion for a current account lookup.

4. **Evaluate every eligibility condition.** Confirm:
   - identity verification was successfully logged;
   - the customer is at least 18 on the current date;
   - current held personal checking accounts plus the proposed account will not exceed four; and
   - there was no checking closure for cause in the prior six months.

   Count only currently held personal checking accounts. Do not count savings or business checking accounts. The account lookup may establish account types and current status, but do not falsely claim it establishes a closure *cause* if that information is absent. Use a documented history result when available; otherwise, an explicit unambiguous customer confirmation in the current interaction can support the closure-for-cause condition.

   Use `scripts/evaluate_personal_checking_eligibility.py` for consistent date, count, and completeness evaluation when helpful. It is advisory: the execution agent must verify that the normalized records faithfully reflect the current lookup and that the verification audit call succeeded.

5. **Open only after all checks pass.** Unlock `open_bank_account_4821` and call it only after steps 1–4 have passed. The agent, not the customer, performs the action. Use:
   - `user_id`: the authenticated customer's ID;
   - `account_type`: `checking`;
   - `account_class`: the exact confirmed official class, including `Account`.

   Never silently substitute a different product, shorten its name, or open before the existing-account lookup. If a customer has selected Purple Account, the opening class must be exactly `Purple Account`.

6. **Give an accurate outcome.** On a successful opening, report only the account details returned by the opening tool and the applicable product terms already documented. If verification, eligibility, lookup, or the opening tool fails or is unavailable, do not claim success; explain the unresolved requirement and the appropriate next step.

## Runtime tool sequence

Use the normal bank-agent tool flow:

1. Profile lookup (`get_user_information_by_email`, `get_user_information_by_name`, or `get_user_information_by_id`) if needed.
2. `get_current_time` if no current timestamp was already obtained, then `log_verification` after two or more profile fields have been matched.
3. `unlock_discoverable_agent_tool` for `get_all_user_accounts_by_user_id_3847`, then `call_discoverable_agent_tool` with the authenticated `user_id`.
4. Evaluate eligibility.
5. Only if eligible, unlock and call `open_bank_account_4821` with the required checking arguments.

Never fabricate a profile match, verification record, account lookup, closure determination, eligibility result, or successful account opening.

## Eligibility helper

`scripts/evaluate_personal_checking_eligibility.py` reads one JSON object from standard input and writes one JSON object to standard output. It does not call bank tools and does not open an account.

### Input schema

- `current_date` (required): ISO `YYYY-MM-DD` date used for age calculation.
- `date_of_birth` (required): `YYYY-MM-DD` or `MM/DD/YYYY`.
- `identity_verified` (required): boolean; set `true` only after `log_verification` succeeds.
- `closure_for_cause_in_last_6_months` (required): boolean; `false` means the condition passes.
- `accounts_complete` (required): boolean indicating that `accounts` came from a complete current lookup.
- `accounts` (required): array of normalized records. Every record needs boolean `counts_toward_personal_checking_limit`; set it `true` only for a currently held personal checking account.
- `account_class` (required): exact selected account class.
- `official_account_classes` (optional): approved account-class strings. If supplied, the selected class must be in it.

### Output schema and validation

The result contains `eligible`, `next_action`, calculated `age_years` and account counts when valid, individual `checks`, and `blocking_reasons`. Treat `eligible: true`, `next_action: "open_account"`, no blocking reasons, and `new_total_personal_checking_count` no greater than four as necessary—but not sufficient—conditions for opening. Also verify that the audit record and source lookup actually succeeded.

Runnable example (with values supplied at runtime rather than hardcoded customer data):

```sh
python3 scripts/evaluate_personal_checking_eligibility.py <<'JSON'
{"current_date":"2025-01-01","date_of_birth":"1990-01-01","identity_verified":true,"closure_for_cause_in_last_6_months":false,"accounts_complete":true,"accounts":[],"account_class":"Example Account"}
JSON
```

The example emits JSON with `eligible`, `checks`, and `next_action`; replace every illustrative value with current interaction evidence before relying on it.
