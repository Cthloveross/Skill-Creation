---
name: travel-checking-account-opening
description: Verify eligibility, compare documented overseas-ATM and early-direct-deposit checking benefits, and safely open a selected personal checking account using the normal banking discovery tools. Use for requests to open a checking account, especially travel-focused product selection.
---

# Travel checking account opening

Use this Skill when a customer wants a new personal checking account and may prioritize foreign/overseas ATM costs and early direct deposit. It distinguishes a product recommendation from an account-opening action: never open an account until identity, eligibility, the exact official account class, and any documented product opening condition are satisfied.

## Inputs and preserved context

Read the current conversation, customer-provided details, prior tool observations, and clarification results before asking anything. Treat prior successful tool observations as evidence that can be reused.

Interpret conversation control markers conservatively:

- Text before `###STOP###` is the customer's answer; do not discard it merely because it has the marker.
- `###OUT-OF-SCOPE###` means that requested information was not supplied. Do not repeatedly ask the same unanswered question in that turn.
- Do not infer a customer's ability to make an opening deposit from an account balance, employment, or travel plans.

A request for “whichever costs least” expresses a preference, but the opening procedure still requires confirmation of the exact official `account_class`. A recommendation alone is not an authorization to choose a different product if material eligibility or opening requirements remain unresolved.

## Product comparison from the supplied policy

For the documented travel requirement, compare only stated fees and benefits and disclose third-party fees separately.

- **Bluest Account**: Rho-Bank foreign ATM withdrawal fee is $0.00; third-party ATM fees are rebated up to $50 per monthly statement cycle; early direct deposit can be up to 2 days early. It requires a **$75,000 opening deposit** and a $112,500 daily balance to keep all benefits active.
- **Purple Account**: foreign ATM withdrawal fee is $0.00; worldwide ATM operator-fee rebates are up to $30 per month; early direct deposit can be up to 2 days early. A separate Purple policy describes a $2.50 Rho-Bank charge for an out-of-network ATM withdrawal. Do not erase this distinction or promise that every overseas ATM use is cost-free; operator fees can also apply.
- **Green Fee-Free Account**: foreign and out-of-network ATM fees are documented as $0.00, but it provides 0 days of early direct-deposit advance, so it does not meet a requirement for early direct deposit.
- **Evergreen Account** has a 2% foreign ATM withdrawal fee, minimum $3.00, so it is not a lowest-cost candidate under this documented comparison.

Consequently, Bluest is the strongest documented option for a customer who can meet its $75,000 opening deposit because it combines $0 foreign withdrawal fee, the larger $50 rebate cap, and two-day early direct deposit. If that opening-deposit condition is not confirmed, do not state Bluest can be opened. Explain the condition and present Purple as a documented two-day-early-deposit alternative with $0 stated foreign ATM fee and a $30 rebate cap, while disclosing the separate out-of-network policy.

Do not claim that a product has no opening requirement merely because none is present in the available materials.

## Required execution procedure

### 1. Establish identity and age

1. Identify the customer using a normal read-only customer lookup by supplied name, email, or user ID. If a prior lookup already resolved one unambiguous customer, reuse it.
2. Obtain or confirm at least **two of four** identity fields against that record: date of birth, email, phone number, and address. A customer who supplies both name and email can have the email matched, but name is not one of the four required fields; obtain or reuse confirmation of one of the four additional fields unless the platform’s already recorded interaction explicitly confirms two qualifying fields.
3. Get the current time with `get_current_time` for the audit timestamp.
4. Once two qualifying fields have been confirmed, call `log_verification` with every required field copied from the matched customer record and the current timestamp. Never invent missing field values.
5. Determine that the customer is at least 18 on the current date. Use `scripts/evaluate_eligibility.py` if structured date values are available. If the date of birth or current date cannot be determined, eligibility is unresolved.

A successful identity-verification audit is required before opening; do not rely on a name/email lookup alone as verification.

### 2. Check account eligibility

The supplied account-information procedure requires `get_all_user_accounts_by_user_id_3847`, even if it is not initially visible among ordinary tools.

1. Unlock it with `unlock_discoverable_agent_tool` using exactly `get_all_user_accounts_by_user_id_3847`.
2. Call it through `call_discoverable_agent_tool` with the resolved user ID, following the unlocked tool’s displayed schema.
3. Inspect all returned accounts. Before opening, establish that the prospective number of personal checking accounts will not exceed four and that there has been no checking account closed for cause within the preceding six months.
4. Use `scripts/evaluate_eligibility.py` to make the age, prospective-count, and six-month calculations reproducible when the tool result provides structured values. Map the tool result faithfully; do not treat unavailable closure reason/date data as proof of no closure for cause.

If account status, closure cause, or closure date needed for the check is absent or ambiguous, do not open the account. State that eligibility cannot yet be established and use only a supported normal read-only source if one is available. Do not substitute credit-card, referral, or transaction history for checking-account history.

### 3. Obtain a valid product selection and material opening confirmation

- Confirm the desired official account class exactly, using the full name ending in `Account` (for example, `Bluest Account` or `Purple Account`).
- For Bluest, specifically confirm that the customer can make the documented $75,000 opening deposit before proceeding. If the customer did not provide that confirmation or returned an out-of-scope answer, do not open Bluest.
- Explain any material documented fee, rebate cap, and requirement that affects the recommendation. Do not characterize third-party ATM operator charges as bank fees or guaranteed rebates beyond the stated cap.

If the customer chooses another account, use only that selected official account class; do not silently substitute the travel recommendation.

### 4. Open only after all gates pass

After identity verification, age, checking-account eligibility, closure review, official account-class confirmation, and product-specific conditions all pass:

1. Unlock `open_bank_account_4821` using `unlock_discoverable_agent_tool`.
2. Read the unlocked tool’s schema and call it via `call_discoverable_agent_tool` with only the required supported arguments. Use the verified customer ID and exact official account class where the schema requires them.
3. Do not invent an opening-deposit field, account status, funding source, or any other unsupported argument. If the tool explicitly requires a funding amount or confirmation, use only the customer-confirmed amount.
4. Report the actual tool result. Do not say an account was opened unless the opening tool reports success.

Scripts only evaluate supplied data and never perform banking actions; all verification logging, discovery, account lookup, and opening must be done with the declared normal banking tools.

## Customer-facing response patterns

- **All gates pass:** briefly confirm the selected account, relevant travel benefits/conditions, and the actual successful opening result.
- **A required fact is missing:** name the specific missing item, distinguish it from a refusal, and do not claim the account is open.
- **The customer cannot satisfy Bluest’s opening deposit:** offer the documented Purple comparison, disclose its separate out-of-network fee policy, and request an exact selection rather than opening an unconfirmed alternative.
- **Eligibility fails:** state that the account cannot be opened based on the failed requirement. Do not attempt the opening tool.

## Script interface and validation

`scripts/evaluate_eligibility.py` reads JSON from stdin and writes one JSON object to stdout. It accepts:

```json
{
  "date_of_birth": "MM/DD/YYYY or YYYY-MM-DD",
  "current_date": "MM/DD/YYYY or YYYY-MM-DD [optional time zone text]",
  "identity_verified": true,
  "personal_checking_accounts": [
    {"status": "open", "closure_date": null, "closed_for_cause": false}
  ]
}
```

`personal_checking_accounts` must contain only accounts classified as personal checking after the executor has faithfully filtered tool data. `closure_date` may be null. The script reports whether the supplied facts establish each objective rule and lists unknown fields. A valid output has `eligible_to_open: true` only if identity is verified, age is at least 18, the prospective count is at most four, and no qualifying closure is found; unknown required data produces `eligible_to_open: false` and a nonempty `unknown_or_invalid` list.

Example runnable call (illustrative placeholders only):

```sh
printf '%s' '{"date_of_birth":"1990-01-01","current_date":"2025-01-01","identity_verified":true,"personal_checking_accounts":[]}' | python3 scripts/evaluate_eligibility.py
```

Before relying on an output, check that it is JSON, that `unknown_or_invalid` is empty, and that every individual `checks` value is true. The executor must still perform the required banking-tool actions separately.
