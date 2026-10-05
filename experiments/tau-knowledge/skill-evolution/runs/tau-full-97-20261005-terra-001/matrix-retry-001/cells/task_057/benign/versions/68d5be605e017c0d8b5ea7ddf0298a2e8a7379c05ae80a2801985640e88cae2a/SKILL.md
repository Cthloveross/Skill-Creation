---
name: personal-checking-opening
description: Recommend and open a personal checking account only after identity verification, eligibility review, a confirmed official account class, and customer authorization.
---

# Personal Checking Opening

Use this Skill when a customer wants to open a personal checking account, including when they need help selecting an account before opening one.

## Required order and guardrails

1. **Identify the customer, but do not treat lookup as verification.** Resolve the profile with a user lookup when needed.
2. **Verify identity before opening.** Ask the customer to provide any two of these profile fields: date of birth, email, phone number, or street address. Compare their answers to the retrieved profile without revealing profile values as prompts. Once two fields match, get the current time and call `log_verification` with the complete retrieved profile and that timestamp.
3. **Help choose an account without opening one.** Explain only product facts supported by the account documentation. If the customer needs all of the following—no account overdraft fee, optional automatic linked-account protection for a per-transfer fee, and direct deposit up to one day early—Blue Account is the documented match. Explain that protection transfers are optional, require an eligible linked funding account, and cost $12.50 per transfer; early posting depends on the payer sending funds early. Ask plainly: “Would you like to open a Blue Account?”
4. **Obtain an affirmative selection of the exact official account class.** Preserve the official selected class exactly (for example, `Blue Account` or `Green Account (checking)`). An affirmative response to an immediately preceding question that specifically names the full official class is sufficient authorization; the customer need not repeat the class verbatim. For example, “That sounds perfect—let’s do it” confirms the named `Blue Account`. Do not infer consent from a feature question, a request for information, or a recommendation that has not yet been accepted. The selection must be an official personal checking class, not a shortened or modified name.
5. **Check eligibility before calling the opening tool.** Unlock and call `get_all_user_accounts_by_user_id_3847` using the resolved runtime `user_id`. Establish each documented condition:
   - identity is verified;
   - customer is at least 18;
   - customer does not exceed four personal checking accounts;
   - customer has no personal checking account closed for cause during the six months before the current date.

   Account lookup data includes account type, class, status, balance, and opening date and can include additional history. Do not assume that missing closure-cause or closure-date data proves eligibility. If a closed personal checking record cannot be evaluated for cause and date, obtain the required information through the supported workflow or explain that opening cannot proceed until eligibility can be confirmed.
6. **Open only after all prerequisites and authorization are established.** Unlock `open_bank_account_4821`, then call it with the customer's runtime `user_id`, account type `checking`, and the exact confirmed `account_class`. Report the returned account record or a tool failure accurately. Do not call the tool merely to obtain a quote, recommendation, or tentative selection.
7. **Discuss post-opening services separately.** Opening Blue Account does not enroll overdraft protection or establish direct deposit. After a successful opening, explain the documented customer settings flow for optional overdraft protection and the payer enrollment process for direct deposit. Do not claim that an eligible funding account exists until it has been confirmed.

## Handling the conversation state

When the customer has expressed product requirements but has not accepted a specifically named official account class, give a concise recommendation and request a decision; do not perform an account opening. In particular, a request for at least one day of early direct deposit is a feature requirement, not authorization to open an account.

When the customer affirmatively accepts a specifically named official class, record that class as their selection and proceed with the remaining prerequisites. Avoid a redundant confirmation prompt solely because the acceptance did not repeat the account name.

If the customer rejects the recommendation, wants an unsupported feature, does not confirm identity, cannot meet eligibility, or does not select an exact class, stop the opening workflow and explain the applicable blocker. Never bypass verification or eligibility because a customer has an existing account.

## Eligibility helper

Use `scripts/assess_personal_checking.py` after normalizing the account-lookup response and collecting the current time. It is a deterministic review aid only; it does not verify identity, retrieve accounts, unlock tools, or open an account.

### Input schema

The script accepts one JSON object on stdin:

- `identity_verified` (boolean): true only after two customer-provided fields were matched and `log_verification` was recorded.
- `as_of` (string): current date/time from the supported time tool, in ISO-like or `MM/DD/YYYY` form.
- `accounts` (array): normalized account objects. For each personal checking record, set `is_personal_checking: true`. Include `closed_for_cause` when known, and, for a for-cause closure, `closed_date` or `date_closed`.
- `desired_account_class` (string): exact class the customer affirmatively selected.
- `account_class_confirmed_exact` (boolean): true after the agent has confirmed the selection is an official full class, including when the customer affirmatively accepted an immediately preceding prompt naming that class.
- Optional `official_account_classes` (array of strings): when an authoritative runtime list is available, the selected class must exactly equal one entry.

A checking record can be excluded from the personal-checking count by setting `is_personal_checking: false`, such as for a business checking record. Do not silently classify an ambiguous record as personal; resolve the classification before relying on the assessment.

### Output schema

The script writes one JSON object containing:

- `decision`: `eligible`, `ineligible`, or `incomplete`;
- `failures`: established eligibility failures;
- `unknowns`: missing or unusable facts that prevent a positive determination;
- `personal_checking_count` and the normalized selection result;
- `six_month_lookback_start` when `as_of` is parseable.

A runnable call through the packaged runtime is `run_skill_script` with `relative_path` set to `scripts/assess_personal_checking.py` and an input object matching the schema above. Only an `eligible` result supports proceeding, and the executor must still ensure the user affirmatively accepted that exact official account class before the banking action.

## Validation before the banking action

Confirm all of the following in the agent's working record: a matched two-field verification and audit log, a resolved runtime `user_id`, current account lookup result, no unresolved closure-history question, the eligibility helper's `eligible` result (or an equivalent documented review), and affirmative selection of the exact official checking class. The opening tool arguments must use only runtime values. Never hardcode a customer identifier, a previously observed account, or a selection from another interaction.

## Validation after a successful Blue Account opening

State that the account overdraft fee is $0.00. Clearly distinguish this from optional overdraft protection: it is **not enrolled automatically**, requires selecting an eligible linked funding account and accepting the $12.50 per-transfer disclosure. Explain that the customer can obtain account and routing numbers from banking profile and provide them to their employer or payer; early arrival is up to one day early and depends on when the payer transmits the deposit.

See `references/personal_checking_policy.md` for source-backed product and procedure facts.
