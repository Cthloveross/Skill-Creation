---
name: personal-checking-opening
summary: Safely recommend and open a personal checking account after identity verification, eligibility review, exact account-class confirmation, and explicit customer authorization.
---

# Personal Checking Opening

Use this Skill when a customer wants to open a personal checking account, including when they need help selecting an account before opening one.

## Required order and guardrails

1. **Identify the customer, but do not treat lookup as verification.** Resolve the profile with a user lookup when needed.
2. **Verify identity before opening.** Ask the customer to confirm any two of the four profile fields: date of birth, email, phone number, and street address. Compare their answers to the retrieved profile. Once two fields match, get the current time and call `log_verification` with the complete retrieved profile and that timestamp. Do not reveal unprompted profile values as verification prompts.
3. **Help choose an account without opening one.** Explain only product facts supported by the account documentation. If the customer needs all of the following—no account overdraft fee, optional automatic linked-account protection for a per-transfer fee, and direct deposit up to one day early—Blue Account is the documented match. Explain that protection transfers are optional, require an eligible linked funding account, and cost $12.50 per transfer; early posting depends on the payer sending funds early. Ask for an explicit selection, such as: “Would you like to open a Blue Account?”
4. **Obtain an exact, affirmative account-class selection.** Do not infer consent from questions about features or recommendations. Preserve the official selected class exactly (for example, `Blue Account` or `Green Account (checking)`). The selection must be an official personal checking class, not a shortened or modified name.
5. **Check eligibility before calling the opening tool.** Unlock and call `get_all_user_accounts_by_user_id_3847` using the resolved `user_id`. Establish each documented condition:
   - identity is verified;
   - customer is at least 18;
   - customer does not exceed four personal checking accounts;
   - customer has no personal checking account closed for cause during the six months before the current date.

   Account lookup data includes account type, class, status, balance, and opening date and can include additional history. Do not assume that missing closure-cause or closure-date data proves eligibility. If a closed personal checking record cannot be evaluated for cause and date, obtain the required information through the supported workflow or explain that opening cannot proceed until eligibility can be confirmed.
6. **Open only after all prerequisites and explicit selection are established.** Unlock `open_bank_account_4821`, then call it with the customer's runtime `user_id`, account type `checking`, and the exact confirmed `account_class`. Report the returned account record or a tool failure accurately. Do not call the tool merely to obtain a quote, recommendation, or tentative selection.
7. **Discuss post-opening services separately.** Opening Blue Account does not itself enroll overdraft protection or establish direct deposit. After a successful opening, explain the documented customer settings flow for optional overdraft protection and the payer enrollment process for direct deposit. Do not claim that an eligible funding account exists until it has been confirmed.

## Handling the current conversation state

When a customer has expressed product requirements but has not yet answered yes to a specific exact class, give a concise recommendation and request a decision; do not perform an account opening. In particular, a request for at least one day of early direct deposit is a feature requirement, not authorization to open an account.

If the customer rejects the recommendation, wants an unsupported feature, does not confirm identity, cannot meet eligibility, or does not select an exact class, stop the opening workflow and explain the applicable blocker. Never bypass verification or eligibility because a customer has an existing account.

## Eligibility helper

Use `scripts/assess_personal_checking.py` after normalizing the account-lookup response and collecting the current time. It is a deterministic review aid only; it does not verify identity, retrieve accounts, unlock tools, or open an account.

### Input schema

The script accepts one JSON object on stdin:

- `identity_verified` (boolean): true only after two customer-provided fields were matched and `log_verification` was recorded.
- `as_of` (string): current date/time from the supported time tool, in ISO-like or `MM/DD/YYYY` form.
- `accounts` (array): normalized account objects. For each personal checking record, set `is_personal_checking: true`. Include `closed_for_cause` when known, and, for a for-cause closure, `closed_date` or `date_closed`.
- `desired_account_class` (string): exact class the customer affirmatively selected.
- `account_class_confirmed_exact` (boolean): true only after the agent has confirmed that the supplied value is the official full class.
- Optional `official_account_classes` (array of strings): when an authoritative runtime list is available, the selected class must exactly equal one entry.

A checking record can be excluded from the personal-checking count by setting `is_personal_checking: false`, such as for a business checking record. Do not silently classify an ambiguous record as personal; resolve the classification before relying on the assessment.

### Output schema

The script writes one JSON object containing:

- `decision`: `eligible`, `ineligible`, or `incomplete`;
- `failures`: established eligibility failures;
- `unknowns`: missing or unusable facts that prevent a positive determination;
- `personal_checking_count` and the normalized selection result;
- `six_month_lookback_start` when `as_of` is parseable.

A runnable call through the packaged runtime is `run_skill_script` with `relative_path` set to `scripts/assess_personal_checking.py` and an input object matching the schema above. Only an `eligible` result supports proceeding, and the executor must still ensure the user explicitly selected that exact account class immediately before the banking action.

## Validation before the banking action

Confirm all of the following in the agent's working record: a matched two-field verification and audit log, a resolved runtime `user_id`, current account lookup result, no unresolved closure-history question, the eligibility helper's `eligible` result (or an equivalent documented review), and explicit affirmative selection of the exact official checking class. The opening tool arguments must use only runtime values. Never hardcode a customer identifier, a previously observed account, or a selection from another interaction.

See `references/personal_checking_policy.md` for source-backed product and procedure facts.
