---
name: business-checking-single-best-fit
version: 1.0.0
description: Recommend one business checking account from supplied product evidence when a customer has hard requirements, apply a currently active recommendation-priority rule only among qualifying products, and safely transition to account-opening eligibility checks when the customer asks to proceed.
---

# Business Checking: Single Best-Fit Recommendation

Use this Skill when a customer wants one recommended business checking account rather than a broad comparison. It is particularly useful when the customer states non-negotiable fee, rebate, eligibility, balance, international-use, or support requirements.

## Inputs and evidence

At runtime, read the customer conversation, supplied product documents, internal policy documents, and any observed current time. Treat the documents as the source of truth for product terms, eligibility, promotion dates, and opening procedures.

Separate facts into:

- **Hard customer requirements**: explicitly non-negotiable conditions, such as a $0 overdraft fee or a minimum monthly ATM-rebate amount.
- **Confirmed customer attributes**: for example, an affirmed formation age.
- **Product facts**: fees, rebates, eligibility conditions, benefits, and limitations documented for each account.
- **Policy facts**: dated promotion priorities and required account-opening controls.
- **Unknowns**: do not turn vague preferences (for example, “easy” or “perks”) into unsupported promises.

Use `scripts/select_account.py` when product facts have been normalized into its JSON input schema. The script evaluates only supplied structured facts; it does not retrieve product data or open an account.

## Recommendation method

1. Extract the hard requirements and their thresholds. A statement such as “zero overdraft fees is non-negotiable” requires a documented overdraft fee of exactly $0. A request for “at least” a monthly rebate requires a documented cap at or above that amount.
2. Confirm any product-specific eligibility that is known from the customer’s answers. Do not represent an eligibility condition as fully cleared when information is missing.
3. Exclude every account that does not satisfy every hard requirement or has an unresolved required fact.
4. Check any recommendation-priority policy against the observed date. Apply it only while it is active and only to the already qualifying accounts. A promotion never overrides a customer requirement.
5. Select one account. State the account name, the specific facts that satisfy the customer’s requirements, and any material fee/limit the customer should understand. Do not provide an unwanted multi-account comparison.
6. If no account can be shown to meet all hard requirements, say so plainly, identify the blocking requirement or missing evidence, and ask only for the information needed to continue. Never invent a product feature.

For the supplied case, the evidence establishes the following relevant conclusion: the customer confirmed formation within four years, needs at least $15 per month in out-of-network ATM fee rebates, and requires a $0 overdraft fee. The dated promotion is active at the supplied observed time. Use the documented Sky Blue terms and active priority rule to recommend **Sky Blue** as the single fit. Disclose that its six-month free period is followed by the documented monthly maintenance fee. If discussing ATM use, distinguish the account’s own international ATM fee and any separate terminal-operator surcharge from the monthly rebate cap; do not promise that an operator surcharge is waived unless evidence says so.

A concise customer-facing response for this state should:

- lead with Sky Blue as the recommendation;
- explain that it has the documented $0 overdraft fee and qualifying monthly ATM-rebate cap, and that the customer’s stated formation age meets its stated eligibility condition;
- mention the six-month free period and the subsequent documented maintenance fee; and
- offer to proceed, rather than opening an account automatically.

## Transition to opening

A recommendation is not authorization to open an account. Do not begin an opening action until the customer clearly asks to proceed and supplies the requested profile identifier or another approved way to locate their profile.

When the customer asks to proceed:

1. Obtain the email address associated with the banking profile if it has not been provided.
2. Look up the customer using the appropriate normal banking tool. Do not guess an identity, user ID, or email.
3. Verify identity by confirming two of the four required identity fields (date of birth, email, phone number, address). Obtain the current timestamp and create the required verification record only after successful verification.
4. Retrieve the customer’s existing accounts and check every documented opening prerequisite: verified identity; at least one OPEN personal checking account; fewer than six business checking accounts; no CLOSED accounts; at least $500 in the applicable existing checking account; and confirmed requested account class.
5. If all prerequisites pass and the customer has confirmed the selected account class, use the normal banking-tool discovery and opening process named by the supplied opening procedure. Unlock/call only the documented tool and use its actual exposed schema; never fabricate arguments.
6. If a prerequisite fails or cannot be verified, do not open the account. Explain the specific documented blocker and appropriate next step.

Do not request or change contact information merely to make a recommendation. Do not use account lookup or account-opening tools before the customer has asked to proceed.

## Script interface

Run:

```text
python scripts/select_account.py < input.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD or ISO timestamp",
  "requirements": {
    "zero_overdraft_fee": true,
    "minimum_atm_rebate_monthly": "15.00",
    "company_age_years": 3
  },
  "accounts": [
    {
      "name": "string",
      "overdraft_fee": "0.00",
      "atm_rebate_monthly": "15.00",
      "max_company_age_years": 4,
      "promotion": {
        "start": "YYYY-MM-DD",
        "end": "YYYY-MM-DD",
        "priority": 1
      }
    }
  ]
}
```

All requirement fields are optional. For a hard fee or rebate requirement, provide the corresponding account value for every candidate; absent values cause that candidate to be marked for review rather than selected. `max_company_age_years` may be omitted only when the supplied evidence affirmatively establishes that no such condition applies to that product.

Output includes `ok`, `selected`, `qualifying`, and `review_required`. `selected` is either one normalized account result or `null`. Validate before using the result: `ok` must be true, `review_required` must be empty, and `selected` must be non-null. Then confirm the script’s selected facts against the source documents before communicating them to the customer.
