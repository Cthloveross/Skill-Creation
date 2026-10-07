---
name: checking-account-guidance-and-opening
description: Guide a customer choosing and opening an additional personal checking account. Use when the customer has account-feature requirements, needs a product recommendation, or wants a personal checking account opened through the authorized banking workflow.
---

# Checking Account Guidance and Opening

## Scope and safety

Use this Skill for personal checking-account recommendations and account-opening requests. Treat product documents and the live tool responses as the source of truth. Do not open an account merely because the customer asked for general advice: obtain an explicit selection of an exact official `account_class` first.

Do not claim that identity verification or eligibility is complete until it has been checked. Do not disclose profile values as verification prompts; ask the customer to provide the values and compare them with the profile record.

## Recommendation workflow

1. Identify the customer using information they supplied (normally full name or email). If the lookup is ambiguous or absent, request an identifier rather than guessing.
2. Extract the customer's non-negotiable needs separately from preferences. Compare only documented features.
3. Explain the recommendation briefly, including material tradeoffs. For a customer whose non-negotiable requirement is no overdraft fees, the documented choices relevant here are:
   - **Light Green Account**: $0 overdraft fee and $0 monthly maintenance fee.
   - **Green Fee-Free Account**: $0 overdraft fee, but a $22.50 monthly maintenance fee applies unless the customer maintains the documented $150 minimum daily balance waiver condition.
4. If the customer only asks which account is suitable, recommend the best documented match and ask them to explicitly choose before proceeding. Do not represent advice as an opened account.
5. Ask for the exact official account name ending in `Account` and confirmation that the customer wants it opened. If a nickname, truncated product name, or an option not ending in `Account` is provided, request the full official name rather than normalizing or guessing.

For the no-overdraft-fee requirement above, a concise response should recommend Light Green Account because it meets the requirement without a monthly maintenance fee, note the Green Fee-Free Account tradeoff, and ask whether the customer wants to proceed with **Light Green Account**.

## Verification and eligibility before opening

After the customer explicitly selects an account, complete every applicable precondition below before an opening action.

1. Resolve the customer to one profile record using `get_user_information_by_name`, `get_user_information_by_email`, or `get_user_information_by_id`.
2. Verify identity by asking the customer to supply and match at least **two of these four** profile fields: date of birth, email, phone number, and address. Do not count the name alone. If fewer than two fields match, do not open the account.
3. Obtain the current timestamp with `get_current_time`, then call `log_verification` with the matched profile record's complete required fields and that timestamp. Log only after successful comparison of at least two customer-supplied fields.
4. Check personal-checking eligibility: the customer must be verified, at least 18, hold no more than four personal checking accounts, and have no checking account closed for cause in the prior six months. Use the authorized opening workflow's eligibility results where the environment provides these checks; if a required condition cannot be determined, explain that opening cannot yet be completed and obtain the needed information or use the authorized tool's check. Never infer account count or closure history from the age of an existing account.
5. Confirm again that the selected `account_class` is the exact official full name ending in `Account`.

Use `scripts/check_opening_prerequisites.py` to consistently evaluate known eligibility inputs. It is a local decision aid only; it does not query profiles, verify values, create audit records, or open accounts.

## Authorized opening action

Only after selection, verification logging, and eligibility checks succeed:

1. Unlock the documented authorized agent tool with `unlock_discoverable_agent_tool` using `open_bank_account_4821`.
2. Invoke it through `call_discoverable_agent_tool`. Supply the resolved customer identifier and exact selected account class, plus any other fields shown by the tool's exposed schema. Do not invent argument names or values; inspect and follow the unlocked tool interface.
3. Report the actual result returned by the authorized tool. If it declines, fails eligibility, or reports a technical error, do not claim the account was opened and do not retry an uncertain state-changing call blindly.

If the customer has not yet made an explicit selection or has not completed verification, stop after asking the targeted follow-up question; no bank action is appropriate.

## Local helper

Run the helper by sending one JSON object on stdin:

```json
{
  "account_class": "Example Account",
  "identity_verified": true,
  "age_years": 30,
  "personal_checking_account_count": 1,
  "closed_for_cause_past_6_months": false
}
```

It emits JSON with `ready_to_open`, `blockers`, and normalized input values. A `ready_to_open: true` result is necessary but not sufficient: the executor must still have logged verification and must use the authorized banking tool. Missing or unknown values are blockers, not favorable assumptions.
