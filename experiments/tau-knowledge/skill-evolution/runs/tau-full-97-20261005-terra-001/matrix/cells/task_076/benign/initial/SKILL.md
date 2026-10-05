---
name: open-personal-checking-account
description: Verify a customer, assess the documented eligibility requirements, recommend the appropriate documented checking option when travel/ATM access and early direct deposit matter, and open a personal checking account only after all prerequisites and an exact official account class are confirmed.
---

# Open a Personal Checking Account

Use this Skill for a request to open a **personal checking** account. It applies the documented requirement that the customer be verified, at least 18, have capacity under the personal-checking-account limit, and have no checking account closed for cause in the prior six months.

## Safety and completion rule

Do not open an account until every required check is affirmatively established:

1. Identity verification has been completed and logged.
2. The customer is at least 18 as of the current date.
3. The customer has fewer than four personal checking accounts that count toward the four-account limit. Opening another account when already at four would exceed the limit.
4. No checking account was closed for cause during the six months ending today.
5. The customer has selected an exact official `account_class` ending in `Account`.

Do not infer a passed eligibility condition from missing data, unrelated account searches, a failed lookup, or a customer declining to answer. If a needed condition remains unknown, explain that the account cannot yet be opened and ask only for the missing information or perform the appropriate lookup. Do not use the personal-savings or business-savings procedures for this task.

## Procedure

### 1. Establish the customer and verify identity

1. Obtain a user ID, or locate the user using an identifier the customer supplies.
2. Retrieve the customer record with the applicable user-information tool.
3. Have the customer confirm at least two of these four fields against the retrieved record: date of birth, email, phone number, and address. A name alone is not one of the two required fields.
4. Get the current time with `get_current_time`.
5. After two fields match, call `log_verification` with the complete retrieved user record and that timestamp. Treat the customer as verified only after this logging action succeeds.
6. Use the retrieved date of birth and current date to determine whether the customer is 18 or older. Do not estimate age from the birth year alone.

If identity cannot be verified and logged, or the customer is under 18, do not continue to opening.

### 2. Retrieve and evaluate account history

1. Unlock `get_all_user_accounts_by_user_id_3847` with `unlock_discoverable_agent_tool`.
2. Call it through `call_discoverable_agent_tool` using the authenticated customer's `user_id`.
3. Inspect the returned account information to identify the customer's personal checking accounts and their statuses. Count the accounts that count toward the four-account personal-checking limit; do not substitute credit-card, referral, or other product results for this account lookup.
4. Determine whether any checking account was closed **for cause** in the six months before the current date. Account status alone is not proof of the closure reason. If the records do not provide sufficient closure history, obtain the required confirmation from the customer or use an available authoritative account-history source.
5. If the limit is reached, a qualifying closure for cause exists, or either condition cannot be established, do not open the account. State the applicable blocker without exposing internal tool details.

The packaged eligibility helper can make the age, six-month cutoff, and pass/block decision reproducible after the factual inputs have been collected. It does not retrieve data, verify identity, or make bank changes.

### 3. Discuss the documented travel options when relevant

When the customer is choosing based on overseas ATM costs and early direct deposit, communicate only documented facts:

- **Purple Account**: no Rho-Bank foreign ATM withdrawal fee, eligible global ATM operator-fee rebates up to $30 per month, and early direct deposit up to two days early. Third-party operator charges can still apply; its published currency conversion markup is 0.5% above the interbank rate. It has a $15 monthly maintenance fee that is waived by a $3,750 minimum daily balance.
- **Bluest Account**: no Rho-Bank foreign ATM withdrawal fee, ATM-fee rebates up to $50 per month, and early direct deposit two days early. It requires a $75,000 opening deposit and a $112,500 daily balance to keep benefits; falling below that daily balance carries a $75 monthly maintenance fee.

Do not promise the absolute lowest possible ATM cost because third-party ATM surcharges and the customer's actual usage affect the result. If the customer cannot meet Bluest's stated requirements, Purple may be the more suitable documented option for these travel needs, but the customer must still choose it. Confirm the final class exactly—for example, `Purple Account`, not merely “Purple.”

### 4. Open the account

Only after all checks pass and the customer has selected the exact official class:

1. Unlock `open_bank_account_4821`.
2. Call it through `call_discoverable_agent_tool` with:
   - `user_id`: authenticated customer's ID
   - `account_type`: `checking`
   - `account_class`: the customer-confirmed full official account name ending in `Account`
3. Report the successful opening in customer-facing terms and summarize relevant features or fees accurately. If the tool fails, report that it could not be completed; do not claim an account was opened or retry without an appropriate reason.

Do not add an opening-deposit transfer flow: no such personal-checking funding procedure is documented here.

## Eligibility helper

`scripts/evaluate_personal_checking_eligibility.py` reads one JSON object from stdin and writes one JSON result to stdout. It uses only the supplied facts.

### Input schema

```json
{
  "as_of": "YYYY-MM-DD or ISO-8601 timestamp",
  "date_of_birth": "MM/DD/YYYY or YYYY-MM-DD",
  "identity_verified": true,
  "closure_history_complete": true,
  "personal_checking_count": 0,
  "checking_records": [
    {
      "counts_toward_limit": true,
      "closed_for_cause": false,
      "closed_date": null
    }
  ]
}
```

`personal_checking_count` may be omitted only when every supplied `checking_records` item explicitly has `counts_toward_limit`. Set `closure_history_complete` to `false` whenever the retrieved records and customer confirmation do not establish the relevant closure history. A `closed_for_cause` value of `true` requires a valid `closed_date`; an unknown fact must not be represented as `false`.

### Output schema and use

The helper emits:

- `eligible`: true only when all requirements pass;
- `checks`: age, verification, account-limit, and closure-history results;
- `blockers`: customer-safe reasons not to open yet;
- `cutoff_date`: the inclusive six-month cutoff used for closure review;
- `next_action`: either `may_open_after_exact_class_confirmation` or `do_not_open`.

Run it with the collected runtime JSON, for example:

```sh
printf '%s' "$INPUT_JSON" | python3 scripts/evaluate_personal_checking_eligibility.py
```

Before calling the opening tool, validate that the helper returned `eligible: true`, `next_action: "may_open_after_exact_class_confirmation"`, identity logging has actually succeeded, and the exact class string is present and ends in `Account`. The helper output is an eligibility aid, not authorization to bypass the required banking-tool workflow.

## Missing-data and refusal handling

- If the customer declines or gives an out-of-scope response to the account-count or closure-for-cause question, leave the condition unresolved and do not open the account.
- If account retrieval returns no records, record that result but still ensure it is authoritative for both limit and closure review before treating it as a pass.
- If the user changes the requested product to business checking, savings, or another product, stop this workflow and use the corresponding documented procedure instead.
- If the customer wants a human agent rather than further clarification, use the normal transfer process with the appropriate supported reason.
